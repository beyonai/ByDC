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
