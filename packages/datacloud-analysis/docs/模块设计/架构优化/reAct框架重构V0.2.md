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
