# G20 全链路回归与发布

## 1. 任务定义

### 1.1 背景

G18（旧节点下线）、G19（测试清理）、G21（目录重组）、G22（ToolRuntime）、G23（skill 标签）、G24（ReAct todo.md）、G25（relation 多步）全部完成后，执行最终全链路回归验收。

### 1.2 目标

1. 验证 4 类核心场景全部通过。
2. 验证图结构稳定性与 tool hook 回调链。
3. 生成回归报告并归档。
4. 完成发布清单签核。

---

## 2. 回归矩阵

### 2.1 必测场景（全部必须通过）

| 编号 | 场景 | 验证要点 |
|------|------|---------|
| C1 | 闲聊短路 | worker 直接回复，不进入 LangGraph 图 |
| C2 | 自动确权后规划执行 | knowledge_enhance → planning → execution → end 全链路正常 |
| C3 | 中断恢复链路 | 含 `checkpoint_id/checkpoint_ns/todo_active_id/react_step_id` 字段验证 |
| C4 | 子 agent 委托路径 | `query_mode=agent_delegate` 的 todo 不被术语澄清阻断 |
| C5 | relation 多步编排 | relation 语义 todo 自动拆分为 locate + query 两步，结果参数正确注入 |
| C6 | skill 标签过滤 | blocklist_tags 命中时 skill 被禁止执行 |
| P1 | 图主链结构稳定性 | `build_analysis_graph()` 节点名称符合预期，无旧节点 |
| P2 | Tool Hook 回调链稳定性 | before/after 回调按优先级执行，patch/interrupt/fail 行为正确 |
| P3 | ToolRuntime 统一入口 | `execute_next_task` 委托给 `ToolRuntime.invoke_with_callbacks` |

### 2.2 可选场景

| 编号 | 场景 | 验证要点 |
|------|------|---------|
| P4 | 执行层关键单测集合时延基线 | 与重构前基线对比，不劣化超过 20% |

---

## 3. 执行方式

### 3.1 运行全量单测

```bash
pytest packages/datacloud-analysis/tests/ -v --tb=short 2>&1 | tee 回归结果.txt
```

### 3.2 图结构验证（P1）

```python
from datacloud_analysis.orchestration.graph_builder import build_analysis_graph

graph = build_analysis_graph()
node_names = set(graph.nodes.keys())

assert {"knowledge_enhance", "planning", "execution", "end"}.issubset(node_names)
assert not {"intent", "dag", "loop", "clarification", "agent_delegate", "direct_tool"} & node_names
```

### 3.3 手动验证核心场景

**C1 闲聊短路：** 发送 "你好"，预期 worker 直接回复，不触发图执行。

**C2 自动确权：** 发送 "查询企业综合分析表前100条数据"，预期全链路正常。

**C3 中断恢复：** 触发含 `ambiguous_terms` 的查询，验证中断 state 含 `resume_context`，恢复后不重复执行已完成 todo。

**C4 子 agent 委托：** 发送文档知识问答类请求，预期不触发术语澄清中断。

**C5 relation 多步：** 发送含关系语义的查询（如"A 和 B 的关联关系"），验证 planning 生成两步 todo。

**C6 skill 标签过滤：** 配置含 blocklist_tags 的 skill，发送匹配请求，验证 skill 被禁止。

---

## 4. 验收门禁

| # | 验收项 | 通过标准 |
|---|--------|---------|
| 1 | C1~C6 场景全部通过 | 手动或自动化测试均通过 |
| 2 | P1 图结构验证通过 | `test_graph_builder_pipeline.py` 绿色 |
| 3 | P2 Tool Hook 验证通过 | `test_tool_hook_plugin_manager.py` 绿色 |
| 4 | P3 ToolRuntime 验证通过 | `test_tool_runtime.py` 绿色 |
| 5 | 全量单测通过 | `pytest packages/datacloud-analysis/tests/` 0 failures |
| 6 | 无旧节点引用 | `test_no_legacy_node_imports.py` 绿色 |
| 7 | README 对齐新链路 | `test_readme_pipeline_alignment.py` 绿色 |
| 8 | 回归报告已归档 | 本目录下存在 `回归报告.md` |

---

## 5. 交付物

完成后在本目录归档：

| 文件 | 内容 |
|------|------|
| `回归报告.md` | 各场景测试结果、通过/失败状态、问题说明 |
| `发布清单.md` | 发布前检查项签核记录 |
| `风险清单.md` | 已知风险、缓解措施、后续跟进项 |

---

## 6. 依赖

**前置**：G18、G19、G21、G22、G23、G24、G25 全部完成并合入目标分支。

## 7. 并行性

收口任务，不可并行，必须在前两波次全部完成后执行。

## 8. 回滚预案

若发布后发现严重回归：

1. 立即回滚到 G17 完成时的 commit（`git revert` 或 `git reset`）。
2. 旧节点文件可从 git history 恢复（`git checkout <commit> -- <file>`）。
3. 通知相关方，记录回滚原因到 `风险清单.md`。

## 9. 提交规范

```
refactor(g20): final regression and release checklist for orchestration refactor
```
