# dc_agent — DataCloud agent for Deep Agents UI

本目录为 **LangGraph** 入口，用于 `langgraph dev` 与 [ui/deep-agents-ui](../../../ui/deep-agents-ui) 对接。已从 datacloud-agent 挪到 datacloud-agent-service 下，与网关服务同仓。

## 运行方式

在 **whale_datacloud** 仓库根目录先同步依赖（含 datacloud-agent），再启动：

```bash
uv sync
cd service/datacloud-agent-service/scripts/dc_agent
uv run langgraph dev
```

或在 **datacloud-agent-service** 目录下：

```bash
cd D:\data\code\baiying\whale_datacloud\service\datacloud-agent-service
uv sync
cd scripts/dc_agent
uv run langgraph dev
```

默认会在 http://127.0.0.1:2024 启动 API。在 deep-agents-ui 中配置：

- **Deployment URL**: `http://127.0.0.1:2024`
- **Assistant ID**: `graph`（与 `langgraph.json` 中 `graphs` 的 key 一致）

## 依赖说明

`langgraph.json` 的 `dependencies` 指向 `../../../../datacloud-agent`，以便安装包含 `dc_agent` 的包。Agent 逻辑在 [datacloud-agent/src/dc_agent](../../../datacloud-agent/src/dc_agent)。

## 模型配置

Agent 使用与 content_writer 相同的大模型配置（Qwen via whale lab proxy），见 `datacloud-agent/src/dc_agent/agent.py`。
