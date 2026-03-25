# e_commerce_demo — LangGraph Agent

本目录为 **LangGraph** 入口，用于 `langgraph dev` 与同级 `../frontend`（Deep Agents UI）对接。

## 运行方式

在 **whale_datacloud** 仓库根目录先同步依赖，再启动：

```bash
uv sync --group dev
cd examples/e_commerce_demo/backend
uv run langgraph dev
```

默认会在 http://127.0.0.1:2024 启动 API。在 Deep Agents UI 中配置：

- **Deployment URL**: `http://127.0.0.1:2024`
- **Assistant ID**: `graph`（与 `langgraph.json` 中 `graphs` 的 key 一致）

## 依赖说明

`langgraph.json` 的 `dependencies` 指向 `../../../packages/datacloud-analysis`。Agent 逻辑在同包内 `src/datacloud_analysis/agent.py`（由本目录 `agent.py` 通过 `importlib` 加载）。

## 环境变量

复制 `.env.example` 为 `.env` 并填写 PG、数据服务、大模型等配置（见模板内注释）。

## 内嵌 DataCloud 数据服务

`datacloud_data_service/` 为与 `sales_analysis_demo` 相同的数据查询服务代码，可按需与 `mock_env` 或独立数据服务联调。
