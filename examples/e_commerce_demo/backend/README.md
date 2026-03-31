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

也可在 `backend` 目录下运行：

```bash
cd examples/e_commerce_demo/backend
uv run uvicorn datacloud_service.workspace_api:app --host 0.0.0.0 --port 8081
```

`workspace_api.py` 不会自动 `load_dotenv`，请确保 `DATACLOUD_GATEWAY_WORKSPACE_DIR` 已在系统环境中注入，且与 Worker 进程保持一致。

---

## 2) 从 `main.py` 开始的完整代码链路

### A. 进程启动层（`main.py`）

1. `load_dotenv(...)` 加载 `examples/e_commerce_demo/backend/.env`。
2. `WorkerConfig.from_environ()` 读取并组装运行参数（Redis、模型、workspace 等）。
3. `run_worker(...)` 启动 `DataCloudWorker`，并注册插件 `InitDataCloudDigitalEmployeePlugin`。

### B. 插件初始化层（`init_agent_conf.py`）

`InitDataCloudDigitalEmployeePlugin.register_agent_configs()` 在 Worker 启动阶段执行：

1. 拉取数字员工列表与详情。
2. 组装 `task_prompt`。
3. 基于本体构建动态工具（例如 `*_query`）。
4. 写回 `AgentConfig(agent_id, prompts, tools, ...)` 到 `agent_context`。

### C. Worker 处理层（`worker.py`）

`DataCloudWorker.process_command()` 的关键流程：

1. 归一化输入消息。
2. 选择当前会话对应 `AgentConfig`。
3. 以 `prompt + tools` 哈希命中/重建编译图。
4. 构造初始 `AgentState` 并执行 `astream_events(...)`。
5. 转发工具事件，结束后 `flush_to_history()`。

### D. 图工厂层（`datacloud_analysis.agent -> graph_builder`）

`create_agent()` 内部调用 `build_analysis_graph(...).compile()`，当前主链为：

`START -> knowledge_enhance -> planning -> execution -> end -> END`

当 `execution_status` 为 `replan` 或 `execution` 时，执行节点会分别回到 `planning` 或 `execution` 继续处理；为 `done` 时进入 `end`。

---

## 3) 节点职责（当前主链）

### `knowledge_enhance`

- 补充知识上下文与术语提示。
- 输出增强后的查询语义供后续规划使用。

### `planning`

- 识别查询模式（analysis / online_query / agent_delegate）。
- 产出 `todos` 与 `todo_md`，必要时生成 direct todo。

### `execution`

- 并发执行依赖满足的 todo。
- 落盘多任务结果并维护执行轨迹。
- 根据 `execution_status` 驱动重规划、继续执行或结束。

### `end`

- 汇总执行结果。
- 输出最终回答（含结构化结果优先通道）。

---

## 4) `workspace_api.py` 在链路中的位置

`workspace_api.py` 不是图节点，而是工作区产物读取服务：

- 读取 `DATACLOUD_GATEWAY_WORKSPACE_DIR` 下会话文件。
- 提供 `/api/v1/workspace/files` 分页读取 JSONL/JSON。
- 支持 `download=true` 直接下载文件。
