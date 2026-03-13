# OpenClaw Gateway Service

OpenClaw 的后端服务，提供 WebSocket 接口供前端实时通信。

## 项目结构

```
datacloud-apps/datacloud-agent-service/
├── server.py              # FastAPI 入口
├── websocket.py           # WebSocket 端点
├── openclaw_protocol.py   # OpenClaw 协议处理
├── config.py              # 配置管理
├── lifespan.py            # 生命周期管理
├── scripts/
│   └── start.sh           # 启动脚本
└── tests/                 # 测试文件
```

## 功能

- **WebSocket 通信** (`/ws`) - 实时双向通信
- **健康检查** (`/health`) - 服务状态监控
- **OpenClaw 协议** - 支持会话管理、聊天消息流式传输
- **Mock 模式** - 无需 API key 即可测试

## 快速开始

### 1. 启动服务（Mock 模式）

```bash
cd datacloud-apps/datacloud-agent-service
./scripts/start.sh
```

服务将在 http://localhost:8000 运行。

### 2. 启动服务（真实 LLM）

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://your-endpoint/v1"  # 可选
./scripts/start.sh
```

### 3. 验证服务

```bash
curl http://localhost:8000/health
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | OpenAI API Key | 无（Mock 模式） |
| `OPENAI_BASE_URL` | API 基础 URL | `https://api.openai.com/v1` |
| `DATACLOUD_SERVICE_HOST` | 服务监听地址 | `0.0.0.0` |
| `DATACLOUD_SERVICE_PORT` | 服务端口 | `8000` |
