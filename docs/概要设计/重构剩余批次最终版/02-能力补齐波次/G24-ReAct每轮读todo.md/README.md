# G24 ReAct 每轮读 todo.md

## 1. 任务定义

### 1.1 背景（§3.4.2）

重构方案 §3.4.2 要求单 todo 的「完整 ReAct」循环：
- **每轮开始时**，LLM 读取当前 `todo.md` 摘要作为上下文（了解整体进度）
- LLM 根据 `todo.md` 内容和当前 todo 的 observe 结果，决定是否修改参数（LLM 改参）
- observe 闭环：工具执行结果作为 observe 输入下一轮

**当前实现：**
- `todo.md` 在每批次执行后写入（`execution.py:1071-1075`），路径为 `{workspace_dir}/temp/todo.md`
- `react_runtime.py` 的 `select_react_capability()` 只做能力选择，**不读取 `todo.md`**
- `_execute_one_todo()` 的 ReAct 循环（`execution.py:667-758`）**不将 `todo.md` 内容注入 LLM 上下文**
- LLM 改参逻辑（根据 observe 结果修改工具参数）**未实现**

### 1.2 目标

1. 在 ReAct 每轮开始时，读取 `todo.md` 并注入 LLM 上下文。
2. 实现 LLM 改参：observe 结果作为输入，LLM 可修改下一轮的工具参数。
3. observe 闭环：工具执行结果（output）作为 observe 传入下一轮 `select_react_capability`。

---

## 2. 详细任务

### 2.1 todo.md 注入 LLM 上下文

在 `react_runtime.py` 的 `select_react_capability()` 中，添加 `todo_md_summary` 参数：

```python
async def select_react_capability(
    todo: dict[str, Any],
    candidates: list[str],
    state: Mapping[str, Any],
    todo_md_summary: str | None = None,   # 新增：当前 todo.md 内容摘要
    observe: str | None = None,            # 新增：上一轮工具执行结果
    ...
) -> ReactSelection:
    ...
```

在 system prompt 中注入 `todo_md_summary`：

```python
system_parts = [BASE_SYSTEM_PROMPT]
if todo_md_summary:
    system_parts.append(f"\n## 当前任务进度\n{todo_md_summary}")
if observe:
    system_parts.append(f"\n## 上一轮执行结果\n{observe}")
```

### 2.2 execution/node.py 中读取 todo.md

在 `_execute_one_todo()` 的 ReAct 循环中，每轮开始时读取 `todo.md`：

```python
async def _read_todo_md(workspace_dir: str | None) -> str | None:
    """读取 todo.md 内容，失败时静默返回 None。"""
    if not workspace_dir:
        return None
    todo_path = pathlib.Path(workspace_dir) / "temp" / "todo.md"
    try:
        return todo_path.read_text(encoding="utf-8")
    except OSError:
        return None
```

在 ReAct 循环中调用：

```python
for react_round in range(max_rounds):
    todo_md = await _read_todo_md(workspace_dir)
    observe_text = _format_observe(last_output) if last_output else None

    selection = await select_react_capability(
        todo=active_todo,
        candidates=remaining_capabilities,
        state=state,
        todo_md_summary=todo_md,
        observe=observe_text,
    )
    ...
    last_output = output  # 保存本轮输出作为下一轮 observe
```

### 2.3 LLM 改参（observe 闭环）

扩展 `ReactSelection` 以支持 LLM 修改工具参数：

```python
class ReactSelection(TypedDict):
    capability_id: str
    source: str
    reason: str
    tool_call_id: str
    param_overrides: dict[str, Any]   # 新增：LLM 建议的参数修改
```

在 `_execute_one_todo()` 中，将 `param_overrides` 合并到 todo 参数：

```python
if selection.get("param_overrides"):
    active_todo = {**active_todo, **selection["param_overrides"]}
```

### 2.4 单元测试

新增 `tests/dca/unit/test_react_todo_md_injection.py`：

```python
@pytest.mark.asyncio
async def test_select_react_capability_injects_todo_md():
    """todo_md_summary 被注入 LLM system prompt。"""
    ...

@pytest.mark.asyncio
async def test_select_react_capability_injects_observe():
    """上一轮 observe 结果被注入 LLM 上下文。"""
    ...

@pytest.mark.asyncio
async def test_react_loop_reads_todo_md_each_round():
    """ReAct 循环每轮读取 todo.md，失败时不中断执行。"""
    ...

@pytest.mark.asyncio
async def test_param_overrides_applied_to_next_round():
    """LLM 返回 param_overrides 时，下一轮工具调用使用修改后的参数。"""
    ...
```

---

## 3. 验收标准

| # | 验收项 | 检查方式 |
|---|--------|---------|
| 1 | `select_react_capability` 接受 `todo_md_summary` 和 `observe` 参数 | 函数签名检查 |
| 2 | ReAct 循环每轮读取 `todo.md` | 代码审查 + 单元测试 |
| 3 | `todo.md` 读取失败时不中断执行（静默降级） | 单元测试覆盖 |
| 4 | `ReactSelection` 含 `param_overrides` 字段 | 类型定义检查 |
| 5 | `param_overrides` 被应用到下一轮工具调用 | 单元测试覆盖 |
| 6 | 新增单元测试通过 | `pytest tests/dca/unit/test_react_todo_md_injection.py` 绿色 |
| 7 | 全量单测通过 | `pytest packages/datacloud-analysis/tests/` 绿色 |

---

## 4. 依赖

**前置**：01-收口前置波次完成（G21 目录重组后路径稳定）。

## 5. 并行性

可与 G22、G23、G25 并行执行。

## 6. 风险提示

- `todo.md` 读取为 IO 操作，需确保异步安全（使用 `anyio.Path` 或 `asyncio.to_thread`）。
- `todo.md` 内容可能较长，注入 LLM 时建议截断到合理长度（如 2000 字符）。
- `param_overrides` 的合并策略需明确：浅合并还是深合并，避免覆盖关键字段（如 `todo_id`）。

## 7. 提交规范

```
refactor(g24): inject todo.md summary and observe into ReAct each round
```
