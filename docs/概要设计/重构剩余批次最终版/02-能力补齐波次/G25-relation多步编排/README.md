# G25 relation 多步编排

## 1. 任务定义

### 1.1 背景（§3.4.5）

重构方案 §3.4.5 要求 `relation` 语义类型支持「先主语/宾语再查询」的完整多步编排：

1. **第一步**：定位主语（subject）和宾语（object）的实体 ID
2. **第二步**：以第一步的结果作为参数，执行关系查询

**当前实现（execution.py:372-379）：**

```python
if "relation" in semantic_types:
    if any(k in lowered for k in _RELATION_KEYWORDS):
        score -= 50  # 提升关系工具优先级
    elif any(k in lowered for k in _QUERY_KEYWORDS):
        score -= 18  # 适度提升查询工具
    elif any(k in lowered for k in _ACTION_KEYWORDS):
        score += 12  # 降低动作工具优先级
```

**差距：** 当前只做工具优先级调整，**没有自动拆分为两步 todo** 的编排逻辑。

### 1.2 目标

1. 当 planning 节点识别到 `relation` 语义类型的 todo 时，自动拆分为两步：
   - `todo_1`：定位主语/宾语实体（`required_tools: ["search_knowledge"]`）
   - `todo_2`：执行关系查询（`depends_on: ["todo_1"]`，参数引用 `todo_1` 的结果）
2. 在 execution 节点中，支持从依赖 todo 的结果中提取参数（结果参数注入）。
3. 若 planning 已经拆分了两步（用户明确描述了两步），则不重复拆分。

---

## 2. 详细任务

### 2.1 planning 节点：relation 语义自动拆分

在 `planning/decomposer.py`（G21 重组后路径）中，添加 `relation` 语义检测与拆分逻辑：

```python
def _should_split_relation_todo(todo: dict[str, Any]) -> bool:
    """判断 todo 是否需要拆分为主语/宾语定位 + 关系查询两步。"""
    semantic_types = todo.get("term_context", {}).get("semantic_types", [])
    if "relation" not in semantic_types:
        return False
    # 若已有 depends_on，说明已经是多步编排的一部分，不重复拆分
    if todo.get("depends_on"):
        return False
    return True


def split_relation_todo(todo: dict[str, Any]) -> list[dict[str, Any]]:
    """将 relation todo 拆分为两步：实体定位 + 关系查询。"""
    todo_id = todo.get("todo_id", "t_rel")
    locate_todo = {
        "todo_id": f"{todo_id}_locate",
        "goal": f"定位「{todo.get('goal', '')}」中的主语和宾语实体",
        "required_tools": ["search_knowledge"],
        "term_context": todo.get("term_context", {}),
        "depends_on": [],
    }
    query_todo = {
        "todo_id": f"{todo_id}_query",
        "goal": todo.get("goal", ""),
        "required_tools": todo.get("required_tools", []),
        "term_context": todo.get("term_context", {}),
        "depends_on": [f"{todo_id}_locate"],
        "param_from_deps": {f"{todo_id}_locate": ["subject_id", "object_id"]},
    }
    return [locate_todo, query_todo]
```

### 2.2 execution 节点：结果参数注入

在 `execution/node.py` 中，支持从依赖 todo 的结果中提取参数（`param_from_deps`）：

```python
def _inject_params_from_deps(
    todo: dict[str, Any],
    completed_todos: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """将依赖 todo 的结果注入当前 todo 的参数。"""
    param_from_deps = todo.get("param_from_deps") or {}
    if not param_from_deps:
        return todo

    injected_params = {}
    for dep_id, fields in param_from_deps.items():
        dep_result = (completed_todos.get(dep_id) or {}).get("output") or {}
        for field in fields:
            if field in dep_result:
                injected_params[field] = dep_result[field]

    if injected_params:
        existing_params = todo.get("tool_params") or
        return {**todo, "tool_params": {**existing_params, **injected_params}}
    return todo
```

在执行 todo 前调用：

```python
active_todo = _inject_params_from_deps(active_todo, completed_todos_map)
```

### 2.3 planning 节点集成

在 `planning/node.py` 的 todo 生成后，对每个 todo 检查是否需要拆分：

```python
expanded_todos = []
for todo in raw_todos:
    if _should_split_relation_todo(todo):
        expanded_todos.extend(split_relation_todo(todo))
    else:
        expanded_todos.append(todo)
todos = expanded_todos
```

### 2.4 单元测试

新增 `tests/dca/unit/test_relation_multistep.py`：

```python
def test_split_relation_todo_generates_two_steps():
    """relation 语义 todo 被拆分为 locate + query 两步。"""
    ...

def test_split_relation_todo_skips_if_already_has_deps():
    """已有 depends_on 的 todo 不重复拆分。"""
    ...

def test_inject_params_from_deps_fills_subject_object():
    """依赖 todo 的 subject_id/object_id 被注入到关系查询 todo。"""
    ...

def test_inject_params_from_deps_noop_if_no_param_from_deps():
    """无 param_from_deps 时，todo 不变。"""
    ...
```

---

## 3. 验收标准

| # | 验收项 | 检查方式 |
|---|--------|---------|
| 1 | `_should_split_relation_todo` 函数存在 | 代码审查 |
| 2 | `split_relation_todo` 生成正确的两步 todo | 单元测试覆盖 |
| 3 | 已有 `depends_on` 的 todo 不重复拆分 | 单元测试覆盖 |
| 4 | `_inject_params_from_deps` 正确注入参数 | 单元测试覆盖 |
| 5 | planning 节点集成拆分逻辑 | 代码审查 |
| 6 | 新增单元测试通过 | `pytest tests/dca/unit/test_relation_multistep.py` 绿色 |
| 7 | 全量单测通过 | `pytest packages/datacloud-analysis/tests/` 绿色 |

---

## 4. 依赖

**前置**：01-收口前置波次完成（G21 目录重组后路径稳定）。

## 5. 并行性

可与 G22、G23、G24 并行执行。

## 6. 风险提示

- `param_from_deps` 字段是新增字段，需确认 `AgentState` 中的 todo 结构支持该字段（或作为 todo 的 extra 字段透传）。
- 拆分逻辑在 planning 节点执行，若 planning 已经生成了多步 todo（LLM 自行拆分），需避免重复拆分（通过 `depends_on` 检查）。
- `split_relation_todo` 生成的 `todo_id` 需保证唯一性，避免与其他 todo 冲突。

## 7. 提交规范

```
refactor(g25): implement relation semantic multi-step orchestration (locate + query)
```
