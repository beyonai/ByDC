# DataCloud Agent Scripts

本目录包含 DataCloud Agent 的各种脚本和工具。

## 目录结构

```
scripts/
├── README.md                 # 本文件
├── start_with_ui.sh         # 启动 Agent + UI 的便捷脚本
├── content_writer/          # Content Writer Agent
│   ├── agent.py            # Agent 入口
│   ├── langgraph.json      # LangGraph 配置
│   ├── run_agent.sh        # 单独启动 Agent
│   └── AGENTS.md           # Agent 行为配置
└── ui/                     # 前端 UI（Git 子模块）
    └── deep-agents-ui/     # Deep Agents 调试 UI
```

## 快速开始

### 1. 初始化 UI 子模块

如果是首次克隆仓库，需要初始化 Git 子模块：

```bash
git submodule update --init --recursive
```

### 2. 一键启动 Agent + UI

```bash
# 启动 content_writer agent 和 UI
./start_with_ui.sh

# 或指定其他 agent
./start_with_ui.sh content_writer
```

脚本会自动：
1. 启动 LangGraph Agent（端口 2024）
2. 启动 Deep Agents UI（端口 3000）
3. 显示访问地址和配置信息
4. 按 Ctrl+C 同时停止两个服务

### 3. 手动启动（如需分别控制）

**终端 1 - 启动 Agent：**

```bash
cd content_writer
uv run langgraph dev
```

Agent 将在 `http://127.0.0.1:2024` 启动。

**终端 2 - 启动 UI：**（UI 位于仓库根目录 `ui/deep-agents-ui`）

```bash
cd ../../ui/deep-agents-ui

# 首次运行需要安装依赖
yarn install

# 启动开发服务器
yarn dev
```

UI 将在 `http://localhost:3000` 启动。

## UI 配置

打开 http://localhost:3000 后，输入以下信息：

| 配置项 | 值 | 说明 |
|--------|-----|------|
| Deployment URL | `http://127.0.0.1:2024` | LangGraph API 地址 |
| Assistant ID | `graph` | 来自 `langgraph.json` 的 graph 名称 |
| LangSmith API Key | (可选) | 如需连接 LangSmith 服务 |

## Deep Agents UI 功能

- **聊天界面**：与 Agent 实时对话
- **文件查看器**：查看 Agent 生成的文件
- **调试模式**：逐步执行 Agent，查看每一步的状态
- **实时流式**：实时查看 Agent 的执行过程

## Agent 类型

### content_writer

内容创作 Agent，具备以下能力：
- 网络搜索研究
- 生成博客文章
- 生成社交媒体图片
- 文件系统操作

## 故障排除

### 端口被占用

```bash
# 查看端口占用
lsof -i :2024  # Agent 端口
lsof -i :3000  # UI 端口

# 终止占用进程
kill -9 <PID>
```

### UI 目录说明

`ui/deep-agents-ui` 已作为仓库的一部分（非子模块），随仓库一起 clone 即可，无需 `git submodule update`。若该目录缺失，请重新 clone 整个 whale_datacloud 仓库。

### Agent 启动失败

检查日志文件：
```bash
cat /tmp/agent.log
cat /tmp/ui.log
```

## 技术栈

- **Agent**: Python + LangGraph + DeepAgents
- **UI**: Next.js + TypeScript + Tailwind CSS
- **通信**: LangGraph SDK REST API

## 相关文档

- [Deep Agents UI](https://github.com/langchain-ai/deep-agents-ui)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [DataCloud Agent 主文档](../README.md)
