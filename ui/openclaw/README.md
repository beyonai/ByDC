# OpenClaw UI

OpenClaw 的前端界面，基于 Lit + Vite 构建。

## 项目结构

```
ui/openclaw/
├── src/
│   ├── gateway.ts         # WebSocket 客户端
│   ├── controllers/
│   │   └── chat.ts        # 聊天状态管理
│   └── views/
│       └── chat-view.ts   # 聊天界面组件
├── index.html             # 入口 HTML
├── package.json           # 依赖配置
├── vite.config.ts         # Vite 配置
└── scripts/
    └── start.sh           # 启动脚本
```

## 功能

- **实时聊天** - WebSocket 连接后端，支持流式消息显示
- **会话管理** - 创建新会话、查看历史
- **Markdown 渲染** - 支持富文本消息显示
- **响应式界面** - 适配不同屏幕尺寸

## 快速开始

### 1. 启动前端

```bash
cd ui/openclaw
./scripts/start.sh
```

前端将在 http://localhost:3000 运行（如被占用会自动尝试其他端口）。

### 2. 确保后端已启动

```bash
# 在另一个终端
cd service/datacloud-agent-service
./scripts/start.sh
```

### 3. 访问应用

打开浏览器访问 http://localhost:3000

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENCLAW_UI_PORT` | 前端服务端口 | `3000` |

## 开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build
```

## 连接配置

前端默认连接 `ws://localhost:8000/ws`。如需修改后端地址，编辑 `src/gateway.ts`：

```typescript
constructor(private url: string = "ws://localhost:8000/ws") {}
```
