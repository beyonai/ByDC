# e_commerce_demo — Backend

本文从 `datacloud_service/main.py` 入口出发，梳理 Gateway Worker 到 LangGraph 全链路，并说明 `workspace_api.py` 启动方式。

## 1) 启动方式

### `main.py`（Gateway Worker）

在仓库根目录执行：

```bash
uv sync
uv run python examples/e_commerce_demo/backend/datacloud_service/main.py
```

可选脚本：

- Linux/macOS：`bash examples/e_commerce_demo/backend/start.sh`
- Windows：`examples\e_commerce_demo\backend\start.bat`

### `workspace_api.py`（工作区文件 API）

在仓库根目录执行：

```bash
uv run python examples/e_commerce_demo/backend/datacloud_service/workspace_api.py
```

默认监听 `0.0.0.0:8081`，接口文档：`http://127.0.0.1:8081/docs`。

---

## 2) 从 `main.py` 开始的完整代码链路

### A. 进程启动层（`main.py`）

`main.py` 的职责是读取环境变量并启动 `run_worker`（自 `by_framework` 包导入；PyPI/依赖名为 `by-framework`）：

1. `load_dotenv(...)` 加载 `examples/e_commerce_demo/backend/.env`。
2. `WorkerConfig.from_environ()` 读取并组装运行参数（Redis、模型、workspace 等）。
3. `run_worker(...)` 启动 `DataCloudWorker`，并注册插件 `InitDataCloudDigitalEmployeePlugin`。

关键点：

- `worker_class=DataCloudWorker` 决定后续消息处理逻辑。
- `plugin_list=[InitDataCloudDigitalEmployeePlugin()]` 决定动态 Agent 配置来源（提示词 + 工具）。

### B. 插件初始化层（`init_agent_conf.py`）

`InitDataCloudDigitalEmployeePlugin.register_agent_configs()` 在 Worker 启动阶段执行，作用是把数字员工配置注入到网关上下文：

1. 调 AI Factory 拉取数字员工列表与详情。
2. 把角色属性/处理流程等拼成 `task_prompt`。
3. 基于本体（`OntologyLoader`）构建动态工具（例如 `*_query`）。
4. 组装 `AgentConfig(agent_id, prompts, tools, ...)` 回写到 `agent_context`。
5. 若没有加载到可用 agent 或某 agent 无工具，则启动失败。

关键产物：

- `prompts`：包含 `system_prompt`、`task_prompt` 等。
- `tools`：动态查询工具，后续会进入 DAG 规划与任务执行。

### C. Worker 处理层（`worker.py`）

每次收到网关指令（`AskAgentCommand`）后，`DataCloudWorker.process_command()` 执行：

1. 归一化输入消息为 LangChain 消息列表（`_normalize_messages`）。
2. 从 `extra_payload.byAgentId` 选择当前会话对应的 `AgentConfig`。
3. 计算配置哈希（prompt + tools），命中缓存则复用图，否则重建图。
4. 构造初始 `state`（`messages/intent/plan/results/workspace_dir/gateway_context/...`）。
5. 调用 `target_graph.astream_events(...)` 流式运行图。
6. 转发工具起止事件到前端（`TASK_CREATE` / `STEP_COMPLETE`）。
7. 结束后发“回答完成”，并 `flush_to_history()`。

关键点：

- `gateway_context` 放入 state 后，节点内部可以直接发 SSE 思考事件。
- `prompts_overwrite` 和 `dynamic_tools` 同时注入 state，图节点可直接读取。

### D. 图工厂层（`datacloud_analysis.agent -> graph_builder`）

`create_agent()` 内部调用 `build_analysis_graph(...).compile()`，图结构固定为：

`START -> intent -> (clarify? insight : dag) -> loop(可迭代) -> insight -> END`

对应节点文件：

- `intent`: `orchestration/intent.py`
- `dag`: `orchestration/dag.py`
- `loop`: `orchestration/loop.py`
- `insight`: `orchestration/insight.py`

---

## 3) 每个节点是干什么的（输入/输出/路由）

### 节点1：`intent_node`（意图识别与改写）

文件：`packages/datacloud-analysis/src/datacloud_analysis/orchestration/intent.py`

主要职责：

1. 读取用户最后一条消息。
2. 调 `search_knowledge` 检索业务知识片段。
3. 用 LLM 输出严格 JSON：`rewritten_intent` + `clarify_needed`。
4. 推送“问题理解”思考日志。

输出写回 state：

- `intent`: 改写后的问题
- `clarify_needed`: 是否需要澄清
- `knowledge_preview`: 截断后的知识片段

路由：

- `clarify_needed=true`：直接进 `insight`（澄清/闲聊路径）
- `clarify_needed=false`：进入 `dag`

### 节点2：`dag_node`（任务拆解规划）

文件：`packages/datacloud-analysis/src/datacloud_analysis/orchestration/dag.py`

主要职责：

1. 根据 `intent` 让 LLM 生成任务数组（DAG plan）。
2. 约束任务类型（动态工具、`code_exec`、`search_knowledge`、`render_report`）。
3. 自动修正 `*_query` 任务参数，确保有 `query/question`。
4. 推送“任务规划”思考日志。

输出写回 state：

- `plan`: 任务列表（每项含 `id/type/status/deps/params`）

兜底逻辑：

- LLM 规划失败时优先回退到一个动态工具任务。
- 若当前没有任何动态工具，会改为澄清分支并提示“先挂载工具”。

### 节点3：`loop_node`（任务执行循环）

文件：`packages/datacloud-analysis/src/datacloud_analysis/orchestration/loop.py`

主要职责：

1. 从 `plan` 中挑出依赖已满足的 ready 任务。
2. 并发执行 ready 任务（`asyncio.gather`）。
3. 单任务：结果放内存 `results[].data`；多任务：结果落盘到 `workspace/temp/{task_id}.json`。
4. 回写任务状态（`done/failed`）。
5. 推送“执行任务”思考日志。

执行器入口：

- `execute_next_task(...)`（`sandbox_executor.py`）按 `task.type` 分发到动态工具或内置工具。

路由（`graph_builder.route_loop`）：

- 仍有 `pending` 任务：继续回到 `loop`
- 全部完成：进入 `insight`

### 节点4：`insight_node`（最终回答生成）

文件：`packages/datacloud-analysis/src/datacloud_analysis/orchestration/insight.py`

主要职责：

1. 聚合 `results`（从内存或 workspace 文件）并格式化。
2. 在第一条 `answerDelta` 前发送 `reasoningLogEnd`（保证 SSE 顺序正确）。
3. 输出最终回答，分两类路径：
   - 澄清路径：只流式输出文本回答。
   - 分析路径：Part1 文本分析 + Part2/Part3 结构化结果（优先 6001 JSON）。
4. 对 `clarify_prompt` 和 `insight_prompt` 追加 `task_prompt`（方案A已生效）。

关键行为：

- 单任务且结构化结果充分时，会走 fast-path：跳过 Part1 LLM，只发结构化结果块。
- 结构化结果优先通过 `content_type=6001` 发给前端，便于前端表格渲染。

---

## 4) `workspace_api.py` 在链路中的位置

`workspace_api.py` 不是图节点，它是工作区产物读取服务：

- 读取 `DATACLOUD_GATEWAY_WORKSPACE_DIR` 下的会话文件。
- 提供 `/api/v1/workspace/files` 分页读取 JSONL/JSON。
- 支持 `download=true` 直接下载文件。

它通常用于前端或调试工具回看 `loop_node` 落盘的中间/结果文件，与 Worker 执行链路解耦。

---

## 5) 常见故障位点（按链路定位）

- 启动即失败：优先看插件是否拉到有效 AgentConfig（工具为空会失败）。
- `Task t1 failed: All connection attempts failed`：通常在 `loop -> execute_next_task -> 动态 query tool` 处，检查数据服务或数据库连通性。
- 有文本无表格：看 `insight_node` 是否拿到结构化 `results`，以及前端是否消费了 6001。

建议先保证以下变量与服务可用：`OPENAI_*`、`DATACLOUD_GATEWAY_REDIS_*`、`DATACLOUD_DATA_SERVICE_*`、`DATACLOUD_GATEWAY_WORKSPACE_DIR`。
# e_commerce_demo — Backend

## `main.py`（Gateway Worker）

在 **whale_datacloud 仓库根目录**：

```bash
uv sync
uv run python examples/e_commerce_demo/backend/datacloud_service/main.py
```

脚本：

- **Linux / macOS**：`bash examples/e_commerce_demo/backend/start.sh`
- **Windows**：`examples\e_commerce_demo\backend\start.bat`

启动时会加载 `examples/e_commerce_demo/backend/.env`。工作区根目录由 **`DATACLOUD_GATEWAY_WORKSPACE_DIR`** 控制，需与下方 Workspace API 一致。

---

## `workspace_api.py`（工作区文件 API）

在仓库根目录：

```bash
uv run python examples/e_commerce_demo/backend/datacloud_service/workspace_api.py
```

默认 **`0.0.0.0:8081`**，文档：`http://127.0.0.1:8081/docs`。也可在 `backend` 目录下：

```bash
cd examples/e_commerce_demo/backend
uv run uvicorn datacloud_service.workspace_api:app --host 0.0.0.0 --port 8081
```

**环境变量**：`DATACLOUD_GATEWAY_WORKSPACE_DIR` 须与 Worker 相同。本文件不会自动 `load_dotenv`，若路径只在 `.env` 里配置，请用系统环境或启动前手动注入。
