# G18 旧节点代码下线

## 1. 任务定义

### 1.1 背景

5 节点主链路（knowledge_enhance → planning → execution → end）已完全落地，但以下旧节点仍以"兼容层"方式被主链路引用，且 6 个旧节点文件仍存在于 orchestration 目录。

**仍有引用的旧节点：**

| 旧节点 | 被引用位置 | 引用方式 |
|--------|-----------|---------|
| `clarification.py` | `execution.py:17,849` | `clarification_node` 处理 `ambiguous_terms` 中断 |
| `intent.py` | `planner_facade.py:65` | `intent_node` 作为 `intent_compat` 兼容层 |

**无引用但未删除的旧节点：**

| 文件 | 已被替代为 |
|------|-----------|
| `dag.py` | `planning.py` + `planning_decomposer.py` |
| `loop.py` | `react_runtime.py` + `execution.py` 内 ReAct 循环 |
| `agent_delegate.py` | `execution.py` 内 `agent_delegate` todo 处理 |
| `direct_tool.py` | `execution.py` 内单 todo 执行路径 |

### 1.2 目标

1. 移除 `execution.py` 对 `clarification_node` 的引用，将澄清中断逻辑内联。
2. 移除 `planner_facade.py` 的 `intent_compat` 兼容层。
3. 删除 6 个旧节点文件。
4. 添加静态防回归检查，防止旧节点被重新引入。

---

## 2. 详细任务

### 2.1 内联 clarification_node（execution.py）

**当前代码（execution.py:840-870 附近）：**

```python
from datacloud_analysis.orchestration.clarification import clarification_node
...
if state.get("ambiguous_terms"):
    updates = await clarification_node(state, gateway_context=gateway_context)
    if updates.get("ambiguous_terms"):
        return {
            **updates,
            "execution_status": "done",
            ...
        }
```

**目标：** 将 `clarification_node` 的核心逻辑内联为 `execution.py` 的私有函数 `_build_clarification_interrupt(state, gateway_context) -> dict`。

内联时需保留的关键行为：
- 向用户发出澄清提示（构造 `messages` 中的 AI 消息）
- 调用 `save_clarification_results`（来自 `datacloud_analysis.tools.knowledge`）持久化确权结果
- 返回包含 `ambiguous_terms`、`execution_status="done"`、`resume_context` 的 state 更新

删除：`from datacloud_analysis.orchestration.clarification import clarification_node`

### 2.2 移除 intent_compat 兼容层（planner_facade.py）

**当前代码（planner_facade.py:55-90 附近）：**

```python
_INTENT_COMPAT_ENV = "DATACLOUD_PLANNING_INTENT_COMPAT"

def _is_intent_compat_enabled() -> bool: ...
def _needs_intent_compat(ctx) -> bool: ...

async def resolve_planning_context(...):
    ctx = _context_from_state(state, query_input)
    if not _needs_intent_compat(ctx):
        return ctx
    if not _is_intent_compat_enabled():
        return ctx
    from datacloud_analysis.orchestration.intent import intent_node
    intent_updates = await intent_node(...)
    return { ..., "planning_context_source": "intent_compat" }
```

**目标：**
- 删除 `_is_intent_compat_enabled`、`_needs_intent_compat` 函数
- 删除 `intent_node` 动态 import 及其调用分支
- `resolve_planning_context` 直接返回 `_context_from_state(state, query_input)`
- 若有测试依赖 `planning_context_source == "intent_compat"`，一并更新

### 2.3 删除旧节点文件

确认无引用后删除：

```
packages/datacloud-analysis/src/datacloud_analysis/orchestration/intent.py
packages/datacloud-analysis/src/datacloud_analysis/orchestration/dag.py
packages/datacloud-analysis/src/datacloud_analysis/orchestration/clarification.py
packages/datacloud-analysis/src/datacloud_analysis/orchestration/loop.py
packages/datacloud-analysis/src/datacloud_analysis/orchestration/agent_delegate.py
packages/datacloud-analysis/src/datacloud_analysis/orchestration/direct_tool.py
```

删除前执行确认命令：

```bash
grep -rn \
  "from datacloud_analysis.orchestration.intent\|from datacloud_analysis.orchestration.dag\|from datacloud_analysis.orchestration.clarification\|from datacloud_analysis.orchestration.loop\|from datacloud_analysis.orchestration.agent_delegate\|from datacloud_analysis.orchestration.direct_tool" \
  . --include="*.py" | grep -v "__pycache__"
```

预期输出：**空**。

### 2.4 添加静态防回归测试

新增 `tests/dca/unit/test_no_legacy_node_imports.py`：

```python
"""静态检查：确保旧节点不被重新引入主链路。"""
import ast
import pathlib

LEGACY_MODULES = {
    "datacloud_analysis.orchestration.intent",
    "datacloud_analysis.orchestration.dag",
    "datacloud_analysis.orchestration.clarification",
    "datacloud_analysis.orchestration.loop",
    "datacloud_analysis.orchestration.agent_delegate",
    "datacloud_analysis.orchestration.direct_tool",
}

SRC_ROOT = pathlib.Path(__file__).parents[4] / "src"


def _collect_imports(path: pathlib.Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def test_no_legacy_orchestration_imports():
    violations = []
    for py_file in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        for imp in _collect_imports(py_file):
            if imp in LEGACY_MODULES:
                violations.append(f"{py_file.relative_to(SRC_ROOT)}: imports {imp}")
    assert not violations, "旧节点被重新引入：\n" + "\n".join(violations)
```

---

## 3. 验收标准

| # | 验收项 | 检查方式 |
|---|--------|---------|
| 1 | `execution.py` 不再 import `clarification_node` | `grep "clarification" execution.py` 无结果 |
| 2 | `planner_facade.py` 不再 import `intent_node` | `grep "intent_node" planner_facade.py` 无结果 |
| 3 | 6 个旧节点文件已删除 | `ls orchestration/*.py` 不含旧文件名 |
| 4 | 全量 grep 无旧节点引用 | 见 2.3 命令，输出为空 |
| 5 | 静态防回归测试通过 | `pytest tests/dca/unit/test_no_legacy_node_imports.py` 绿色 |
| 6 | `ambiguous_terms` 中断路径仍可触发 | 集成测试或手动验证澄清场景 |
| 7 | 全量单测通过 | `pytest packages/datacloud-analysis/tests/` 绿色 |

---

## 4. 依赖

无前置批次依赖（G01~G17 已完成）。

## 5. 并行性

本任务先行，G19 和 G21 依赖本任务完成后才可执行。

## 6. 风险提示

- `clarification_node` 内联时，注意保留 `save_clarification_results` 调用，否则术语确权结果不会持久化。
- `intent_compat` 移除后，若有外部调用方依赖 `planning_context_source == "intent_compat"` 字段，需同步更新。
- 删除文件前务必执行 grep 检查，避免遗漏动态 import（如 `importlib.import_module`）。

## 7. 提交规范

```
refactor(g18): remove legacy orchestration nodes (intent/dag/clarification/loop/agent_delegate/direct_tool)
```
