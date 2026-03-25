# 亦庄产业大脑

## 简介

亦庄产业大脑是一个基于 Agent 的产业大脑 Demo，用于演示如何通过 Agent 技术实现产业大脑的能力。

## Agent 前后端（LangGraph + Deep Agents UI）

与 `examples/sales_analysis_demo` 同源：`backend/` 为 LangGraph 入口，`frontend/` 为对话界面。

```bash
# 仓库根目录
uv sync --group dev

# 终端 1 — Agent API（默认 http://127.0.0.1:2024）
cd examples/e_commerce_demo/backend
uv run langgraph dev

# 终端 2 — 前端（默认 http://localhost:3000）
cd examples/e_commerce_demo/frontend
yarn install
yarn dev
```

在浏览器设置中填写 **Deployment URL** 为 `http://127.0.0.1:2024`，**Assistant ID** 为 `graph`。`backend/.env` 需从 `.env.example` 复制并配置 PG、大模型与数据服务（详见 `backend/README.md`）。

数据仿真与知识测试仍使用本目录下的 `mock_env/`。
