## 1. ReAct 与 LangGraph 生态对齐

---

### 1.1 现状

#### 1.1.1 自研图拓扑

```
用户请求
  │
  ▼
[intend]  ← 意图识别 / 命令路由
  │
  ├─ command 路径 ──────────────────────────► [respond]
  │
  └─ analysis 路径
       │
       ▼
    [llm_call]  ← 每轮 LLM 推理（读 state["messages"]，写 AIMessage）
       │
       │ Send(tool_name, state) ← 按 tool_calls 并行路由
       │
       ├─► [per-tool node: query_xxx]  ┐
       ├─► [per-tool node: compute_xxx]├─ 各工具独立节点（LangGraph Send API）
       └─► [per-tool node: ...]        ┘
              │  汇聚
              ▼
        [tool_dispatcher]  ← 读 react_messages_log，分发调用，追加 ToolMessage
              │
              ├─ execution_status=finish_react ──► [finish_react_node] ──► [respond]
              │
              ├─ execution_status=clarify_needed
              │     │
              │     ▼
              │  [analyze_clarify]  ← LLM 分析歧义
              │     │
              │     ▼
              │  [user_clarify]  ← 发送 SSE 等待用户回复（interrupt）
              │     │  resume
              │     ▼
              │  [tool_dispatcher]  ← 重入，带回填参数继续执行
              │
              └─ 正常 → 回到 [llm_call]（下一轮）
```

#### 1.1.2 核心实现模块

| 模块                      | 规模     | 职责                                                     |
| ------------------------- | -------- | -------------------------------------------------------- |
| `react_loop.py`           | ~1208 行 | LLM 调用、流式输出、工具分发、三级停止、interrupt/resume |
| `graph_builder.py`        | ~277 行  | 节点注册、边路由、Send API 配置                          |
| `tool_dispatcher_node.py` | ~120 行  | 工具分发、ClarificationNeededError 捕获                  |
| `llm_call_node.py`        | ~96 行   | V0.3 图模式下的 LLM 节点（与 react_loop 并存）           |
| `state.py`                | ~228 行  | 完整 AgentState 字段定义                                 |

#### 1.1.3 三级停止条件

| 级别 | 触发条件                            | 说明                           |
| ---- | ----------------------------------- | ------------------------------ |
| L1   | LLM 调用 `finish_react` 工具        | 最优路径，携带结构化结果元数据 |
| L2   | LLM 不产生 tool_calls，直接文字回答 | 适用于简单问答                 |
| L3   | 超出 `max_rounds`（默认 10 轮）     | 兜底保护，返回降级答案         |

#### 1.1.4 interrupt / resume：方案 A vs 方案 B

> **为什么叫"方案 B"？**  
> 在 react_loop 的设计演进中，曾存在两套 interrupt/resume 实现，
> 最终选定方案 B 作为生产方案并完全替换方案 A。

**方案 A（已废弃）— 进程内缓存**

中断时将恢复上下文存储在 Worker 进程内存的 `_resume_result_cache`（`OrderedDict`）中：

```
Worker 内存
  └─ _resume_result_cache[session_id] = {messages, pending_tool_calls, ...}
```

- 优点：实现简单，无外部依赖
- **致命缺陷**：Worker 重启或请求被路由到不同实例时，内存数据丢失，
  resume 无法恢复，用户体验中断

**方案 B（当前生产方案）— LangGraph State 持久化**

中断时将执行上下文序列化写入 LangGraph State 字段：

```python
state["react_messages"]           = _serialize_messages(messages)   # 消息历史
state["react_pending_tool_calls"] = pending                          # 未执行 tool_calls
state["react_round_idx"]          = round_idx                        # 轮次索引
state["react_last_query_data"]    = _last_query_data                 # 查询数据缓存
```

LangGraph checkpoint（OpenGauss）自动将 State 持久化到数据库。
恢复时从 State 反序列化，逐条重放 pending_tool_calls，无需重调 LLM。

- 优点：天然跨实例/重启持久化；依赖 LangGraph 生态标准能力
- 代价：State 字段增多（4 个专用字段）；需 `_serialize_messages` / `_deserialize_messages` 往返

**迁移到 prebuilt 后的对应关系**

`create_react_agent` 内置 `interrupt_before` / `interrupt_after` 机制，直接利用
LangGraph checkpoint 存储完整 State，不再需要手工序列化消息历史。
方案 B 的四个 react_* 字段可以全部删除。

#### 1.1.5 澄清子流程（最重定制点）

`ClarificationNeededError` 由工具的 `before_call_back` 钩子抛出，
`tool_dispatcher_node` 捕获后写入 `pending_clarification_context`，
路由至 `analyze_clarify → user_clarify` 子图，等待用户回复后 resume 并回填参数。
整个子流程深度耦合于 state 字段与插件钩子体系。

---

### 1.2 目标架构

#### 1.2.1 LangGraph prebuilt `create_react_agent` 拓扑

```
用户请求
  │
  ▼
[agent]  ← LLM 推理节点（内置消息管理）
  │
  │ 有 tool_calls → should_continue → "tools"
  ▼
[tools]  ← 工具执行节点（内置并行、内置 ToolMessage 追加）
  │
  ├─ ToolMessage.name == "finish_react" → [after_tools] → END   （L1，见 1.2.2）
  │
  └─ 其他工具 → [after_tools] → 回到 [agent]（下一轮）

停止条件：
  L1: finish_react 工具执行完毕后由 after_tools 节点检测
  L2: agent 节点产出 AIMessage 无 tool_calls → should_continue → END
  L3: react_round_idx >= max_rounds → should_continue → END
```

`create_react_agent` 提供：内置消息裁剪（`trim_messages`）、内置重试、
内置 checkpoint、原生 `interrupt_before`/`interrupt_after`。

#### 1.2.2 finish_react + Markdown 格式化输出兼容性

**结论：完全兼容，`finish_react` 工具仍可由 LLM 调用并产出 Markdown。**

迁移后的关键设计要点：**不能**在 `should_continue` 看到 finish_react 就直接返回 `END`，
否则 tools 节点不运行，finish_react 工具体永远不执行，Markdown 输出丢失。

正确流程如下：

```
① LLM 产出 AIMessage，tool_calls = [finish_react(answer="## 分析结果\n...")]
② should_continue 看到 tool_calls 非空 → 返回 "tools"（不能在此终止！）
③ [tools] 节点执行 finish_react 工具体 → 产出 ToolMessage(content="## 分析结果\n...")
④ [after_tools] 检测 ToolMessage.name == "finish_react" → 返回 END
⑤ 图终止，Markdown 内容在 ToolMessage 中，由 respond 节点提取并返回给用户
```

对应代码：

```python
def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """agent 节点出口：决定是否继续调用工具。"""
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not (last.tool_calls or []):
        return "__end__"                                    # L2：LLM 直接回答
    if int(state.get("react_round_idx") or 0) >= max_rounds:
        return "__end__"                                    # L3：轮数保护
    return "tools"                                          # 含 finish_react 也走 tools

def after_tools(state: AgentState) -> Literal["agent", "__end__"]:
    """tools 节点出口：检测 finish_react 是否已执行。"""
    messages = state["messages"]
    # 取最近一批 ToolMessage（本轮工具调用结果）
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            break
        if isinstance(msg, ToolMessage) and msg.name == "finish_react":
            return "__end__"                                # L1：finish_react 已执行，终止
    return "agent"                                          # 继续下一轮 LLM 推理
```

#### 1.2.3 能力对比

| 能力维度                           | 自研 StateGraph                | `create_react_agent`          | 迁移复杂度           |
| ---------------------------------- | ------------------------------ | ----------------------------- | -------------------- |
| interrupt/resume                   | ✅ 方案 B（State 序列化）       | ✅ 原生 checkpoint interrupt   | 低（需验证语义等价） |
| 工具并行执行                       | ✅ Send API                     | ✅ 内置并行                    | 低                   |
| 消息窗口裁剪                       | ✅ 手工 `_trim_messages_window` | ✅ 内置 `trim_messages`        | 低                   |
| L1 finish_react + Markdown 输出    | ✅ 自定义 sentinel 工具         | ✅ after_tools 节点检测（见 1.2.2） | 中              |
| L3 max_rounds 保护                 | ✅ 轮次计数                     | ✅ should_continue 检测        | 低                   |
| 澄清子流程                         | ✅ 深度集成                     | ⚠️ 需自定义 HookAwareToolNode  | **高**（最大障碍）   |
| 插件钩子（before/after_call_back） | ✅ 完整体系                     | ⚠️ 需继承 ToolNode 实现        | **高**               |
| 流式 thinking token                | ✅ 直接控制                     | ⚠️ 需自定义 stream handler     | 中                   |
| 可观测性 / LangSmith               | ⚠️ 部分                         | ✅ 原生集成                    | —                    |
| 代码维护成本                       | ❌ 高（>1200 行）               | ✅ 低（prebuilt）              | —                    |

#### 1.2.4 关键结论

**澄清子流程与插件钩子是迁移的核心障碍**，但两者均有明确的适配路径（见 1.3.3、1.3.4）。
`finish_react` + Markdown 输出在迁移后完全保留，无功能退化。

---

### 1.3 POC 验证方案

#### 1.3.1 POC 范围与边界

**在 POC 范围内（必须验证，任一失败则中止）**

| 优先级 | 验证项 | 预计耗时 |
|--------|--------|----------|
| 1 | `finish_react` + `after_tools` 停止条件 + Markdown 输出完整性 | 1-2 天 |
| 2 | `HookAwareToolNode` 插件钩子注入（before/after + ClarificationNeededError） | 2-3 天 |
| 3 | 澄清子流程接入父图（ClarificationNeededError → analyze_clarify → user_clarify → resume） | 3-5 天 |
| 4 | interrupt/resume 与 prebuilt checkpoint 的语义等价性 | 1-2 天 |
| 5 | 流式 thinking token 的 stream handler 适配 | 1 天 |

**不在 POC 范围内**

- 生产迁移、数据迁移
- 性能压测（功能等价后再做）
- byclaw-data worker 层改造

#### 1.3.2 POC 落地工作流

**启动条件**：P0-1、P0-2、阶段 A~D 整改全部完成，主干稳定后再启动 POC。

```
Step 1  拉 POC 分支（不影响 main）
────────────────────────────────────────────────────────────
git checkout main && git pull
git checkout -b poc/langgraph-prebuilt-react

Step 2  按优先级顺序逐项验证（不通过即中止，不进入下一项）
────────────────────────────────────────────────────────────
① finish_react + Markdown 输出
   → 写 tests/dca/poc/test_prebuilt_finish_condition.py
   → 通过后继续

② HookAwareToolNode 插件钩子
   → 实现 src/datacloud_analysis/orchestration/execution/hook_aware_tool_node.py
   → 写 tests/dca/poc/test_prebuilt_hooks.py
   → 通过后继续

③ 澄清子流程
   → 实现 src/datacloud_analysis/orchestration/execution/clarify_subgraph.py
   → 写 tests/dca/poc/test_prebuilt_clarification.py
   → 通过后继续

④ interrupt/resume 等价性
   → 写 tests/dca/poc/test_prebuilt_interrupt_resume.py

⑤ thinking token 流式适配
   → 写 tests/dca/poc/test_prebuilt_streaming.py

Step 3  输出 POC 报告（通过 / 部分通过 / 失败）
────────────────────────────────────────────────────────────
内容：验证结论、代码行数对比、风险点、建议决策

Step 4  决策（见 1.3.6 决策门控）
────────────────────────────────────────────────────────────
通过 → 从 main 拉 feature/migrate-to-prebuilt-react 正式开发
部分通过 → 局部借鉴（见 1.3.7 最低收益线）
失败 → POC 分支直接丢弃，不合并 main
```

> **POC 分支不合并 main。** 验证性代码质量要求低于生产，正式迁移在独立的
> feature 分支重新写生产级代码，复用 POC 的结论和接口设计，不复用 POC 的实现。

#### 1.3.3 澄清子流程适配方案

在 `create_react_agent` 外层包一个**父图**，prebuilt 作为子图运行，
澄清子流程在父图层处理：

```
[父图: analysis_graph]
  │
  ├─ [prebuilt_react_subgraph]  ← create_react_agent（含 HookAwareToolNode）
  │       工具执行时若抛 ClarificationNeededError
  │       → HookAwareToolNode 捕获，写入 state["execution_status"]="clarify_needed"
  │       → 父图出口路由至澄清子流程
  │
  ├─ [analyze_clarify]  ← 与当前实现复用
  └─ [user_clarify]     ← 与当前实现复用，执行 interrupt，等待用户 resume
```

父图边路由：

```python
def route_after_tools(state: AgentState) -> str:
    if state.get("execution_status") == "clarify_needed":
        return "analyze_clarify"      # 路由到澄清子流程
    return "prebuilt_react_subgraph"  # 继续下一轮（或已结束）
```

#### 1.3.4 插件钩子机制实现（`HookAwareToolNode`）

继承 `langgraph.prebuilt.ToolNode`，覆写 `ainvoke`（公开 API，比 `_run_one` 稳定）：

```python
from typing import Any, Literal
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from datacloud_analysis.tool_hook_plugins.types import ClarificationNeededError


class HookAwareToolNode(ToolNode):
    """在 prebuilt ToolNode 基础上注入 before/after_call_back 钩子。"""

    def __init__(
        self,
        tools: list[Any],
        *,
        plugin_manager: Any,
        loader: Any = None,
        gateway_context: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(tools, **kwargs)
        self._pm = plugin_manager
        self._loader = loader
        self._gw_ctx = gateway_context

    async def ainvoke(
        self,
        state: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        messages = list(state.get("messages") or [])
        last_ai = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage)), None
        )
        if not last_ai or not last_ai.tool_calls:
            return await super().ainvoke(state, config, **kwargs)

        # ── before_call_back：逐工具注入，可修改参数，可触发澄清 ──────────
        patched_calls: list[dict[str, Any]] = []
        for tc in last_ai.tool_calls:
            tool_name = str(tc.get("name") or "")
            ctx: dict[str, Any] = {
                "tool_name": tool_name,
                "tool_params": dict(tc.get("args") or {}),
                "gateway_context": self._gw_ctx,
                "loader": self._loader,
            }
            try:
                ctx = await self._pm.run_before_hooks(ctx, config)
            except ClarificationNeededError as exc:
                # 返回 Command，父图路由至澄清子流程
                return Command(
                    update={
                        "execution_status": "clarify_needed",
                        "pending_clarification_context": {
                            **exc.context,
                            "tool_name": tool_name,
                        },
                    },
                    goto="analyze_clarify",
                )
            patched_calls.append({**tc, "args": ctx["tool_params"]})

        # ── 用修改后的 tool_calls 替换最后一条 AIMessage ────────────────
        patched_ai = last_ai.model_copy(update={"tool_calls": patched_calls})
        patched_state = {**state, "messages": [*messages[:-1], patched_ai]}

        # ── 执行工具（走 prebuilt 原有逻辑）────────────────────────────
        result = await super().ainvoke(patched_state, config, **kwargs)

        # ── after_call_back：遍历本轮产出的 ToolMessage ─────────────────
        for msg in result.get("messages") or []:
            if isinstance(msg, ToolMessage):
                await self._pm.run_after_hooks(
                    {"tool_name": msg.name, "result": msg.content},
                    config,
                )

        return result
```

**关键设计说明**

| 点 | 说明 |
|----|------|
| 覆写 `ainvoke` 而非 `_run_one` | `ainvoke` 是 Runnable 公开接口，随 LangGraph 版本升级破坏风险低 |
| `ClarificationNeededError` 返回 `Command` | LangGraph 父图收到 Command 后路由至 `analyze_clarify` 节点 |
| `model_copy` 替换 tool_calls | AIMessage 为 Pydantic 不可变对象，必须用 `model_copy` 生成新实例 |
| after_call_back 在 `super().ainvoke` 之后 | 确保工具已执行、ToolMessage 已生成再触发后置钩子 |

#### 1.3.5 评估维度与度量指标

| 维度             | 验证方法                                                      | 通过标准              |
| ---------------- | ------------------------------------------------------------- | --------------------- |
| **功能等价性**   | 跑现有 338 个单测（POC 分支不删除任何现有测试）               | 通过率 ≥ 当前 303/338 |
| **finish_react** | `test_prebuilt_finish_condition.py` 验证 Markdown 内容完整性  | 全部通过              |
| **interrupt/resume** | `test_prebuilt_interrupt_resume.py` 覆盖中断 + 跨实例恢复 | 全部通过              |
| **澄清子流程**   | `test_prebuilt_clarification.py` 覆盖完整澄清链路             | 全部通过              |
| **插件钩子**     | before/after_call_back 在 prebuilt 路径可触发，参数透传正确   | 验证通过              |
| **代码行数**     | 统计 POC 分支相对 main 的净增/删行数                          | 净减少 > 30%          |

#### 1.3.6 决策门控

| 决策                    | 触发条件                                                              |
| ----------------------- | --------------------------------------------------------------------- |
| **全量迁移**            | 全部 5 项验证通过 + 代码净减少 > 30%                                  |
| **保留自研 + 局部借鉴** | 澄清子流程或钩子适配复杂度超预期，但 finish_react / interrupt 验证通过 |
| **放弃迁移**            | HookAwareToolNode 无法等价替代，或 prebuilt 内部 API 在升级中频繁破坏  |

#### 1.3.7 最低收益线（局部借鉴，无需改图拓扑）

即便全量迁移 POC 失败，以下三项改动可独立落地，**无需修改图拓扑**，风险极低：

1. 将 `react_loop.py` 的消息裁剪替换为 `langchain_core.messages.trim_messages`
2. 将 `llm_retry.py` 的重试逻辑替换为 `langchain_core` 的 `with_retry` 装饰器
3. 引入 `langchain_core.RunnableWithFallbacks` 替代手工 fallback 切换

#### 1.3.8 迁移路径（全量迁移 POC 通过后）

```
阶段 1（2 周）：从 main 拉 feature/migrate-to-prebuilt-react
              实现 HookAwareToolNode + after_tools 节点，替换 react_loop 核心循环

阶段 2（2 周）：接入澄清子图父图结构，端到端回归全量测试套件

阶段 3（1 周）：thinking token 流式适配，LangSmith 可观测性验证

阶段 4（1 周）：生产灰度（feature flag DATACLOUD_USE_PREBUILT_REACT=false 默认关闭）
              监控 success_rate / latency / interrupt_resume 成功率
              无异常后切换默认值为 true，保留旧路径一个版本后删除
```



### 1.4 实现设计

---

#### 1.4.1 新图拓扑

```
START
  │
  ▼
[intend]  ← 命令路由 + user_query 提取（不变）
  │
  ├─ command_done ─────────────────────────────────────────────────► END
  │
  └─ react
       │
       ▼
    [agent]  ← LLM 推理（bind_tools + trim_messages + 流式输出）
       │
       ├─ L2: 无 tool_calls ──────────────────────────────────────► [respond]
       ├─ L3: react_round_idx ≥ max_rounds ────────────────────────► [respond]
       └─ 有 tool_calls（含 finish_react）
            │
            ▼
         [tools]  ← HookAwareToolNode（before/after hook 注入）
            │
            ├─ ClarificationNeededError
            │     └─► Command(goto="analyze_clarify")
            │               │
            │         [analyze_clarify]  ← LLM 分析歧义（复用现有节点）
            │               │
            │         [user_clarify]     ← interrupt，等待用户回复
            │               │ resume
            │               └──────────────────────────────────────► [tools]
            │
            └─ 正常执行（after_tools_route 路由）
                  │
                  ├─ L1: finish_react ToolMessage 存在
                  │     └─► [finish_react_node]  ← 提取 react_final（微调）
                  │               └─────────────────────────────────► [respond]
                  │
                  └─ 其他工具 ────────────────────────────────────► [agent]（下一轮）

[respond]  ← format_result()（Markdown / 6001 协议，不变）
  └─► END
```

对比当前 V0.3 拓扑，**新增** `after_tools_route` 路由函数、`HookAwareToolNode`；
**删除** `tool_dispatcher_node`、`make_tool_node`（per-tool Send API）；
**保留** `intend`、`finish_react_node`（微调）、`respond`、澄清子流程三节点。

---

#### 1.4.2 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| **新增** | `execution/hook_aware_tool_node.py` | HookAwareToolNode 实现 |
| **重写** | `orchestration/graph_builder.py` | 按新拓扑重组节点与边 |
| **微调** | `execution/finish_react_node.py` | 适配 `react_last_query_data` 来源（见 1.4.5） |
| **微调** | `execution/llm_call_node.py` | 提取为独立 `agent` 节点，移除旧路由判断 |
| **保留** | `orchestration/intend/` | 不变 |
| **保留** | `orchestration/respond/` | 不变 |
| **保留** | `orchestration/clarification/` | 不变（直接复用） |
| **保留** | `orchestration/state.py` | 不变（react_* 字段迁移完成后再清理） |
| **迁移后删除** | `execution/react_loop.py` | ~1208 行，完全替代后删除 |
| **迁移后删除** | `execution/tool_dispatcher_node.py` | 被 HookAwareToolNode 替代 |
| **迁移后删除** | `execution/make_tool_node.py` | Send API per-tool 模式废弃 |

---

#### 1.4.3 阶段一（1 周）：HookAwareToolNode + 停止条件

**目标**：实现新工具执行层，在独立测试中验证 finish_react + Markdown 路径。

##### HookAwareToolNode（`execution/hook_aware_tool_node.py`）

设计见 1.3.4，生产级关键点补充：

```python
class HookAwareToolNode(ToolNode):
    async def ainvoke(self, state, config=None, **kwargs):
        # 1. before_call_back：按工具逐一注入，可修改参数，可触发澄清
        # 2. ClarificationNeededError → return Command(goto="analyze_clarify")
        # 3. super().ainvoke(patched_state, config) — 执行工具
        # 4. after_call_back：遍历本轮 ToolMessage，触发后置钩子
        ...
```

注意事项：
- `patched_state["messages"]` 必须用 `model_copy` 替换最后一条 AIMessage，不能直接赋值（Pydantic 不可变）
- `after_call_back` 只遍历本轮新增 ToolMessage（最后一条 AIMessage 之后的 ToolMessage）
- `gateway_context` 从 `config["configurable"]["gateway_context"]` 读取，优先级高于构造函数注入

##### 路由函数

```python
def should_continue(state: AgentState) -> Literal["tools", "respond"]:
    """agent 节点出口。"""
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not (last.tool_calls or []):
        return "respond"                             # L2：LLM 直接文字回答
    if int(state.get("react_round_idx") or 0) >= _DEFAULT_MAX_ROUNDS:
        return "respond"                             # L3：轮数保护
    return "tools"                                   # finish_react 也走 tools（必须执行工具体）


def after_tools_route(state: AgentState) -> Literal["agent", "finish_react_node"]:
    """tools 节点出口（正常执行路径，ClarificationNeededError 由 Command 绕过此函数）。"""
    messages = state["messages"]
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            break
        if isinstance(msg, ToolMessage) and msg.name == "finish_react":
            return "finish_react_node"               # L1：finish_react 已执行
    return "agent"                                   # 继续下一轮推理
```

**阶段一验收**：`finish_react + Markdown` 单测全通；`before/after_call_back` 单测全通；
`ClarificationNeededError → Command` 单测全通。

---

#### 1.4.4 阶段二（1 周）：父图重构

**目标**：`graph_builder.py` 按新拓扑完整重连所有节点，端到端回归。

##### 新 `graph_builder.py` 骨架

```python
def build_analysis_graph(
    prompts_overwrite=None,
    tools=None,
    loader=None,
    redirect_tools=None,
) -> StateGraph[AgentState]:
    builder = StateGraph(AgentState)

    # ── 节点 ──────────────────────────────────────────────────────────────
    builder.add_node("intend",            _intend)
    builder.add_node("agent",             make_llm_call_node(...))   # 现有 llm_call_node 复用
    builder.add_node("tools",             HookAwareToolNode(
                                              tools_list,
                                              plugin_manager=...,
                                              loader=loader,
                                          ))
    builder.add_node("finish_react_node", finish_react_node)
    builder.add_node("analyze_clarify",   analyze_clarify_node)
    builder.add_node("user_clarify",      user_clarify_node)
    builder.add_node("respond",           respond_node)

    # ── 边 ────────────────────────────────────────────────────────────────
    builder.add_edge(START, "intend")
    builder.add_conditional_edges(
        "intend", _route_after_intend,
        {"command_done": END, "react": "agent"},
    )
    builder.add_conditional_edges(
        "agent", should_continue,
        {"tools": "tools", "respond": "respond"},
    )
    builder.add_conditional_edges(
        "tools", after_tools_route,
        {"agent": "agent", "finish_react_node": "finish_react_node"},
    )
    # ClarificationNeededError 由 HookAwareToolNode 返回 Command(goto="analyze_clarify")
    # LangGraph 自动路由，无需额外 add_conditional_edges
    builder.add_conditional_edges(
        "analyze_clarify", _route_after_analyze,
        {"user_clarify": "user_clarify", "tools": "tools"},
    )
    builder.add_edge("user_clarify",      "tools")
    builder.add_edge("finish_react_node", "respond")
    builder.add_edge("respond",           END)

    return builder
```

##### L2/L3 在 `respond` 的处理

`should_continue` L2/L3 路由到 `respond` 时，`state["react_final"]` 可能未设置。
在 `respond_node` 开头增加兜底逻辑：

```python
# respond_node 兜底：L2/L3 时 react_final 未设置，从最后一条 AIMessage 构建
if not state.get("react_final"):
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    answer = extract_ai_text(last_ai.content) if last_ai else ""
    react_final = {
        "result_type": "text",
        "answer": answer,
        "answer_streamed": bool(state.get("answer_streamed")),
    }
else:
    react_final = state.get("react_final") or {}
```

**阶段二验收**：全量 `pytest tests/dca` 通过率 ≥ 当前基线（342/342）；
`intend → agent → tools → finish_react_node → respond` 链路 E2E 通过；
澄清子流程链路通过。

---

#### 1.4.5 阶段三（5 天）：高风险适配

**目标**：解决两个未验证风险点，并修复 `react_last_query_data` 来源问题。

##### 风险一：interrupt/resume 语义验证（⚠️ 最高风险）

**问题**：方案 B 的 4 个 `react_*` 序列化字段（`react_messages`、`react_pending_tool_calls`、
`react_round_idx`、`react_last_query_data`）在新架构下由 LangGraph 原生 checkpoint 替代。
需要验证：真实 OpenGauss checkpointer 下，`user_clarify → interrupt()` 中断后，
跨请求/跨实例恢复时 `state["messages"]` 与 `react_round_idx` 完整保留。

**验证方法**（集成测试，非 mock）：
```python
# tests/dca/integration/test_interrupt_resume_prebuilt.py
async def test_interrupt_resume_across_invocations():
    # 1. 启动 graph，执行到 user_clarify interrupt()
    # 2. 序列化 checkpoint 到 OpenGauss
    # 3. 新实例加载 checkpoint，resume
    # 4. 断言：messages 完整，round_idx 正确，工具参数回填成功
```

**卡点**：此测试不通过，阻塞阶段三完成，不进入阶段四。

---

##### 风险二：流式 thinking token 适配（⚠️ 中风险）

**问题**：现有 `_invoke_llm_with_fallback` 在 `react_loop.py` 中直接控制流式输出，
推送 thinking token 给 `gateway_context.emit_chunk()`。
`llm_call_node.py` 已复用此逻辑。新架构保留 `make_llm_call_node`（agent 节点），
不涉及 prebuilt 的 `astream_events`，因此**该风险实际可控**：
只需确认 `_invoke_llm_with_fallback` 在新图拓扑中被正确调用即可，
无需修改流式推送实现。

**验证方法**：
```python
# tests/dca/integration/test_thinking_token_stream.py
async def test_thinking_token_emitted_in_new_graph():
    # mock gateway_context.emit_chunk
    # 运行新图一轮推理
    # 断言 emit_chunk 被调用且 event_type=thinking
```

---

##### `react_last_query_data` 来源修复

**问题**：`finish_react_node` 读取 `state["react_last_query_data"]` 填充 `query_data`，
此字段由旧 `react_loop.py` 在工具执行后写入。新架构中 `react_loop.py` 被删除，
写入者消失，`query_data` 将永远为 `None`。

**修复方案**：在 `HookAwareToolNode.ainvoke` 的 after_call_back 阶段，
检测 ToolMessage 中包含 query_result 格式数据时，写入 `state["react_last_query_data"]`：

```python
# hook_aware_tool_node.py — after_call_back 后追加
for msg in result.get("messages") or []:
    if isinstance(msg, ToolMessage) and msg.name != "finish_react":
        # 尝试解析工具返回的 query_data
        _try_persist_query_data(state, msg.content)
```

或更简单：`finish_react` 工具的 args 中已含 `result_type` 和 `answer`，
`query_data` 通过 `react_last_query_data` 传递的场景仅限 `query_result` 类型。
确认 `query_*` 工具是否直接在 finish_react args 里携带完整 query_data，
若是则 `react_last_query_data` 可废弃，`finish_react_node` 直接从 tool_call args 读取。

> **⚠️ 待确认**：在阶段三开始前，需 code review `query_*` 工具的 finish_react 调用约定，
> 确定 query_data 是否已在 finish_react args 中传递。

---

#### 1.4.6 阶段四（3 天）：feature flag + 灰度上线

```python
# 环境变量开关（默认关闭，不影响现有生产）
DATACLOUD_USE_PREBUILT_REACT = os.getenv("DATACLOUD_USE_PREBUILT_REACT", "false").lower()

def build_analysis_graph(...):
    if DATACLOUD_USE_PREBUILT_REACT == "true":
        return _build_prebuilt_graph(...)   # 新路径
    return _build_legacy_graph(...)         # 旧路径（现有代码不动）
```

**灰度监控指标**：

| 指标 | 采集方式 | 告警阈值 |
|------|----------|----------|
| `success_rate` | respond_node 正常完成 / 总请求 | < 95% 回滚 |
| `avg_latency` | intend → respond 耗时 | 较旧路径 > 20% 告警 |
| `interrupt_resume_success` | user_clarify resume 成功 / interrupt 次数 | < 100% 立即回滚 |
| `l3_rate` | max_rounds 触发比例 | 较旧路径 > 5% 告警 |

**上线顺序**：
1. 部署新版本（`DATACLOUD_USE_PREBUILT_REACT=false`，旧路径运行）
2. 单台 worker 切 `true`，观察 1 小时
3. 逐步扩大（25% → 50% → 100%）
4. 100% 稳定 1 周后，删除旧路径代码，移除 feature flag

---

#### 1.4.7 集成测试卡点清单

以下测试为**硬卡点**，任一失败阻塞对应阶段推进：

| 卡点 | 测试文件 | 阻塞阶段 |
|------|----------|---------|
| `finish_react + Markdown` 内容完整性 | `tests/dca/unit/test_hook_aware_tool_node.py` | 阶段一 |
| `before/after_call_back` 参数透传正确 | `tests/dca/unit/test_hook_aware_tool_node.py` | 阶段一 |
| `ClarificationNeededError → Command` 路由 | `tests/dca/unit/test_hook_aware_tool_node.py` | 阶段一 |
| 全量单测回归（≥ 342 passed） | `tests/dca/` | 阶段二 |
| 澄清 E2E（ambiguous → resume → dispatch） | `tests/dca/unit/test_clarification_e2e_chain.py` | 阶段二 |
| interrupt/resume 跨实例语义等价 | `tests/dca/integration/test_interrupt_resume_prebuilt.py` | 阶段三 |
| thinking token 流式推送 | `tests/dca/integration/test_thinking_token_stream.py` | 阶段三 |

---

#### 1.4.8 完成标志与回滚策略

**迁移完成标志**（满足全部才可删除旧代码）：

- [ ] `DATACLOUD_USE_PREBUILT_REACT=true` 生产运行 ≥ 7 天，0 次 interrupt_resume 失败
- [ ] `react_loop.py` 代码路径监控确认零调用
- [ ] 净代码行数减少 > 30%（`react_loop.py` 1208 行 + `tool_dispatcher_node.py` 120 行 + `make_tool_node.py` 已删除）

**回滚策略**：

- 快速回滚：`DATACLOUD_USE_PREBUILT_REACT=false`，无需重启，下次请求即走旧路径
- 数据回滚：LangGraph checkpoint 格式兼容（state 字段超集），旧版本可读新版本 checkpoint
- 不兼容场景：若 `react_*` 序列化字段在新版本被清理，旧版本 resume 时可能失败 → **字段清理必须在旧路径完全下线后执行**
