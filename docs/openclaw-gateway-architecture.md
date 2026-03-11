# OpenClaw Gateway Python 实现 - 架构设计方案

> 基于 datacloud-agent SDK 的 OpenClaw Gateway Python 实现架构设计文档
> 版本: 1.0
> 日期: 2026-03-09

---

## 1. 设计目标

基于 datacloud-agent SDK 构建一个最小化的 OpenClaw Gateway Python 实现，核心特性：

- **SDK 级 API**: 提供 Python 库而非独立服务
- **多 Agent 切换**: 支持斜杠命令（`/model`, `/reset`, `/help` 等）
- **多租户架构**: 基于工作空间路径的租户隔离
- **队列系统**: 6 种队列模式（COLLECT/STEER/STEER_BACKLOG/FOLLOWUP/INTERRUPT/QUEUE）
- **四层文件架构**: SystemPromptBuilder 支持身份层/操作层/知识层/协作层
- **无 WebSocket/HTTP 服务器**: SDK 纯进程内调用
- **Service 层分离**: HTTP/WebSocket 服务作为独立组件，与 SDK 分离

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         whale-datacloud (Workspace)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────┐ │
│  │   datacloud-agent/      │  │   service/              │  │    ui/      │ │
│  │   (SDK Package)         │  │   (Service Layer)       │  │  (UI Layer) │ │
│  │                         │  │                         │  │             │ │
│  │  ┌─────────────────┐   │  │  ┌─────────────────┐     │  │ deep-agents │ │
│  │  │  src/datacloud_ │   │  │  │ datacloud-agent │     │  │    -ui/     │ │
│  │  │     agent/      │   │  │  │    -service/    │     │  │  (submodule)│ │
│  │  │                 │   │  │  │                 │     │  │             │ │
│  │  │  • api/         │   │  │  │  • server.py    │     │  └─────────────┘ │
│  │  │  • core/        │   │  │  │  • websocket.py │     │                  │
│  │  │  • queue/       │   │  │  │  • routers/     │     │                  │
│  │  │  • tenant/      │   │  │  │  • scripts/     │     │                  │
│  │  │  • prompts/     │   │  │  │                 │     │                  │
│  │  │  • events/      │   │  │  └─────────────────┘     │                  │
│  │  │  • backend/     │   │  │                          │                  │
│  │  │  • config/      │   │  │  Regular project         │                  │
│  │  └─────────────────┘   │  │  (no src-layout)         │                  │
│  │                        │  │                          │                  │
│  │  src-layout            │  │  Uses: uv + FastAPI      │                  │
│  │  Uses: uv workspace    │  │                          │                  │
│  └─────────────────────────┘  └─────────────────────────┘                  │
│                                                                             │
│  Dependencies:                                                              │
│  • service depends on SDK (datacloud-agent)                                 │
│  • UI connects to service via LangGraph API                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. SDK 层 (datacloud-agent/)

### 3.1 目录结构

```
datacloud-agent/
├── src/datacloud_agent/           # SDK 源码 (src-layout)
│   ├── __init__.py                # 包入口，导出主要 API
│   ├── __version__.py             # 版本信息
│   │
│   ├── api/                       # 用户-facing API 层
│   │   ├── __init__.py
│   │   ├── client.py              # GatewayClient (高级 API)
│   │   ├── types.py               # ChatResponse, ChatChunk 等数据类型
│   │   └── exceptions.py          # 自定义异常
│   │
│   ├── core/                      # 核心引擎层
│   │   ├── __init__.py
│   │   ├── session.py             # SessionManager (租户感知)
│   │   ├── registry.py            # AgentRegistry
│   │   ├── runner.py              # AgentRunner (队列集成)
│   │   └── router.py              # CommandRouter (斜杠命令)
│   │
│   ├── queue/                     # 消息队列系统
│   │   ├── __init__.py
│   │   ├── types.py               # QueueMode, QueueState, QueuedMessage
│   │   ├── manager.py             # QueueManager
│   │   ├── enqueuer.py            # MessageEnqueuer
│   │   ├── drainer.py             # QueueDrainer
│   │   └── policy.py              # QueuePolicy
│   │
│   ├── tenant/                    # 多租户支持
│   │   ├── __init__.py
│   │   ├── context.py             # TenantContext (contextvars)
│   │   ├── resolver.py            # TenantResolver
│   │   └── workspace.py           # TenantWorkspaceManager
│   │
│   ├── prompts/                   # 系统提示词构建
│   │   ├── __init__.py
│   │   ├── builder.py             # SystemPromptBuilder
│   │   ├── loader.py              # 四层文件加载器
│   │   └── types.py               # PromptConfig, LayerType
│   │
│   ├── events/                    # 事件系统
│   │   ├── __init__.py
│   │   ├── emitter.py             # EventEmitter
│   │   └── types.py               # Event, EventType
│   │
│   ├── backend/                   # 存储后端
│   │   ├── __init__.py
│   │   ├── composite.py           # TenantAwareFileBackend
│   │   └── session_store.py       # 会话持久化 (JSONL)
│   │
│   ├── config/                    # 配置管理
│   │   ├── __init__.py
│   │   ├── models.py              # Pydantic 配置模型
│   │   └── loader.py              # 配置文件加载
│   │
│   └── utils/                     # 工具函数
│       ├── __init__.py
│       ├── dedupe.py              # DedupeCache
│       └── debounce.py            # InboundDebouncer
│
├── tests/                         # 测试目录
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api/
│   ├── test_core/
│   ├── test_queue/
│   └── test_tenant/
│
├── docs/                          # 文档
│   └── README.md
│
├── pyproject.toml                 # uv workspace 配置
└── README.md                      # SDK 说明
```

### 3.2 关键设计

#### 3.2.1 SDK 职责边界

**SDK 做的事情**:
- ✅ 提供编程接口 (`GatewayClient`)
- ✅ 会话管理 (`SessionManager`)
- ✅ Agent 注册与创建 (`AgentRegistry`)
- ✅ 队列系统 (`QueueManager`)
- ✅ 多租户上下文 (`TenantContext`)
- ✅ 系统提示词构建 (`SystemPromptBuilder`)
- ✅ 与 deepagents 集成

**SDK 不做的事情**:
- ❌ HTTP 服务
- ❌ WebSocket 服务
- ❌ 进程管理
- ❌ 网络层认证

#### 3.2.2 与 deepagents 的关系

```
┌─────────────────────────────────────┐
│         datacloud_agent             │
│  ┌─────────────────────────────┐   │
│  │  api.GatewayClient          │   │  ← 用户直接使用
│  └─────────────┬───────────────┘   │
│                │                    │
│  ┌─────────────▼───────────────┐   │
│  │  core.AgentRunner           │   │  ← 队列 + 执行编排
│  └─────────────┬───────────────┘   │
│                │                    │
│  ┌─────────────▼───────────────┐   │
│  │  deepagents.create_agent()  │   │  ← LangGraph 执行层
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

#### 3.2.3 多租户设计

租户上下文通过 `contextvars` 贯穿整个调用链：

```python
# tenant/context.py
import contextvars
from dataclasses import dataclass

tenant_ctx: contextvars.ContextVar['TenantContext'] = contextvars.ContextVar('tenant_ctx')

@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    tenant_type: str  # "public" | "user_public" | "user_private"
    session_id: Optional[str] = None
    task_id: Optional[str] = None
```

三层根目录结构：
```
workspaces/
├── public/                          # 应用级 (所有租户共享)
├── {tenantId}_public/               # 租户级共享
└── {tenantId}_private/.datacloud/workspaces/  # 租户私有
    └── session-{id}/
        ├── skills/
        ├── cache/
        └── tasks/task-{id}/
```

#### 3.2.4 队列系统

6 种队列模式：
- `STEER` - 立即注入当前运行 (LangGraph interrupt)
- `FOLLOWUP` - 当前运行结束后处理
- `COLLECT` - 合并多条消息 (默认)
- `STEER_BACKLOG` - steer + followup
- `INTERRUPT` - 中止当前运行
- `QUEUE` - 通用队列

---

## 4. Service 层 (service/datacloud-agent-service/)

### 4.1 目录结构

```
service/
└── datacloud-agent-service/         # 服务目录 (普通项目结构，无 src-layout)
    ├── README.md                    # 服务说明
    ├── pyproject.toml               # uv 配置
    ├── uv.lock                      # uv 锁定文件
    │
    ├── server.py                    # FastAPI 主入口
    ├── websocket.py                 # WebSocket 处理
    ├── lifespan.py                  # 服务生命周期 (启动/关闭)
    ├── deps.py                      # FastAPI dependencies
    ├── config.py                    # 服务配置
    │
    ├── routers/                     # API 路由
    │   ├── __init__.py
    │   ├── chat.py                  # /v1/chat/completions
    │   ├── sessions.py              # /v1/sessions/*
    │   ├── agents.py                # /v1/agents/*
    │   └── langgraph.py             # LangGraph API 兼容 (给 UI 用)
    │
    ├── middleware/                  # 中间件
    │   ├── __init__.py
    │   └── tenant.py                # 租户解析中间件
    │
    └── scripts/                     # 启动脚本
        ├── start.sh                 # 启动服务
        └── start_with_ui.sh         # 启动服务 + UI
```

### 4.2 关键设计

#### 4.2.1 Service 职责边界

**Service 做的事情**:
- ✅ HTTP API (OpenAI 兼容)
- ✅ WebSocket 实时通信
- ✅ LangGraph API 兼容 (供 deep-agents-ui 使用)
- ✅ 多租户 HTTP 中间件
- ✅ 与 SDK 集成

**Service 不做的事情**:
- ❌ 核心 Agent 逻辑 (由 SDK 提供)
- ❌ 队列系统实现 (由 SDK 提供)
- ❌ 会话持久化 (由 SDK 提供)

#### 4.2.2 LangGraph API 兼容性

为了让 deep-agents-ui 可以直接连接，Service 需要实现 LangGraph API 的子集：

```python
# routers/langgraph.py

@app.get("/ok")
async def health_check():
    """LangGraph 健康检查"""
    return {"status": "ok"}

@app.post("/threads")
async def create_thread():
    """创建会话 (对应我们的 session)"""
    session = await session_manager.create_session(...)
    return {"thread_id": session.session_id}

@app.post("/threads/{thread_id}/runs")
async def create_run(thread_id: str, request: RunRequest):
    """创建运行 (对应我们的 chat)"""
    # 转换为 GatewayClient 调用
    ...
```

UI 配置：
- Deployment URL: `http://127.0.0.1:2024`
- Assistant ID: `gateway`

#### 4.2.3 项目配置 (pyproject.toml)

```toml
[project]
name = "datacloud-agent-service"
version = "0.1.0"
description = "DataCloud Agent Service - HTTP/WebSocket API"
requires-python = ">=3.12"
dependencies = [
    "datacloud-agent",           # workspace 依赖
    "fastapi>=0.100",
    "websockets>=12.0",
    "uvicorn>=0.24",
    "python-multipart>=0.0.6",
]

[tool.uv.sources]
datacloud-agent = { workspace = true }

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "httpx>=0.25",
]

[project.scripts]
datacloud-agent-service = "server:main"
```

注意：使用普通项目结构（非 src-layout），`packages = ["."]` 表示当前目录就是包根。

---

## 5. UI 层 (ui/deep-agents-ui/)

### 5.1 目录结构

```
ui/
└── deep-agents-ui/                # Git 子模块
    ├── package.json
    ├── src/
    ├── public/
    └── ...
```

### 5.2 集成方式

1. **Git 子模块管理**
   ```bash
   git submodule add https://github.com/langchain-ai/deep-agents-ui.git ui/deep-agents-ui
   ```

2. **启动方式**
   ```bash
   # 从 service 目录启动
   cd service/datacloud-agent-service
   ./scripts/start_with_ui.sh
   ```

3. **UI 配置**
   打开 http://localhost:3000 后输入：
   - Deployment URL: `http://127.0.0.1:2024`
   - Assistant ID: `gateway`

---

## 6. Workspace 配置

### 6.1 根 pyproject.toml

```toml
[tool.uv.workspace]
members = [
    "datacloud-agent",
    "datacloud-data-service",
    "datacloud-knowledge-service",
    "datacloud-memory",
    "service/datacloud-agent-service",  # 服务作为 workspace 成员
]

[tool.uv.sources]
datacloud-agent = { workspace = true }
datacloud-data-service = { workspace = true }
datacloud-knowledge-service = { workspace = true }
datacloud-memory = { workspace = true }
```

### 6.2 依赖关系

```
datacloud-agent-service
    └── depends on: datacloud-agent (SDK)
        └── depends on: deepagents (external)
                         datacloud-knowledge-service
                         datacloud-data-service
                         datacloud-memory
```

---

## 7. 实现阶段 (MVP)

### Phase 1: SDK 核心 (1-2 天)
- [ ] `SessionManager` - 会话管理
- [ ] `AgentRegistry` - Agent 注册表
- [ ] `AgentRunner` - 基础运行器（无队列）
- [ ] `GatewayClient` - 高级 API

### Phase 2: 多租户基础 (1 天)
- [ ] `TenantContext` - 租户上下文 (contextvars)
- [ ] `TenantResolver` - 租户解析
- [ ] 三层根目录结构

### Phase 3: 四层文件架构 (1 天)
- [ ] `SystemPromptBuilder` - 系统提示词构建
- [ ] 四层文件加载器

### Phase 4: 简化队列 (1-2 天)
- [ ] `QueueManager` - 队列管理
- [ ] `COLLECT` 模式 - 合并消息
- [ ] `STEER` 模式 - LangGraph interrupt

### Phase 5: Service 层 (1 天)
- [ ] FastAPI 应用框架
- [ ] WebSocket 支持
- [ ] LangGraph 兼容路由

### Phase 6: UI 集成 (0.5 天)
- [ ] 验证 deep-agents-ui 连通性
- [ ] 一键启动脚本

### Phase 7: 可观测性 (0.5 天)
- [ ] 结构化日志
- [ ] 健康检查端点
- [ ] 错误处理

---

## 8. 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| **SDK/Service 分离** | 完全分离 | SDK 可嵌入其他项目，Service 可独立部署 |
| **Service 项目结构** | 普通项目 (无 src-layout) | 服务层代码简单，不需要 src-layout 隔离 |
| **多租户隔离** | 路径隔离 + contextvars | 简单、无数据库依赖、符合文件管理规范 |
| **队列实现** | 基于 LangGraph interrupt | 复用框架能力，避免自定义调度器 |
| **UI 集成** | LangGraph API 兼容 | deep-agents-ui 零改动对接 |
| **依赖管理** | uv workspace | 统一锁定文件，子项目相互引用 |

---

## 9. 风险与注意事项

### 9.1 技术风险

1. **Tenant-ID 信任问题**
   - 设计假设上游已认证
   - 服务层需要验证 tenant_id 合法性

2. **ContextVar 传播**
   - 线程/子进程需手动传递租户上下文
   - 避免隔离泄漏

3. **并发文件访问**
   - 多实例写入同一目录需协调
   - 考虑文件锁或共享后端

4. **LangGraph 版本漂移**
   - 锁定依赖版本
   - 增加契约测试

### 9.2 实现建议

1. **先简化队列**
   - 初期只实现 COLLECT 和 STEER 两种模式
   - 其他模式后续迭代

2. **早期添加测试**
   - SDK 层单元测试
   - Service 层集成测试
   - UI 端到端测试

3. **文档同步**
   - API 文档随代码更新
   - 使用示例保持可运行

---

## 10. 附录

### 10.1 参考文档

- OpenClaw Gateway 设计文档: `/openclaw_gateway_python设计/`
- datacloud-agent 现有代码: `/datacloud-agent/`
- deep-agents-ui: https://github.com/langchain-ai/deep-agents-ui

### 10.2 术语表

| 术语 | 说明 |
|------|------|
| SDK | Software Development Kit，软件开发工具包 |
| Service | HTTP/WebSocket 服务层 |
| UI | User Interface，此处指 deep-agents-ui |
| Tenant | 租户，多租户架构中的隔离单元 |
| Queue Mode | 队列模式，消息处理策略 |
| Four-layer | 四层文件架构：app → user → session → task |

---

## 11. 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0 | 2026-03-09 | 初始版本，架构设计确定 |
