# 超级分析智能体

本目录为 [Deep Agents UI](https://github.com/langchain-ai/deep-agents-ui) 的代码，作为 whale_datacloud 仓库的一部分嵌套在此，用于连接 LangGraph / Deep Agents 进行对话与调试。

## 使用方式（仓库根目录下）

```bash
cd ui/deep-agents-ui
yarn install
yarn dev
```

浏览器打开 http://localhost:3000，在设置中填写：

- **Deployment URL**：LangGraph 服务地址（如 `http://127.0.0.1:2024`）
- **Assistant ID**：对应 agent 的 ID（如来自 `langgraph.json` 的 graph 名）
- **LangSmith API Key**（可选）：可按需配置或使用环境变量 `NEXT_PUBLIC_LANGSMITH_API_KEY`

## 上游出处

- 上游仓库：[langchain-ai/deep-agents-ui](https://github.com/langchain-ai/deep-agents-ui)
- 基于 [Deep Agents](https://github.com/langchain-ai/deepagents) 的交互界面，用于与 LangGraph 部署的 agent 进行聊天、查看状态与调试。
