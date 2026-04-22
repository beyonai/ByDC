# datacloud-analysis 模型调用 & ReAct 优化整改方案

**版本：** v1.1  
**日期：** 2026-04-21  

---

## 1. 背景与问题清单

基于当前架构评估与代码评审，问题按优先级列出：

1. `P0`：`tool_dispatcher_node` 中 `ToolMessage` 因死代码永远不追加到 `react_messages_log`，工具结果丢失。
2. `P0`：`llm_retry.py` 存在三处代码缺陷，`stream_llm_call_with_retry` 在任何调用场景下均会崩溃。
3. `P1`：`tool_dispatcher_node` 未读取请求级 `configurable.gateway_context`，上下文透传不一致。
4. `P2`：`interrupt/resume` 能力依赖 `bootstrap.setup()` 先执行，未初始化时会静默降级到无 checkpoint。
5. `P2`：LLM fallback 模型能力在运行时被硬关闭（`_build_fallback_llm() -> None`），且底层重试函数存在缺陷（见 P0-2）。
6. `P3`：`finish_react` 判定依赖 `calls[0]`，混合 tool_calls 存在行为歧义。
7. `P3`：ReAct 采用自研 StateGraph 流程，未直接使用 LangGraph prebuilt ReAct（`create_react_agent`）。

---

## 2. 整改目标

1. 修复工具调用结果丢失与重试函数崩溃两处 P0 缺陷，恢复基础功能正确性。
2. 保证模型调用链路上下文透传一致（尤其 `gateway_context`）。
3. 保证中断、重试、恢复在生产环境"默认可用、不可静默失效"。
4. 提升模型不可用场景的容灾能力（主模型重试 + fallback）。
5. 消除 ReAct 终止判定边界问题，避免误停或漏执行。
6. 明确 ReAct 架构路线：短期稳态优化自研图；中期评估是否切换 LangGraph prebuilt。

---

## 3. 分阶段整改方案

## 阶段 P0-1（最高优先级）：修复 `tool_dispatcher_node` ToolMessage 死代码

### 问题根因

`tool_dispatcher_node.py` 中，工具调用成功后追加 `ToolMessage` 的代码位于
`except ClarificationNeededError` 块的 `return` 语句之后，属于死代码，永远不会执行：

```python
# 当前错误结构（伪代码）
except ClarificationNeededError as exc:
    ...
    return {"execution_status": "clarify_needed", ...}  # ← 函数已 return

    # ⚠️ 以下永远不执行（return 之后 + result 未赋值 → NameError）
    tool_msg = ToolMessage(content=str(result), ...)
    messages.append(tool_msg)
```

**后果**：正常工具调用成功后，工具结果从不写入 `react_messages_log`。下一轮 LLM
拿到的历史消息缺少所有 `ToolMessage`，产生"工具调用有去无回"的幻觉，极可能陷入
死循环或错误收敛。

### 变更点

将 `ToolMessage` 追加逻辑移至 `try` 块内 `dispatch_tool` 成功返回后，
`except` 块仅处理 `ClarificationNeededError`：

```python
for tc in calls:
    tool_name = str(tc.get("name") or "")
    try:
        _tool_id, result = await dispatch_tool(
            tc, tools_map, state,
            gateway_context=_gateway_context,  # 阶段 A 一并修复
            loader=loader,
        )
        # ✅ 成功路径：追加 ToolMessage
        tool_msg = ToolMessage(
            content=str(result) if not isinstance(result, str) else result,
            tool_call_id=str(tc.get("id") or ""),
        )
        messages.append(tool_msg)
        logger.info("[tool_dispatcher] tool=%s done", tool_name)
    except ClarificationNeededError as exc:
        logger.info(
            "[tool_dispatcher] ClarificationNeededError tool=%s round=%s",
            tool_name, state.get("react_round_idx"),
        )
        return {
            "execution_status": "clarify_needed",
            "pending_clarification_context": {
                **exc.context,
                "tool_name": tool_name,
                "react_round_idx": int(state.get("react_round_idx") or 1) - 1,
            },
        }
```

### 涉及文件

- `src/datacloud_analysis/orchestration/execution/tool_dispatcher_node.py`

### 测试补充

1. 工具调用成功后，`react_messages_log` 中存在对应 `ToolMessage`。
2. `ClarificationNeededError` 时，返回 `clarify_needed` 状态，`react_messages_log` 不变。
3. 多工具顺序调用，每个工具结果均被正确追加。

### 验收标准

1. 工具执行成功后，下一轮 LLM 能在消息历史中看到 `ToolMessage`。
2. 回归所有 `tool_dispatcher_node` 相关单测全部通过。

---

## 阶段 P0-2（最高优先级）：修复 `llm_retry.py` 三处代码缺陷

### 问题根因

`stream_llm_call_with_retry` 存在三处缺陷，函数在任何调用场景下均会崩溃：

```python
# 缺陷 1：max_retries 被 min_wait 的值覆盖，min_wait 从未赋值
max_retries = _DEFAULT_MAX_RETRIES   # = 3
max_retries = _DEFAULT_MIN_WAIT      # ← 应为 min_wait = _DEFAULT_MIN_WAIT；max_retries 变为 1.0

# 缺陷 2：min_wait 从未定义 → NameError
wait = min(min_wait * (2**attempt), max_wait)

# 缺陷 3：函数缺少 async 关键字，内部却有 await → SyntaxError / RuntimeError
def stream_llm_call_with_retry(...):
    return await llm_call(...)
```

### 变更点

```python
async def stream_llm_call_with_retry(          # ← 补 async
    llm_call: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    max_retries = _DEFAULT_MAX_RETRIES         # = 3
    min_wait = _DEFAULT_MIN_WAIT               # ← 修正变量名
    max_wait = _DEFAULT_MAX_WAIT
    rate_limit_wait = _DEFAULT_RATE_LIMIT_WAIT
    ...
    wait = min(min_wait * (2**attempt), max_wait)   # ← min_wait 已正确赋值
```

### 涉及文件

- `src/datacloud_analysis/orchestration/execution/llm_retry.py`

### 测试补充

1. 主模型 5xx 错误 → 触发重试，最多 3 次，等待符合指数退避。
2. 429 限流 → 在指数退避基础上追加 `Retry-After` 等待。
3. 401/403 不可重试错误 → 立即抛出，不等待。
4. 重试耗尽 → 抛出原始异常。

### 验收标准

1. `stream_llm_call_with_retry` 可被正常 `await` 调用。
2. `max_retries`、`min_wait` 使用正确的模块级常量。
3. 单测覆盖可重试 / 不可重试 / 429 / 耗尽四条路径。

---

## 阶段 A（P1）：修复 `gateway_context` 透传一致性

### 变更点

1. 修改 `tool_dispatcher_node`，按与 `llm_call_node` 一致的优先级读取：
   - 优先 `config["configurable"]["gateway_context"]`
   - 次选闭包注入的 `gateway_context`
2. `dispatch_tool(...)` 调用改为传入解析后的 `_gateway_context`。
3. 确认 `tool_wrapper.dispatch_tool` 函数签名支持 `gateway_context` 参数；
   如签名缺失，需同步在 `tool_wrapper.py` 补充该参数。

### 涉及文件

- `src/datacloud_analysis/orchestration/execution/tool_dispatcher_node.py`
- `src/datacloud_analysis/orchestration/execution/tool_wrapper.py`（确认签名）

### 测试补充

1. 新增单测：`configurable.gateway_context` 存在时，`dispatch_tool` 接收到的是请求级上下文。
2. 回归现有 `tool_dispatcher_node` 相关单测。

### 验收标准

1. 同一轮请求在 `llm_call`、`per-tool node`、`tool_dispatcher` 里看到的 `gateway_context` 一致。
2. 相关单测全部通过。

---

## 阶段 B（P2）：将 checkpoint 从"可选降级"改为"可控 fail-fast"

### 变更点

1. 引入显式策略开关：
   - `DATACLOUD_REQUIRE_CHECKPOINTER=true` 时，未初始化 checkpointer 直接抛错；
   - `false` 时允许当前降级行为（用于本地调试 / 测试）。
2. **将 checkpointer 编译策略提取为公共函数**（如 `_compile_graph_with_policy(graph)`），
   在 `agent.py` 和 `runner.py` 两处共用，避免再次出现行为偏差。
3. 在启动日志中明确：生产环境必须先执行 `await bootstrap.setup()`。

### 涉及文件

- `src/datacloud_analysis/agent.py`
- `src/datacloud_analysis/orchestration/runner.py`
- `src/datacloud_analysis/bootstrap.py`（日志提示）

### 测试补充

1. `require_checkpointer=true` 且未初始化 → 抛出可识别错误。
2. `require_checkpointer=false` → 保留现有降级编译。
3. 已初始化 checkpointer → 正常编译且可 resume。

### 验收标准

1. 生产配置下无"静默失效"的 interrupt/resume。
2. `agent.py` 与 `runner.py` 共用同一编译策略，行为一致。
3. 配置策略行为与测试一致。

---

## 阶段 C（P2）：恢复可配置 fallback 模型能力

> ⚠️ **前置依赖**：必须先完成 **阶段 P0-2**（修复 `llm_retry.py`），
> 否则底层重试函数崩溃，fallback 路径无法正常工作。

### 变更点

1. 改造 `_build_fallback_llm()`：
   - 默认保持关闭（兼容现网）；
   - 显式配置（环境变量或 settings）开启时，从 `DATACLOUD_FALLBACK_LLM_*` 读取参数并构建 fallback 模型。
2. 保持现有主模型重试逻辑，在主模型重试耗尽后自动进入 fallback（已在 `_invoke_llm_with_fallback` 支持）。

### 涉及文件

- `src/datacloud_analysis/orchestration/execution/llm_retry.py`（P0-2 已修复后扩展）
- `src/datacloud_analysis/orchestration/execution/llm_call_node.py`
- `src/datacloud_analysis/orchestration/execution/react_loop.py`（回归验证）

### 测试补充

1. fallback 关闭：行为与当前一致。
2. fallback 开启：主模型失败后切换到 fallback 并成功返回。
3. 主备都失败：保留当前 checkpoint + 引导文案逻辑。

### 验收标准

1. fallback 开关可控。
2. 故障场景下成功率和可恢复性提升。

---

## 阶段 D（P3）：修复 `finish_react` 混合调用判定

### 变更点

将判定规则从"看 `calls[0]`"改为三路判断：

```python
# 当前（有歧义）
if not calls or calls[0].get("name") == "finish_react":
    return {"execution_status": "finish_react"}

# 修复后
non_finish = [tc for tc in calls if tc.get("name") != "finish_react"]
if not calls or not non_finish:
    return {"execution_status": "finish_react"}
# 混合场景：忽略混入的 finish_react，优先执行实际工具，下一轮再收敛结束
calls = non_finish
```

### 涉及文件

- `src/datacloud_analysis/orchestration/execution/tool_dispatcher_node.py`

### 测试补充

1. 混合 calls（`finish_react + query_xxx`）应执行 `query_xxx`。
2. 仅 `finish_react` 时应立即结束（保持现有行为）。
3. `calls` 为空时应立即结束。

### 验收标准

1. 混合 calls 行为稳定、可预期。
2. 不引入现有纯 `finish_react` 回归。

---

## 阶段 E（架构路线）：ReAct 与 LangGraph 生态对齐策略【暂不开发】

### 结论建议

1. **短期（当前版本）**：保留自研 StateGraph ReAct 主流程，先完成 P0 ~ D 的稳定性整改。
2. **中期（POC）**：新增实验分支评估 `langgraph.prebuilt.create_react_agent`，重点对比：
   - 中断恢复（interrupt/resume）支持
   - **澄清子流程（`ClarificationNeededError`）兼容性**（当前最重定制点，切换成本主要在此）
   - 工具并行执行
   - 可观测性、迁移成本
   - 输出 POC 对比报告后再决定是否切换主架构。

### 验收标准

1. 有明确 POC 数据结论，不做拍脑袋迁移。
2. 保持当前业务插件能力不回退。

---

## 4. 推荐实施顺序

| 顺序 | 阶段 | 优先级 | 说明 |
|------|------|--------|------|
| 1 | P0-1：ToolMessage 死代码 | P0 | 功能正确性，必须最先修 |
| 2 | P0-2：llm_retry 三处缺陷 | P0 | 阶段 C 的前置依赖 |
| 3 | 阶段 A：gateway_context 透传 | P1 | 可与 P0-1 合并 PR |
| 4 | 阶段 D：finish_react 判定 | P3 | 低成本高收益，提前实施 |
| 5 | 阶段 B：checkpoint fail-fast | P2 | 需提取公共编译函数 |
| 6 | 阶段 C：fallback 开关 | P2 | 依赖 P0-2 完成 |
| 7 | 阶段 E：生态对齐 POC【暂不开发】 | — | 稳定后启动 |

---

## 5. 回归验证清单

在 `packages/datacloud-analysis` 目录执行：

```bash
uv run ruff format .
uv run ruff check .
uv run mypy .
uv run pytest
```

增量验证（优先跑受影响模块）：

```bash
uv run pytest tests/dca/unit/test_tool_dispatcher_node.py
uv run pytest tests/dca/unit/test_llm_retry.py
uv run pytest tests/dca/unit/test_llm_call_node.py
uv run pytest tests/dca/unit/test_react_loop_state_resume.py
```

---

## 6. 风险与回滚

1. **P0-1**：ToolMessage 追加位置调整属于功能修复，无额外风险；需确保 `ClarificationNeededError` 路径回归不受影响。
2. **P0-2**：`llm_retry.py` 修复为纯 bug fix，逻辑不变；修复后需全量 LLM 调用路径回归。
3. **阶段 B**：`require_checkpointer` 切换为 fail-fast 后，未完成初始化的调用链会直接失败。回滚策略：通过配置关闭 `DATACLOUD_REQUIRE_CHECKPOINTER`。
4. **阶段 C**：fallback 启用后可能带来模型行为差异（输出风格、tool_call 稳定性）。回滚策略：通过配置关闭 fallback；保留旧逻辑分支一版，出现生产异常可快速回退。

---

## 7. v1.0 → v1.1 变更说明

| 变更项 | v1.0 | v1.1 |
|--------|------|------|
| 新增 P0-1 | 未提及 | 识别 `tool_dispatcher_node` ToolMessage 死代码，提升为 P0 |
| 新增 P0-2 | 未提及 | 识别 `llm_retry.py` 三处缺陷（async 缺失、变量覆盖、NameError），提升为 P0 |
| 阶段 A 补充 | 未提及 `tool_wrapper.py` | 明确需确认 `dispatch_tool` 签名，必要时同步修改 |
| 阶段 B 补充 | 两处编译路径各自修改 | 提取公共函数统一策略，避免再次行为偏差 |
| 阶段 C 依赖声明 | 无前置依赖说明 | 明确依赖 P0-2 先完成 |
| 阶段 E 评估项 | 未含澄清子流程 | 补充 `ClarificationNeededError` 兼容性为核心评估项 |
| 实施顺序 | A → D → B → C → E | P0-1 → P0-2 → A → D → B → C → E |
