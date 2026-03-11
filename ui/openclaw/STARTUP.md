# OpenClaw UI 启动指南

本文档说明如何启动 OpenClaw UI 的前端和后端服务。

## 环境要求

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) >= 0.7
- Node.js >= 18
- npm >= 9

## 快速启动

### 1. 启动后端服务

```bash
cd service/datacloud-agent-service

# 使用真实 API（推荐）
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"
uv run python -m uvicorn server:app --host 0.0.0.0 --port 8000

# 或使用 mock 模式（无需 API key）
uv run python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

后端服务将在 http://localhost:8000 运行。

### 2. 启动前端服务

```bash
cd ui/openclaw
npm run dev
```

前端服务将在 http://localhost:3000 运行。

### 3. 访问应用

打开浏览器访问 http://localhost:3000

## 配置说明

### 后端配置

后端服务支持以下环境变量：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `OPENAI_API_KEY` | OpenAI API Key | 无（mock 模式） |
| `OPENAI_BASE_URL` | OpenAI API Base URL | https://api.openai.com/v1 |
| `DATACLOUD_SERVICE_HOST` | 服务监听地址 | 0.0.0.0 |
| `DATACLOUD_SERVICE_PORT` | 服务端口 | 8000 |

### 前端配置

前端通过 WebSocket 连接到后端，默认连接 `ws://localhost:8000/ws`。

如需修改后端地址，编辑 `ui/openclaw/src/gateway.ts`：

```typescript
constructor(private url: string = "ws://localhost:8000/ws") {}
```

## 验证服务

### 检查后端健康状态

```bash
curl http://localhost:8000/health
```

预期响应：
```json
{"status":"healthy","service":"datacloud-agent-service","version":"0.1.0"}
```

### 检查前端

打开浏览器访问 http://localhost:3000，应看到：
- 页面标题：DataCloud Agent - OpenClaw UI
- 连接状态：Connected（绿色指示）

## 常见问题

### 1. 端口被占用

**后端端口 8000 被占用：**
```bash
# 查找占用进程
lsof -i :8000
# 结束进程
kill -9 <PID>
```

**前端端口 3000 被占用：**
前端会自动尝试其他端口（如 3001），查看控制台输出获取实际端口。

### 2. API Key 无效

如果使用真实 API 返回错误，请检查：
- API Key 是否正确
- Base URL 是否可访问
- 网络连接是否正常

### 3. 前端不显示 AI 响应

检查浏览器控制台：
- WebSocket 是否连接成功
- 是否收到 `chat.chunk` 事件
- 是否有 JavaScript 错误

## 开发模式

### 后端热重载

```bash
uv run python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### 前端开发

```bash
cd ui/openclaw
npm run dev
```

Vite 提供热模块替换（HMR），修改代码后页面自动更新。

## 生产部署

### 构建前端

```bash
cd ui/openclaw
npm run build
```

构建产物在 `ui/openclaw/dist` 目录。

### 部署后端

使用 gunicorn 或 uvicorn 部署：

```bash
uv run gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## 目录结构

```
whale-datacloud/
├── service/
│   └── datacloud-agent-service/    # 后端服务
│       ├── server.py                # FastAPI 入口
│       ├── openclaw_protocol.py     # WebSocket 协议处理
│       └── websocket.py             # WebSocket 端点
├── ui/
│   └── openclaw/                    # 前端应用
│       ├── src/
│       │   ├── views/chat-view.ts   # 聊天界面
│       │   ├── controllers/chat.ts  # 状态管理
│       │   └── gateway.ts           # WebSocket 客户端
│       └── index.html
└── datacloud-agent/                 # Agent 核心库
    └── src/datacloud_agent/
```

## 相关文档

- [datacloud-agent README](../../datacloud-agent/README.md)
- [后端服务 README](../../service/datacloud-agent-service/README.md)
