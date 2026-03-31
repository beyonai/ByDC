# G21 orchestration 目录重组

## 1. 任务定义

### 1.1 背景

当前 `orchestration/` 目录下所有文件平铺，G18 完成后剩余 17 个文件。按重构方案要求，应**一个节点一个文件夹**，节点私有文件放在节点文件夹内，公共文件放到公共文件夹。

### 1.2 G18 完成后的文件清单（17 个）

```
orchestration/
├── __init__.py
├── graph_builder.py          # 图装配
├── state.py                  # AgentState
├── runner.py                 # 调试辅助
├── query_shape_utils.py      # 公共工具函数
├── knowledge_enhance.py      # 知识增强节点
├── planning.py               # 规划节点
├── planner_contract.py       # 规划节点私有：接口契约
├── planner_facade.py         # 规划节点私有：上下文解析
├── planning_decomposer.py    # 规划节点私有：任务拆解
├── execution.py              # 执行节点
├── react_runtime.py          # 执行节点私有：ReAct 能力选择
├── sandbox_executor.py       # 执行节点私有：工具执行沙箱
├── execution_summary.py      # 结束节点私有：执行摘要模型
├── summary_persistence.py    # 结束节点私有：摘要持久化接口
└── insight.py                # 结束节点
```

### 1.3 目标目录结构

```
orchestration/
├── __init__.py
├── graph_builder.py          # 顶层公共（不移动）
├── state.py                  # 顶层公共（不移动）
├── runner.py                 # 顶层公共（不移动）
├── shared/                   # 公共工具
│   ├── __init__.py
│   └── query_shape_utils.py
├── knowledge_enhance/        # 知识增强节点
│   ├── __init__.py
│   └── node.py               # 原 knowledge_enhance.py
├── planning/                 # 规划节点
│   ├── __init__.py
│   ├── node.py               # 原 planning.py
│   ├── contract.py           # 原 planner_contract.py
│   ├── facade.py             # 原 planner_facade.py
│   └── decomposer.py         # 原 planning_decomposer.py
├── execution/                # 执行节点
│   ├── __init__.py
│   ├── node.py               # 原 execution.py
│   ├── react_runtime.py      # 原 react_runtime.py
│   └── sandbox_executor.py   # 原 sandbox_executor.py
└── end/                      # 结束节点
    ├── __init__.py
    ├── node.py               # 原 insight.py
    ├── execution_summary.py  # 原 execution_summary.py
    └── summary_persistence.py # 原 summary_persistence.py
```

---

## 2. 详细任务

### 2.1 文件迁移映射

| 原路径 | 新路径 |
|--------|--------|
| `orchestration/query_shape_utils.py` | `orchestration/shared/query_shape_utils.py` |
| `orchestration/knowledge_enhance.py` | `orchestration/knowledge_enhance/node.py` |
| `orchestration/planning.py` | `orchestration/planning/node.py` |
| `orchestration/planner_contract.py` | `orchestration/planning/contract.py` |
| `orchestration/planner_facade.py` | `orchestration/planning/facade.py` |
| `orchestration/planning_decomposer.py` | `orchestration/planning/decomposer.py` |
| `orchestration/execution.py` | `orchestration/execution/node.py` |
| `orchestration/react_runtime.py` | `orchestration/execution/react_runtime.py` |
| `orchestration/sandbox_executor.py` | `orchestration/execution/sandbox_executor.py` |
| `orchestration/insight.py` | `orchestration/end/node.py` |
| `orchestration/execution_summary.py` | `orchestration/end/execution_summary.py` |
| `orchestration/summary_persistence.py` | `orchestration/end/summary_persistence.py` |

**保持原位（不移动）：**
- `orchestration/__init__.py`
- `orchestration/graph_builder.py`
- `orchestration/state.py`
- `orchestration/runner.py`

### 2.2 各子包 __init__.py 导出规范

每个节点子包的 `__init__.py` 导出节点主函数，保持对外接口稳定：

**`knowledge_enhance/__init__.py`：**
```python
from datacloud_analysis.orchestration.knowledge_enhance.node import knowledge_enhance_node

__all__ = ["knowledge_enhance_node"]
```

**`planning/__init__.py`：**
```python
from datacloud_analysis.orchestration.planning.node import planning_node

__all__ = ["planning_node"]
```

**`execution/__init__.py`：**
```python
from datacloud_analysis.orchestration.execution.node import execution_node

__all__ = ["execution_node"]
```

**`end/__init__.py`：**
```python
from datacloud_analysis.orchestration.end.node import insight_node

__all__ = ["insight_node"]
```

**`shared/__init__.py`：**
```python
from datacloud_analysis.orchestration.shared.query_shape_utils import (
    QueryShape,
    detect_query_shape,
)

__all__ = ["QueryShape", "detect_query_shape"]
```

### 2.3 节点内部 import 路径更新

迁移后，节点内部的相互引用需更新：

**`planning/node.py` 内部 import：**
```python
# 旧
from datacloud_analysis.orchestration.planner_contract import PlanningContext
from datacloud_analysis.orchestration.planner_facade import resolve_planning_context
from datacloud_analysis.orchestration.planning_decomposer import decompose_plan

# 新
from datacloud_analysis.orchestration.planning.contract import PlanningContext
from datacloud_analysis.orchestration.planning.facade import resolve_planning_context
from datacloud_analysis.orchestration.planning.decomposer import decompose_plan
```

**`execution/node.py` 内部 import：**
```python
# 旧
from datacloud_analysis.orchestration.react_runtime import select_react_capability
from datacloud_analysis.orchestration.sandbox_executor import execute_next_task, ...

# 新
from datacloud_analysis.orchestration.execution.react_runtime import select_react_capability
from datacloud_analysis.orchestration.execution.sandbox_executor import execute_next_task, ...
```

**`end/node.py` 内部 import：**
```python
# 旧
from datacloud_analysis.orchestration.execution_summary import build_execution_summary, ...
from datacloud_analysis.orchestration.summary_persistence import ExecutionSummaryStore

# 新
from datacloud_analysis.orchestration.end.execution_summary import build_execution_summary, ...
from datacloud_analysis.orchestration.end.summary_persistence import ExecutionSummaryStore
```

### 2.4 graph_builder.py 的 import

`graph_builder.py` 通过子包 `__init__` 导出，**import 路径可以不变**：

```python
# 这些 import 在重组后仍然有效（通过子包 __init__ 导出）
from datacloud_analysis.orchestration.execution import execution_node
from datacloud_analysis.orchestration.insight import insight_node  # 需更新为 end
from datacloud_analysis.orchestration.knowledge_enhance import knowledge_enhance_node
from datacloud_analysis.orchestration.planning import planning_node
```

注意：`insight_node` 原来在 `orchestration.insight`，迁移后在 `orchestration.end`，需更新 `graph_builder.py` 中的 import：

```python
# 旧
from datacloud_analysis.orchestration.insight import insight_node

# 新
from datacloud_analysis.orchestration.end import insight_node
```

### 2.5 扫描并更新测试中的 import 路径

```bash
grep -rn "from datacloud_analysis.orchestration\." \
  packages/datacloud-analysis/tests/ --include="*.py" | grep -v "__pycache__"
```

逐一更新为新路径（或通过子包 `__init__` 导出保持兼容）。

---

## 3. 验收标准

| # | 验收项 | 检查方式 |
|---|--------|---------|
| 1 | 目录结构符合规范 | `ls orchestration/` 含 shared/knowledge_enhance/planning/execution/end 子目录 |
| 2 | 旧平铺文件已移动 | `ls orchestration/*.py` 只剩 `__init__.py graph_builder.py state.py runner.py` |
| 3 | 各子包 `__init__.py` 正确导出 | `python -c "from datacloud_analysis.orchestration.execution import execution_node"` 无报错 |
| 4 | `graph_builder.py` import 正常 | `python -c "from datacloud_analysis.orchestration.graph_builder import build_analysis_graph"` 无报错 |
| 5 | 无循环 import | `python -c "import datacloud_analysis.orchestration"` 无报错 |
| 6 | 全量单测通过 | `pytest packages/datacloud-analysis/tests/` 绿色 |

---

## 4. 依赖

**前置**：G18 完成（旧节点文件已删除，避免迁移时混入旧文件）。

## 5. 并行性

G18 完成后，可与 G19 并行执行。

## 6. 风险提示

- 建议先创建新目录和文件，验证 import 正常后再删除旧文件，避免中间状态破坏 CI。
- 若有外部包直接 import 旧路径（如 `from datacloud_analysis.orchestration.sandbox_executor import ...`），需同步更新或在顶层 `__init__.py` 添加兼容导出。
- 注意 `insight_node` 的模块路径从 `orchestration.insight` 变为 `orchestration.end`，`graph_builder.py` 必须更新。

## 7. 提交规范

```
refactor(g21): reorganize orchestration directory into per-node subdirectories
```
