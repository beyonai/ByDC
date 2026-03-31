# G19 旧测试与文档清理

## 1. 任务定义

### 1.1 背景

G18 完成后，旧节点文件已删除。本任务清理测试和文档中的旧节点残留，确认防回归测试通过。

### 1.2 当前状态（截至 2026-03-31）

经检查，测试目录中**无直接 import 旧节点**的测试文件。以下防回归断言已存在，需确认仍然通过：

| 测试文件 | 断言内容 | 状态 |
|---------|---------|------|
| `test_graph_builder_pipeline.py:15-16` | `"intent" not in node_names`、`"dag" not in node_names` | 需验证 |
| `test_readme_pipeline_alignment.py:22-23` | `"intent ->" not in content`、`"dag" not in content`、`"loop" not in content` | 需验证 |
| `test_no_legacy_node_imports.py`（G18 新增） | 全量静态 import 检查 | G18 新增后验证 |

### 1.3 目标

1. 确认并清理所有依赖旧节点文件的测试（若有）。
2. 确认 README 和设计文档无旧图流程描述。
3. 确认所有防回归测试通过。
4. 清理 `__pycache__` 中的旧节点编译缓存。

---

## 2. 详细任务

### 2.1 扫描测试目录

执行以下命令，确认无旧节点 import：

```bash
grep -rn \
  "from datacloud_analysis.orchestration.intent\|from datacloud_analysis.orchestration.dag\|from datacloud_analysis.orchestration.clarification\|from datacloud_analysis.orchestration.loop\|from datacloud_analysis.orchestration.agent_delegate\|from datacloud_analysis.orchestration.direct_tool" \
  packages/datacloud-analysis/tests/ --include="*.py" | grep -v "__pycache__"
```

预期输出：**空**。

若有输出：
- 专门测试旧节点功能的测试文件（如 `test_intent_node.py`）：**直接删除**
- 集成测试中顺带引用旧节点：**重写为使用新节点的等价测试**

### 2.2 文档检查

```bash
grep -rn "intent ->\|dag ->\|loop ->\|clarification ->" \
  docs/ packages/datacloud-analysis/README.md examples/e_commerce_demo/backend/README.md
```

预期输出：**空**。

若有旧流程描述，更新为新 5 节点链路：
```
knowledge_enhance → planning → execution → end
```

### 2.3 运行防回归测试

```bash
pytest packages/datacloud-analysis/tests/dca/unit/test_readme_pipeline_alignment.py -v
pytest packages/datacloud-analysis/tests/dca/unit/test_graph_builder_pipeline.py -v
pytest packages/datacloud-analysis/tests/dca/unit/test_no_legacy_node_imports.py -v
```

### 2.4 清理 __pycache__

```bash
find packages/datacloud-analysis/src/datacloud_analysis/orchestration/__pycache__ \
  \( -name "intent*" -o -name "dag*" -o -name "clarification*" \
     -o -name "loop*" -o -name "agent_delegate*" -o -name "direct_tool*" \) \
  -delete
```

---

## 3. 验收标准

| # | 验收项 | 检查方式 |
|---|--------|---------|
| 1 | 测试目录无旧节点 import | grep 命令输出为空 |
| 2 | README 无旧图流程描述 | grep 命令输出为空 |
| 3 | `test_readme_pipeline_alignment` 通过 | pytest 绿色 |
| 4 | `test_graph_builder_pipeline` 通过 | pytest 绿色 |
| 5 | `test_no_legacy_node_imports` 通过 | pytest 绿色 |
| 6 | 全量单测通过 | `pytest packages/datacloud-analysis/tests/` 绿色 |

---

## 4. 依赖

**前置**：G18 完成（旧节点文件已删除）。

## 5. 并行性

G18 完成后，可与 G21 并行执行。

## 6. 提交规范

```
refactor(g19): clean up legacy node tests and documentation
```
