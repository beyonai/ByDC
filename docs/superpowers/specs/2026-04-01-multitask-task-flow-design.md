# 多任务规划与返回改造设计（2026-04-01）

## 1. 背景
- 复杂查询需要拆分为多个任务（如先查网格，再查企业）。
- 现有系统只保留最后任务结果，缺少依赖传参与多文件返回。
- 目标是一轮用户请求即可获得所有子任务结果及综合说明。

## 2. 目标
1. 规划节点支持 DAG 契约：`depends_on` + `inputs_from`。
2. 执行节点按拓扑顺序运行任务并注入依赖输出。
3. 每个任务产出结构化结果与文件，并统一追加写入。
4. End/Insight 节点聚合多任务结果，支持分别/综合返回与文件列示。
5. 完整链路具备可观测日志，便于诊断任务处理过程。

## 3. 架构概览
```
knowledge_enhance → planning (DAG Planner) → execution (DAG Executor) → end (Multi-task Aggregator) → insight
```
- `WorkerState.context` 扩展：
  - `planned_tasks`: `PlanTask` 列表。
  - `task_queue`: 按拓扑排序的 `todo_id` 队列。
  - `results_list`: `TaskResult` 顺序列表。
  - `results_map`: `{todo_id: TaskResult}` 快速访问。
- 统一 artifact 根目录：`<session_workspace>/tasks/<todo_id>/`。

## 4. 规划节点设计
1. **输入**：LLM 生成的任务 JSON（含 `todo_id/goal/required_tools/depends_on/inputs_from`）。
2. **验证**：
   - `todo_id` 唯一。
   - `depends_on` 指向已定义任务。
   - `inputs_from` 中出现的任务若未声明在 `depends_on`，自动补充依赖边。
   - 无环：构建 DAG（NetworkX 或自实现拓扑）。
3. **拓扑排序**：
   - 生成 `task_queue`。
   - 对拓扑不可达节点标记 `blocked_by_missing_dependency`，并立即生成对应 `TaskResult(status='blocked', blocked_by='missing_dependency')` 供后续节点展示。
4. **`inputs_from` 语法**：
   - 允许引用父任务 `TaskResult.result_meta` 下的字段，语法：`"<task>.result_meta.<field>[.<subfield>]"`。
   - 允许引用 `artifact_refs`，语法：`"<task>.artifact_refs[<index>].<field>"`。
   - 若字段缺失或索引越界，规划层记录 warning；执行阶段注入 `None` 并判定是否继续。
   - 任务可声明 `required_inputs`（如 `{"grid_ids": true}`），执行阶段若必需字段为 `None` 则直接 `blocked`。
5. **PlanTask 结构**：
   ```python
   @dataclass
   class PlanTask:
       todo_id: str
       goal: str
       required_tools: list[str]
       depends_on: list[str]
       inputs_from: dict[str, str]
       required_inputs: dict[str, bool]
   ```
6. **状态写入**：
   - `state.context['planned_tasks'] = [PlanTask,...]`
   - `state.context['task_queue'] = ['t1','t2',...]`
   - 初始化 `results_list=[]`, `results_map={}`（若已有 blocked 任务，预填对应结果）。
7. **日志**：输出任务数量、DAG 边、拓扑顺序、被阻断任务。

## 5. 执行节点设计
1. **循环**：按 `task_queue` 迭代，若队列项已在 `results_map`（如预blocked）则跳过执行，直接纳入最终结果。
2. **依赖注入**：
   - 根据 `inputs_from` 从 `results_map[source_id]` 读取字段，如果 source 失败则目标任务 `status='blocked'`、`blocked_by=source_id`。
   - 若某个注入值 `None` 且 `required_inputs[key]=true`，直接判定 blocked。
   - 对 artifact 引用：若文件不存在或无法读取，记录 `TaskError(code='artifact_not_found', ...)` 并直接 `status='failed'`。
3. **工具调用**：
   - 选取 `required_tools`（未来兼容 skill/hook）。
   - 构造 payload：用户原 query、任务 goal、注入参数、todo_id。
4. **失败策略**：
   - 工具返回错误、超时或 artifact 写入失败 -> `status='failed'`，记录 `error_detail`。
   - 不重试；依赖任务自动 `blocked_by`。
5. **产物写入**：
   ```python
   @dataclass
   class ArtifactRef:
       todo_id: str
       path: str  # <session>/tasks/<todo_id>/<file>
       name: str
       mime: str | None
       size: int | None
   
   @dataclass
   class TaskError:
       code: str
       message: str
       tool: str | None
       trace_id: str | None
       remediation: str | None
   
   @dataclass
   class TaskResult:
       todo_id: str
       status: Literal['success','failed','blocked']
       result_meta: dict[str, Any]
       artifact_refs: list[ArtifactRef]
       error_detail: TaskError | None
       blocked_by: str | Literal['missing_dependency', None]
   ```
   - 文件写入 `tasks/<todo_id>/...`。
   - `state.context['results_list'].append(result)`。
   - `state.context['results_map'][todo_id] = result`。
6. **日志**：任务开始/结束、依赖注入结果、产物路径、error/blocked 原因。

## 6. End 节点设计
1. **输入**：`results_list` + `planned_tasks`。
2. **分别返回**：按拓扑顺序生成 per-task 段落（包含状态、摘要、关键指标）。
3. **综合说明**：存在依赖关系时，组合 narrative，说明后续任务基于哪些上游输出。
4. **blocked/failed 展示**：
   - `blocked`：展示“任务 t2 因 t1 失败被阻断”，并引用 `blocked_by`（包括 `missing_dependency`或缺失必须输入）。
   - `failed`：展示 `error_detail.message` 与可选恢复建议。
5. **文件列表**：汇总 `artifact_refs`，附 path、todo_id、描述。
6. **`final_summary` 契约**：
   ```json
   {
     "tasks": [
       {
         "todo_id": "t1",
         "status": "success",
         "summary": "找出效益最低的10个网格……",
         "result_meta": {...},
         "artifact_refs": [...],
         "depends_on": []
       },
       {
         "todo_id": "t2",
         "status": "blocked",
         "summary": "因 t1 失败未执行",
         "blocked_by": "t1",
         "result_meta": {},
         "artifact_refs": []
       }
     ],
     "combined_narrative": "企业结果来自 t1 输出的 10 个网格……",
     "artifact_index": [
       {"todo_id": "t1", "path": ".../tasks/t1/...", "desc": "网格 Top10"},
       {"todo_id": "t2", "path": ".../tasks/t2/...", "desc": "企业 Top10"}
     ]
   }
   ```
   - Insight 直接消费 `final_summary` 渲染不同返回模式。

## 7. 可观测性
- 规划：`planned_tasks` 数量、`dag_edges`、`topology_order`、`blocked_initially`。
- 执行：每个任务的 `status`、耗时、依赖解析结果、错误码。
- End：`returned_tasks`、`artifact_count`、blocked/failed 摘要。

## 8. 测试计划
1. **Unit**：
   - `planning_node`：循环依赖检测、缺失 `todo_id`、`inputs_from` 解析、`blocked_by_missing_dependency` 生成。
   - `execution_node`：依赖注入正确性、artifact 缺失、任务成功/失败/阻断场景、必需输入缺失处理。
   - `end_node`：`final_summary` 结构生成、blocked/failed 渲染。
2. **Integration**：
   - 构造模拟 DAG 请求，验证两个子任务均执行并写入 `results_list`。
3. **Regression**：
   - 确认单任务 case 仍按原逻辑运行（`task_queue` 只有一项）。

## 9. 后续
- Insight 读取 `final_summary`，渲染 UI。
- 若需与空间同步，`artifact_refs` 提供真实路径/URL。
- 堆叠更多任务类型时，复用 `PlanTask`/`TaskResult` 契约。