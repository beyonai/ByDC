# 8. 与 OpenClaw 的差异

## 8.1 架构层面差异

| 特性 | OpenClaw Gateway | Python SDK 实现 |
|------|-----------------|----------------|
| **Agent SDK** | Pi SDK (Node.js) | deepagents (Python) |
| **运行时** | Node.js + TypeScript | Python + LangGraph |
| **沙箱** | Docker | deepagents sandbox / 可选 |
| **对外接口** | WebSocket/HTTP 服务器 | Python SDK API |
| **子 Agent** | Pi SDK 原生 | deepagents SubAgent |
| **工具** | Pi SDK 内置 | deepagents 内置 |
| **持久化** | JSONL 树结构 | JSONL 简化版 |
| **协议** | 完整 Gateway 协议 | 无协议，直接 API 调用 |
| **认证** | Token/Password/Tailscale | 应用层处理 |
| **重试逻辑** | 复杂 (auth failover, compaction) | 简化 |

## 8.2 服务模式差异

| 方面 | OpenClaw Gateway | Python SDK 实现 |
|------|-----------------|----------------|
| **部署方式** | 独立服务进程 | 库/包形式嵌入应用 |
| **通信方式** | 网络协议 (WS/HTTP) | 进程内函数调用 |
| **事件流** | WebSocket 帧 | Python 异步迭代器/回调 |
| **并发处理** | 服务器管理连接 | 应用管理 async 任务 |
| **适用场景** | 多客户端远程访问 | 单应用内集成 |

## 8.3 已剥离的组件

以下 OpenClaw Gateway 的组件在 SDK 版本中已移除：

1. **GatewayServer** - WebSocket/HTTP 服务器
2. **协议握手** - connect/hello-ok 帧处理
3. **传输层认证** - Token/Password/Tailscale 集成
4. **多渠道适配** - WhatsApp/Telegram/Discord 等

---
