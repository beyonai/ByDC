# Bug 修复报告

## 修复时间
2026-04-06

## 问题描述

运行时报错：
```
AttributeError: 'Runtime' object has no attribute 'state'. Did you mean: 'store'?
```

错误发生在 `knowledge_injection.py:43`：
```python
state = request.runtime.state
```

## 根因分析

### 1. ModelRequest 的 runtime 属性

查看 `langchain.agents.middleware.types.ModelRequest` 定义：

```python
@dataclass(init=False)
class ModelRequest(Generic[ContextT]):
    model: BaseChatModel
    messages: list[AnyMessage]
    system_message: SystemMessage | None
    tool_choice: Any | None
    tools: list[BaseTool | dict[str, Any]]
    response_format: ResponseFormat[Any] | None
    state: AgentState[Any]  # ✅ state 是 ModelRequest 的直接属性
    runtime: Runtime[ContextT]  # ✅ runtime 是 Runtime 类型
    model_settings: dict[str, Any] = field(default_factory=dict)
```

### 2. Runtime 类的定义

查看 `langgraph.runtime.Runtime` 定义：

```python
@dataclass(**_DC_KWARGS)
class Runtime(Generic[ContextT]):
    context: ContextT = field(default=None)
    store: BaseStore | None = field(default=None)
    stream_writer: StreamWriter = field(default=_no_op_stream_writer)
    previous: Any = field(default=None)
    # ❌ 没有 state 属性
```

**结论**: `Runtime` 类只有 `context`、`store`、`stream_writer`、`previous` 属性，**没有 `state` 属性**。

### 3. 正确的访问方式

查看其他中间件的实现（如 `deepagents.middleware.patch_tool_calls`）：

```python
class PatchToolCallsMiddleware(AgentMiddleware):
    def before_agent(self, state: AgentState, runtime: Runtime[Any]) -> dict[str, Any] | None:
        messages = state["messages"]  # ✅ 直接使用 state 参数
        # ...
```

查看 `langchain.agents.middleware.types` 中的示例：

```python
@dynamic_prompt
def context_aware_prompt(request: ModelRequest) -> str:
    msg_count = len(request.state["messages"])  # ✅ 使用 request.state
    # ...
```

**结论**: 应该使用 `request.state` 而不是 `request.runtime.state`。

### 4. ToolCallRequest 的 runtime 属性

查看 `langgraph.prebuilt.tool_node.ToolCallRequest` 定义：

```python
class ToolCallRequest:
    tool_call: ToolCall
    tool: BaseTool | None
    state: Any
    runtime: ToolRuntime  # ✅ runtime 是 ToolRuntime 类型
```

查看 `langgraph.prebuilt.tool_node.ToolRuntime` 定义：

```python
class ToolRuntime(_DirectlyInjectedToolArg, Generic[ContextT, StateT]):
    state: StateT
    context: ContextT
    config: RunnableConfig  # ✅ 有 config 属性
    stream_writer: StreamWriter
    tool_call_id: str | None
    store: BaseStore | None
```

**结论**: `ToolRuntime` 有 `config` 属性，所以 `request.runtime.config` 是正确的。

## 修复方案

### 修复 1: knowledge_injection.py

**错误代码**:
```python
state = request.runtime.state  # ❌ Runtime 没有 state 属性
```

**修复后**:
```python
state = request.state  # ✅ 直接使用 request.state
```

**修改位置**:
- `src/datacloud_analysis/middlewares/knowledge_injection.py:43`
- `src/datacloud_analysis/middlewares/knowledge_injection.py:93`

### 修复 2: tool_logging.py（无需修改）

**现有代码**:
```python
return request.runtime.config.get("configurable", {}).get("gateway_context")
```

**分析**: 这是正确的，因为：
- `ToolCallRequest.runtime` 是 `ToolRuntime` 类型
- `ToolRuntime` 有 `config` 属性
- ✅ 无需修改

## 修复验证

### 1. 代码检查

```bash
grep -rn "request\.runtime\." src/datacloud_analysis/middlewares/ --include="*.py"
```

结果：
```
src/datacloud_analysis/middlewares/knowledge_injection.py:42:        # 去重检查：使用 request.state（而不是 request.runtime.state）
src/datacloud_analysis/middlewares/tool_logging.py:131:            return request.runtime.config.get("configurable", {}).get("gateway_context")
```

✅ 只有 `tool_logging.py` 使用 `request.runtime.config`，这是正确的。

### 2. 测试验证

运行核心逻辑测试：
```bash
python -m pytest tests/test_agent/test_stage4_core_logic.py -v
```

结果：
```
9 passed, 4 warnings in 0.03 seconds
```

✅ 所有测试通过。

## 总结

### 修复内容

1. ✅ 修复 `knowledge_injection.py` 中的 `request.runtime.state` → `request.state`（2处）
2. ✅ 确认 `tool_logging.py` 中的 `request.runtime.config` 是正确的

### 根本原因

- `ModelRequest.runtime` 是 `Runtime` 类型，没有 `state` 属性
- `ModelRequest.state` 是直接属性，应该直接访问
- `ToolCallRequest.runtime` 是 `ToolRuntime` 类型，有 `config` 属性

### 影响范围

- ✅ 修复后，知识注入中间件可以正常访问 state
- ✅ 工具调用日志中间件可以正常访问 gateway_context
- ✅ 所有核心逻辑测试通过

### 后续建议

1. 在完整环境中运行集成测试，验证修复效果
2. 更新测试用例，覆盖 `request.state` 的访问场景
3. 添加类型检查，避免类似错误
