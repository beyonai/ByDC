# OpenClaw Gateway Python 实现 - 工作计划

## TL;DR

> **目标**: 基于 datacloud-agent SDK 构建 OpenClaw Gateway Python 实现
> 
> **核心交付物**:
> - SDK 核心模块 (api/, core/, queue/, tenant/, prompts/, events/, backend/, config/)
> - Service 层 (FastAPI + WebSocket)
> - 完整测试套件
> - 集成 deep-agents-ui
> 
> **Estimated Effort**: Large (7-8 天)
> **Parallel Execution**: YES - 4 Waves
> **Critical Path**: Wave 1 → Wave 2 → Wave 3 → Wave 4

---

## Context

### Original Request
基于 @docs/openclaw-gateway-architecture.md 和 @openclaw_gateway_python设计/ 目录下的设计文档，实现 OpenClaw Gateway Python 版本。

### 设计文档要点
1. **SDK 级 API**: 提供 Python 库而非独立服务
2. **多 Agent 切换**: 支持斜杠命令（`/model`, `/reset`, `/help` 等）
3. **多租户架构**: 基于工作空间路径的租户隔离
4. **队列系统**: 6 种队列模式
5. **四层文件架构**: SystemPromptBuilder 支持身份层/操作层/知识层/协作层
6. **Service 层分离**: HTTP/WebSocket 服务作为独立组件

### 现有代码状态
- datacloud-agent workspace 已配置
- 已有 deepagents 使用示例 (content_writer.py)
- 需要从零开始实现 SDK 核心功能

---

## Work Objectives

### Core Objective
构建一个功能完整的 OpenClaw Gateway Python SDK，提供多租户、多 Agent、队列系统支持，并配套 Service 层供 UI 集成。

### Concrete Deliverables
- `datacloud-agent/src/datacloud_agent/api/` - GatewayClient, types, exceptions
- `datacloud-agent/src/datacloud_agent/core/` - SessionManager, AgentRegistry, AgentRunner, CommandRouter
- `datacloud-agent/src/datacloud_agent/queue/` - 完整队列系统实现
- `datacloud-agent/src/datacloud_agent/tenant/` - 多租户支持
- `datacloud-agent/src/datacloud_agent/prompts/` - SystemPromptBuilder
- `datacloud-agent/src/datacloud_agent/events/` - EventEmitter
- `datacloud-agent/src/datacloud_agent/backend/` - 存储后端
- `datacloud-agent/src/datacloud_agent/config/` - 配置管理
- `service/datacloud-agent-service/` - FastAPI + WebSocket 服务

### Definition of Done
- [ ] 所有 SDK 模块实现并通过单元测试
- [ ] Service 层运行，可通过 HTTP/WebSocket 访问
- [ ] deep-agents-ui 可连接并正常工作
- [ ] 斜杠命令 (`/model`, `/reset`, `/help`) 正常工作
- [ ] 多租户隔离正确工作
- [ ] 队列系统 (至少 COLLECT 和 STEER 模式) 正常工作

### Must Have
- GatewayClient 高级 API
- SessionManager 会话管理
- AgentRegistry Agent 注册表
- CommandRouter 斜杠命令
- TenantContext 多租户上下文
- QueueManager 队列管理 (COLLECT + STEER 模式)
- SystemPromptBuilder 四层文件架构
- FastAPI Service 层

### Must NOT Have (Guardrails)
- 不实现完整的 6 种队列模式 (Phase 1 只实现 COLLECT + STEER)
- 不实现分布式队列后端 (Redis)
- 不实现高级认证/授权 (仅通过 tenant_id 隔离)
- 不实现工具执行 sandbox
- 不实现子 Agent 完整支持

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (pytest 已配置)
- **Automated tests**: TDD (RED-GREEN-REFACTOR)
- **Framework**: pytest + pytest-asyncio
- **Coverage target**: >80%

### QA Policy
Every task MUST include agent-executed QA scenarios:
- **Python 模块**: Import test + function call + assertion
- **API 端点**: curl/httpx request + response assertion
- **Integration**: End-to-end flow verification

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - Start Immediately):
├── T1: Project structure setup
├── T2: Config module (Pydantic models)
├── T3: Event system (EventEmitter)
├── T4: Tenant context (TenantContext, contextvars)
└── T5: Backend storage (TenantAwareFileBackend)

Wave 2 (Core SDK - After Wave 1):
├── T6: SessionManager
├── T7: AgentRegistry
├── T8: CommandRouter
├── T9: Queue types and manager
├── T10: Message enqueuer and drainer
└── T11: AgentRunner (basic)

Wave 3 (Advanced Features - After Wave 2):
├── T12: SystemPromptBuilder (four-layer)
├── T13: STEER mode implementation
├── T14: GatewayClient (high-level API)
└── T15: SDK integration tests

Wave 4 (Service Layer - After Wave 3):
├── T16: FastAPI app structure
├── T17: HTTP API routes
├── T18: WebSocket support
├── T19: LangGraph compatibility routes
└── T20: Service integration tests

Wave 5 (UI Integration - After Wave 4):
├── T21: deep-agents-ui submodule setup
├── T22: Start scripts
└── T23: E2E verification

Wave FINAL (Verification):
├── TF1: Plan compliance audit
├── TF2: Code quality review
└── TF3: Final integration test
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| T1 | - | T2-T5 |
| T2 | T1 | T6-T11 |
| T3 | T1 | T11, T14 |
| T4 | T1 | T5, T6, T8 |
| T5 | T1, T4 | T6, T11 |
| T6 | T2, T4, T5 | T11, T14 |
| T7 | T2 | T11, T14 |
| T8 | T2, T4 | T11, T14 |
| T9 | T2 | T10, T11 |
| T10 | T9 | T11 |
| T11 | T3, T5, T6, T7, T8, T10 | T13, T14 |
| T12 | T2 | T14 |
| T13 | T11 | T14 |
| T14 | T3, T6, T7, T8, T11, T12, T13 | T16-T20 |
| T15 | T14 | TF1-TF3 |
| T16-T20 | T14 | T21-T23 |
| T21-T23 | T16-T20 | TF1-TF3 |

---

## TODOs

### Wave 1: Foundation

- [x] **T1. Project Structure Setup**

  **What to do**:
  - Create SDK directory structure under `datacloud-agent/src/datacloud_agent/`
  - Create subdirectories: api/, core/, queue/, tenant/, prompts/, events/, backend/, config/, utils/
  - Create `__init__.py` files with proper exports
  - Update `datacloud-agent/pyproject.toml` if needed

  **Must NOT do**:
  - Don't implement any logic yet, just structure
  - Don't create Service layer yet

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: T2-T5
  - **Blocked By**: None

  **References**:
  - `docs/openclaw-gateway-architecture.md:63-137` - SDK directory structure
  - `datacloud-agent/pyproject.toml` - Current project config

  **Acceptance Criteria**:
  - [ ] Directory structure matches design doc
  - [ ] All `__init__.py` files exist
  - [ ] `python -c "from datacloud_agent import __version__"` works

  **QA Scenarios**:
  ```
  Scenario: Verify directory structure
    Tool: Bash
    Steps:
      1. ls datacloud-agent/src/datacloud_agent/api/
      2. ls datacloud-agent/src/datacloud_agent/core/
      3. ls datacloud-agent/src/datacloud_agent/queue/
    Expected: All directories exist with __init__.py
  ```

  **Commit**: YES
  - Message: `chore(structure): setup SDK directory structure`
  - Files: `datacloud-agent/src/datacloud_agent/**/__init__.py`

- [x] **T2. Config Module (Pydantic Models)**

  **What to do**:
  - Implement `datacloud_agent/config/models.py` with Pydantic models:
    - `GatewayConfig` - 主配置
    - `MessagesConfig` - 消息处理配置
    - `InboundConfig` - 入站消息配置
    - `QueueConfig` - 队列配置
    - `AgentConfig` - Agent 配置
  - Implement `datacloud_agent/config/loader.py` - 配置文件加载
  - Support YAML/JSON config files

  **Must NOT do**:
  - Don't implement env var override yet
  - Don't validate file paths exist

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T3, T4, T5)
  - **Parallel Group**: Wave 1
  - **Blocks**: T6-T11
  - **Blocked By**: T1

  **References**:
  - `openclaw_gateway_python设计/5-配置设计.md:1-106` - Config structure
  - `openclaw_gateway_python设计/10-队列与消息处理系统实现.md:797-833` - Config classes

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_config.py`
  - [ ] `pytest datacloud-agent/tests/test_config.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Load config from dict
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         from datacloud_agent.config import GatewayConfig
         config = GatewayConfig(port=8080)
         print(config.port)
         "
    Expected: Output "8080"
  
  Scenario: Config validation fails on invalid data
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         from datacloud_agent.config import GatewayConfig
         GatewayConfig(port='invalid')
         " 2>&1
    Expected: ValidationError raised
  ```

  **Commit**: YES
  - Message: `feat(config): add pydantic config models`
  - Files: `datacloud-agent/src/datacloud_agent/config/*.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_config.py`

- [x] **T3. Event System (EventEmitter)**

  **What to do**:
  - Implement `datacloud_agent/events/types.py` - Event, EventType enums
  - Implement `datacloud_agent/events/emitter.py` - EventEmitter class
  - Support:
    - Callback registration (`on_event`, `off_event`)
    - Async event emission
    - Event history (circular buffer)
    - Event filtering

  **Must NOT do**:
  - Don't implement persistent event storage
  - Don't implement event replay from disk

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T2, T4, T5)
  - **Parallel Group**: Wave 1
  - **Blocks**: T11, T14
  - **Blocked By**: T1

  **References**:
  - `openclaw_gateway_python设计/3-核心组件设计-SDK版本.md:359-407` - EventEmitter design

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_events.py`
  - [ ] `pytest datacloud-agent/tests/test_events.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Register and emit event
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         import asyncio
         from datacloud_agent.events import EventEmitter
         
         emitter = EventEmitter()
         received = []
         
         async def handler(event):
             received.append(event)
         
         emitter.on_event(handler)
         asyncio.run(emitter.emit({'type': 'test', 'data': 'hello'}))
         print(received[0]['data'])
         "
    Expected: Output "hello"
  ```

  **Commit**: YES
  - Message: `feat(events): implement EventEmitter`
  - Files: `datacloud-agent/src/datacloud_agent/events/*.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_events.py`

- [x] **T4. Tenant Context (contextvars)**

  **What to do**:
  - Implement `datacloud_agent/tenant/types.py` - TenantType enum
  - Implement `datacloud_agent/tenant/context.py`:
    - `TenantContext` dataclass (tenant_id, tenant_type, session_id, task_id)
    - `tenant_ctx` ContextVar
    - Helper methods for path resolution
  - Implement `datacloud_agent/tenant/resolver.py` - TenantResolver

  **Must NOT do**:
  - Don't implement actual file operations yet
  - Don't implement permission checks

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T2, T3, T5)
  - **Parallel Group**: Wave 1
  - **Blocks**: T5, T6, T8
  - **Blocked By**: T1

  **References**:
  - `openclaw_gateway_python设计/12-多租户与文件空间设计.md:135-261` - TenantContext design

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_tenant.py`
  - [ ] `pytest datacloud-agent/tests/test_tenant.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: ContextVar isolation
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         import asyncio
         from datacloud_agent.tenant import TenantContext, tenant_ctx
         
         async def task1():
             token = TenantContext(tenant_id='A', tenant_type='user_private').scoped()
             await asyncio.sleep(0.1)
             result = tenant_ctx.get().tenant_id
             TenantContext.reset(token)
             return result
         
         async def task2():
             token = TenantContext(tenant_id='B', tenant_type='user_private').scoped()
             await asyncio.sleep(0.05)
             result = tenant_ctx.get().tenant_id
             TenantContext.reset(token)
             return result
         
         results = asyncio.gather(task1(), task2())
         print(list(asyncio.run(results)))
         "
    Expected: Output "['A', 'B']" (contexts are isolated)
  ```

  **Commit**: YES
  - Message: `feat(tenant): implement TenantContext with contextvars`
  - Files: `datacloud-agent/src/datacloud_agent/tenant/*.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_tenant.py`

- [x] **T5. Backend Storage (TenantAwareFileBackend)**

  **What to do**:
  - Implement `datacloud_agent/backend/composite.py`:
    - `TenantAwareFileBackend` class
    - Route operations based on path prefix
    - Support public/user_public/user_private paths
  - Implement `datacloud_agent/backend/session_store.py`:
    - JSONL-based session persistence
    - Append-only write
    - Read with filtering

  **Must NOT do**:
  - Don't implement file locking yet
  - Don't implement compression

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T2, T3, T4)
  - **Parallel Group**: Wave 1
  - **Blocks**: T6, T11
  - **Blocked By**: T1, T4

  **References**:
  - `openclaw_gateway_python设计/12-多租户与文件空间设计.md:486-557` - TenantAwareFileBackend
  - `openclaw_gateway_python设计/6-关键实现细节.md:111-119` - JSONL format

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_backend.py`
  - [ ] `pytest datacloud-agent/tests/test_backend.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Write and read session data
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         import asyncio
         import tempfile
         from datacloud_agent.backend import SessionStore
         
         async def test():
             with tempfile.TemporaryDirectory() as tmp:
                 store = SessionStore(tmp)
                 await store.append('session-1', {'type': 'message', 'content': 'hello'})
                 records = await store.read('session-1')
                 print(records[0]['content'])
         
         asyncio.run(test())
         "
    Expected: Output "hello"
  ```

  **Commit**: YES
  - Message: `feat(backend): implement tenant-aware file backend`
  - Files: `datacloud-agent/src/datacloud_agent/backend/*.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_backend.py`

### Wave 2: Core SDK

- [x] **T6. SessionManager**

  **What to do**:
  - Implement `datacloud_agent/core/session.py`:
    - `Session` dataclass (session_id, session_key, tenant_id, agent_id, etc.)
    - `SessionManager` class
    - Session key format: `tenant:{tenantId}:agent:{agentId}:{mainKey}`
    - In-memory session storage with optional JSONL persistence
    - Methods: `create_session`, `get_session`, `get_or_create_session`, `reset_session`

  **Must NOT do**:
  - Don't implement distributed session storage
  - Don't implement session expiration/timeout

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Wave 1)
  - **Parallel Group**: Wave 2
  - **Blocks**: T11, T14
  - **Blocked By**: T2, T4, T5

  **References**:
  - `openclaw_gateway_python设计/3-核心组件设计-SDK版本.md:409-415` - SessionManager
  - `openclaw_gateway_python设计/12-多租户与文件空间设计.md:339-480` - TenantAwareSessionManager

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_session.py`
  - [ ] `pytest datacloud-agent/tests/test_session.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Create and retrieve session
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         import asyncio
         from datacloud_agent.core import SessionManager
         from datacloud_agent.tenant import TenantContext
         
         async def test():
             manager = SessionManager()
             ctx = TenantContext(tenant_id='user_001', tenant_type='user_private')
             session = await manager.create_session(ctx, agent_id='default')
             retrieved = await manager.get_session(session.session_key)
             print(retrieved.agent_id)
         
         asyncio.run(test())
         "
    Expected: Output "default"
  ```

  **Commit**: YES
  - Message: `feat(session): implement SessionManager`
  - Files: `datacloud-agent/src/datacloud_agent/core/session.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_session.py`

- [x] **T7. AgentRegistry**

  **What to do**:
  - Implement `datacloud_agent/core/registry.py`:
    - `AgentRegistry` class
    - Load agent configs from YAML
    - `create_agent()` method using deepagents
    - Support provider/model override
    - List available agents

  **Must NOT do**:
  - Don't implement dynamic agent reloading
  - Don't implement agent versioning

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T6, T8, T9, T10)
  - **Parallel Group**: Wave 2
  - **Blocks**: T11, T14
  - **Blocked By**: T2

  **References**:
  - `openclaw_gateway_python设计/3-核心组件设计-SDK版本.md:416-419` - AgentRegistry
  - `openclaw_gateway_python设计/6-关键实现细节.md:1-109` - deepagents integration
  - `datacloud-agent/src/datacloud_agent/agent/content_writer.py:167-184` - create_deep_agent example

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_registry.py`
  - [ ] `pytest datacloud-agent/tests/test_registry.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: List agents from config
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         from datacloud_agent.core import AgentRegistry
         
         registry = AgentRegistry()
         # Mock config loading
         registry._agents = {
             'default': {'name': 'Default', 'model': 'claude-sonnet-4-6'},
             'coder': {'name': 'Coder', 'model': 'claude-opus-4'}
         }
         agents = registry.list_agents()
         print([a['id'] for a in agents])
         "
    Expected: Output "['default', 'coder']"
  ```

  **Commit**: YES
  - Message: `feat(registry): implement AgentRegistry`
  - Files: `datacloud-agent/src/datacloud_agent/core/registry.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_registry.py`

- [x] **T8. CommandRouter**

  **What to do**:
  - Implement `datacloud_agent/core/router.py`:
    - `CommandRouter` class
    - Parse slash commands: `/model`, `/reset`, `/help`
    - `CommandResult` dataclass
    - Command handlers registry
    - Support command arguments

  **Must NOT do**:
  - Don't implement custom command registration yet
  - Don't implement command aliases

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T6, T7, T9, T10)
  - **Parallel Group**: Wave 2
  - **Blocks**: T11, T14
  - **Blocked By**: T2, T4

  **References**:
  - `openclaw_gateway_python设计/3-核心组件设计-SDK版本.md:420-423` - CommandRouter

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_router.py`
  - [ ] `pytest datacloud-agent/tests/test_router.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Parse /model command
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         from datacloud_agent.core import CommandRouter
         
         router = CommandRouter()
         result = router.parse_command('/model coder')
         print(result.command if result else 'None')
         "
    Expected: Output "model"
  ```

  **Commit**: YES
  - Message: `feat(router): implement CommandRouter`
  - Files: `datacloud-agent/src/datacloud_agent/core/router.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_router.py`

- [x] **T9. Queue Types and Manager**

  **What to do**:
  - Implement `datacloud_agent/queue/types.py`:
    - `QueueMode` enum (STEER, FOLLOWUP, COLLECT, STEER_BACKLOG, INTERRUPT, QUEUE)
    - `DropPolicy` enum (OLD, NEW, SUMMARIZE)
    - `QueueSettings` dataclass
    - `QueuedMessage` dataclass
    - `QueueState` dataclass
  - Implement `datacloud_agent/queue/manager.py`:
    - `QueueManager` class
    - Per-session queue storage
    - Async lock management

  **Must NOT do**:
  - Don't implement distributed queue yet
  - Don't implement queue persistence

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T6, T7, T8, T10)
  - **Parallel Group**: Wave 2
  - **Blocks**: T10, T11
  - **Blocked By**: T2

  **References**:
  - `openclaw_gateway_python设计/10-队列与消息处理系统实现.md:1-71` - Queue types
  - `openclaw_gateway_python设计/10-队列与消息处理系统实现.md:137-212` - QueueManager

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_queue_types.py`
  - [ ] `pytest datacloud-agent/tests/test_queue_types.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Create and retrieve queue
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         from datacloud_agent.queue import QueueManager, QueueSettings, QueueMode
         
         manager = QueueManager()
         settings = QueueSettings(mode=QueueMode.COLLECT)
         queue = manager.get_or_create('session-1', settings)
         print(queue.mode.value)
         "
    Expected: Output "collect"
  ```

  **Commit**: YES
  - Message: `feat(queue): implement queue types and manager`
  - Files: `datacloud-agent/src/datacloud_agent/queue/types.py`, `manager.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_queue_types.py`

- [x] **T10. Message Enqueuer and Drainer**

  **What to do**:
  - Implement `datacloud_agent/queue/enqueuer.py`:
    - `MessageEnqueuer` class
    - Deduplication logic
    - Drop policy application
  - Implement `datacloud_agent/queue/drainer.py`:
    - `QueueDrainer` class
    - Background drain task
    - COLLECT mode: merge messages
    - Individual mode: process one by one

  **Must NOT do**:
  - Don't implement STEER mode yet (T13)
  - Don't implement complex scheduling

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T6, T7, T8, T9)
  - **Parallel Group**: Wave 2
  - **Blocks**: T11
  - **Blocked By**: T9

  **References**:
  - `openclaw_gateway_python设计/10-队列与消息处理系统实现.md:214-323` - MessageEnqueuer
  - `openclaw_gateway_python设计/10-队列与消息处理系统实现.md:325-452` - QueueDrainer

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_queue_ops.py`
  - [ ] `pytest datacloud-agent/tests/test_queue_ops.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Enqueue and drain message
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         import asyncio
         from datacloud_agent.queue import QueueManager, MessageEnqueuer, QueueDrainer, QueueSettings, QueuedMessage
         
         async def test():
             manager = QueueManager()
             enqueuer = MessageEnqueuer(manager)
             drainer = QueueDrainer(manager)
             
             settings = QueueSettings()
             msg = QueuedMessage(prompt='hello', session_key='s1')
             
             success = await enqueuer.enqueue('s1', msg, settings)
             print(f'enqueued: {success}')
         
         asyncio.run(test())
         "
    Expected: Output "enqueued: True"
  ```

  **Commit**: YES
  - Message: `feat(queue): implement enqueuer and drainer`
  - Files: `datacloud-agent/src/datacloud_agent/queue/enqueuer.py`, `drainer.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_queue_ops.py`

- [x] **T11. AgentRunner (Basic)**

  **What to do**:
  - Implement `datacloud_agent/core/runner.py`:
    - `AgentRunner` class
    - Integrate with QueueManager, MessageEnqueuer, QueueDrainer
    - Handle inbound deduplication (DedupeCache)
    - Handle debouncing (InboundDebouncer)
    - Basic run flow: check active → decide action → execute or enqueue
    - Support COLLECT and FOLLOWUP modes

  **Must NOT do**:
  - Don't implement STEER mode yet (T13)
  - Don't implement INTERRUPT yet

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Wave 2)
  - **Parallel Group**: Wave 2
  - **Blocks**: T13, T14
  - **Blocked By**: T3, T5, T6, T7, T8, T10

  **References**:
  - `openclaw_gateway_python设计/10-队列与消息处理系统实现.md:601-795` - QueuedAgentRunner
  - `openclaw_gateway_python设计/3-核心组件设计-SDK版本.md:424-430` - AgentRunner

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_runner.py`
  - [ ] `pytest datacloud-agent/tests/test_runner.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Handle message when no active run
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         import asyncio
         # Mock test - verify runner structure
         from datacloud_agent.core import AgentRunner
         print('AgentRunner imported successfully')
         "
    Expected: Output "AgentRunner imported successfully"
  ```

  **Commit**: YES
  - Message: `feat(runner): implement basic AgentRunner`
  - Files: `datacloud-agent/src/datacloud_agent/core/runner.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_runner.py`

### Wave 3: Advanced Features

- [x] **T12. SystemPromptBuilder (Four-Layer)**

  **What to do**:
  - Implement `datacloud_agent/prompts/types.py`:
    - `LayerType` enum (IDENTITY, OPERATION, KNOWLEDGE, COLLABORATION)
    - `PromptConfig` dataclass
    - `SystemPromptConfig` dataclass
  - Implement `datacloud_agent/prompts/loader.py`:
    - Load four-layer files (SOUL.md, IDENTITY.md, USER.md, AGENTS.md, etc.)
    - Handle file truncation (head/tail ratio)
  - Implement `datacloud_agent/prompts/builder.py`:
    - `SystemPromptBuilder` class
    - Build system prompt from layers
    - Support bootstrap_max_chars

  **Must NOT do**:
  - Don't implement dynamic prompt reloading
  - Don't implement prompt caching yet

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T13)
  - **Parallel Group**: Wave 3
  - **Blocks**: T14
  - **Blocked By**: T2

  **References**:
  - `openclaw_gateway_python设计/5-配置设计.md:108-149` - Four-layer architecture
  - `openclaw_gateway_python设计/3-核心组件设计-SDK版本.md:431-434` - SystemPromptBuilder

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_prompts.py`
  - [ ] `pytest datacloud-agent/tests/test_prompts.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Build system prompt from files
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         import tempfile
         from pathlib import Path
         from datacloud_agent.prompts import SystemPromptBuilder
         
         with tempfile.TemporaryDirectory() as tmp:
             # Create test files
             Path(tmp, 'SOUL.md').write_text('You are a helpful assistant.')
             Path(tmp, 'AGENTS.md').write_text('Always be concise.')
             
             builder = SystemPromptBuilder(tmp)
             prompt = builder.build(agent_id='test', model='claude')
             print('SOUL' in prompt and 'concise' in prompt)
         "
    Expected: Output "True"
  ```

  **Commit**: YES
  - Message: `feat(prompts): implement SystemPromptBuilder`
  - Files: `datacloud-agent/src/datacloud_agent/prompts/*.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_prompts.py`

- [x] **T13. STEER Mode Implementation**

  **What to do**:
  - Extend `datacloud_agent/core/runner.py`:
    - Add STEER mode support using LangGraph interrupt/Command
    - Add STEER_BACKLOG mode
    - Add INTERRUPT mode
    - Track running tasks per session
    - Implement `_steer_run()` method
    - Implement `_interrupt_run()` method
  - Update `datacloud_agent/queue/policy.py`:
    - `QueuePolicy` class for action resolution

  **Must NOT do**:
  - Don't implement complex checkpoint recovery
  - Don't implement distributed steer

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T12)
  - **Parallel Group**: Wave 3
  - **Blocks**: T14
  - **Blocked By**: T11

  **References**:
  - `openclaw_gateway_python设计/11-steer-和-steerbacklog-模式实现.md` - Full STEER implementation

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_steer.py`
  - [ ] `pytest datacloud-agent/tests/test_steer.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: STEER mode resolves correctly
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         from datacloud_agent.queue import QueuePolicy, QueueAction, QueueMode
         
         action = QueuePolicy.resolve(
             is_active=True,
             is_heartbeat=False,
             should_followup=False,
             queue_mode=QueueMode.STEER
         )
         print(action.value)
         "
    Expected: Output "enqueue-followup" (or appropriate action)
  ```

  **Commit**: YES
  - Message: `feat(runner): implement STEER mode`
  - Files: `datacloud-agent/src/datacloud_agent/core/runner.py`, `queue/policy.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_steer.py`

- [x] **T14. GatewayClient (High-Level API)**

  **What to do**:
  - Implement `datacloud_agent/api/types.py`:
    - `ChatResponse` dataclass
    - `ChatChunk` dataclass
  - Implement `datacloud_agent/api/exceptions.py`:
    - Custom exceptions
  - Implement `datacloud_agent/api/client.py`:
    - `GatewayClient` class
    - `chat()` method - sync/blocking API
    - `chat_stream()` method - async iterator
    - `switch_agent()` method
    - `reset_session()` method
    - `list_agents()` method
    - `execute_command()` method
  - Update `datacloud_agent/__init__.py` with exports

  **Must NOT do**:
  - Don't implement sync wrapper (keep it async)
  - Don't implement connection pooling

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Wave 3)
  - **Parallel Group**: Wave 3
  - **Blocks**: T15, T16-T20
  - **Blocked By**: T3, T6, T7, T8, T11, T12, T13

  **References**:
  - `openclaw_gateway_python设计/3-核心组件设计-SDK版本.md:43-328` - GatewayClient design

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/test_client.py`
  - [ ] `pytest datacloud-agent/tests/test_client.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Import GatewayClient
    Tool: Bash (python REPL)
    Steps:
      1. python -c "
         from datacloud_agent import GatewayClient, ChatResponse, ChatChunk
         print('GatewayClient imported successfully')
         "
    Expected: Output "GatewayClient imported successfully"
  ```

  **Commit**: YES
  - Message: `feat(api): implement GatewayClient high-level API`
  - Files: `datacloud-agent/src/datacloud_agent/api/*.py`, `__init__.py`
  - Pre-commit: `pytest datacloud-agent/tests/test_client.py`

- [x] **T15. SDK Integration Tests**

  **What to do**:
  - Create `datacloud-agent/tests/integration/test_sdk_flow.py`:
    - End-to-end test: create client → chat → verify response
    - Test agent switching
    - Test command execution
    - Test queue modes
  - Create test fixtures in `datacloud-agent/tests/conftest.py`
  - Mock deepagents for tests

  **Must NOT do**:
  - Don't test with real LLM calls
  - Don't test file system operations extensively

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Wave 3)
  - **Parallel Group**: Wave 3
  - **Blocks**: TF1-TF3
  - **Blocked By**: T14

  **References**:
  - `openclaw_gateway_python设计/3-核心组件设计-SDK版本.md:469-549` - SDK usage examples

  **Acceptance Criteria**:
  - [ ] Test file: `datacloud-agent/tests/integration/test_sdk_flow.py`
  - [ ] `pytest datacloud-agent/tests/integration/ -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Run integration tests
    Tool: Bash
    Steps:
      1. cd datacloud-agent && pytest tests/integration/ -v --tb=short
    Expected: All tests pass
  ```

  **Commit**: YES
  - Message: `test(integration): add SDK integration tests`
  - Files: `datacloud-agent/tests/integration/*.py`, `conftest.py`
  - Pre-commit: `pytest datacloud-agent/tests/integration/`

### Wave 4: Service Layer

- [x] **T16. FastAPI App Structure**

  **What to do**:
  - Create `service/datacloud-agent-service/` directory
  - Create `pyproject.toml` for service
  - Create basic structure:
    - `server.py` - FastAPI app factory
    - `lifespan.py` - Startup/shutdown lifecycle
    - `config.py` - Service config
    - `deps.py` - FastAPI dependencies
  - Add to root `pyproject.toml` workspace members

  **Must NOT do**:
  - Don't implement routes yet
  - Don't implement auth

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Wave 3)
  - **Parallel Group**: Wave 4
  - **Blocks**: T17-T20
  - **Blocked By**: T14

  **References**:
  - `docs/openclaw-gateway-architecture.md:220-251` - Service structure

  **Acceptance Criteria**:
  - [ ] Service can be imported
  - [ ] `python -c "from server import app"` works

  **QA Scenarios**:
  ```
  Scenario: Import service app
    Tool: Bash
    Steps:
      1. cd service/datacloud-agent-service && python -c "from server import app; print('OK')"
    Expected: Output "OK"
  ```

  **Commit**: YES
  - Message: `feat(service): setup FastAPI app structure`
  - Files: `service/datacloud-agent-service/*.py`, `pyproject.toml`

- [x] **T17. HTTP API Routes**

  **What to do**:
  - Implement `service/datacloud-agent-service/routers/chat.py`:
    - POST /v1/chat/completions (OpenAI compatible)
  - Implement `service/datacloud-agent-service/routers/sessions.py`:
    - POST /v1/sessions
    - GET /v1/sessions/{id}
    - DELETE /v1/sessions/{id}
  - Implement `service/datacloud-agent-service/routers/agents.py`:
    - GET /v1/agents
    - GET /v1/agents/{id}
  - Wire up routers in `server.py`

  **Must NOT do**:
  - Don't implement streaming yet (T18)
  - Don't implement full OpenAI compatibility

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T18, T19)
  - **Parallel Group**: Wave 4
  - **Blocks**: T20
  - **Blocked By**: T16

  **References**:
  - `docs/openclaw-gateway-architecture.md:237-243` - Routers

  **Acceptance Criteria**:
  - [ ] Test file: `service/datacloud-agent-service/tests/test_routes.py`
  - [ ] `pytest service/datacloud-agent-service/tests/test_routes.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Test health endpoint
    Tool: Bash
    Steps:
      1. cd service/datacloud-agent-service
      2. python -c "
         from fastapi.testclient import TestClient
         from server import app
         client = TestClient(app)
         response = client.get('/health')
         print(response.status_code)
         "
    Expected: Output "200"
  ```

  **Commit**: YES
  - Message: `feat(service): implement HTTP API routes`
  - Files: `service/datacloud-agent-service/routers/*.py`
  - Pre-commit: `pytest service/datacloud-agent-service/tests/test_routes.py`

- [x] **T18. WebSocket Support**

  **What to do**:
  - Implement `service/datacloud-agent-service/websocket.py`:
    - WebSocket endpoint `/ws`
    - Connection handler
    - Message parsing (JSON)
    - Integration with GatewayClient
    - Event streaming to WebSocket

  **Must NOT do**:
  - Don't implement binary message support
  - Don't implement custom protocols

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T17, T19)
  - **Parallel Group**: Wave 4
  - **Blocks**: T20
  - **Blocked By**: T16

  **References**:
  - `docs/openclaw-gateway-architecture.md:232` - WebSocket

  **Acceptance Criteria**:
  - [ ] Test file: `service/datacloud-agent-service/tests/test_websocket.py`
  - [ ] `pytest service/datacloud-agent-service/tests/test_websocket.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Test WebSocket connection
    Tool: Bash
    Steps:
      1. cd service/datacloud-agent-service
      2. python -c "
         from fastapi.testclient import TestClient
         from server import app
         client = TestClient(app)
         with client.websocket_connect('/ws') as ws:
             ws.send_json({'method': 'ping'})
             data = ws.receive_json()
             print(data.get('method'))
         "
    Expected: Output "pong" (or appropriate response)
  ```

  **Commit**: YES
  - Message: `feat(service): implement WebSocket support`
  - Files: `service/datacloud-agent-service/websocket.py`
  - Pre-commit: `pytest service/datacloud-agent-service/tests/test_websocket.py`

- [x] **T19. LangGraph Compatibility Routes**

  **What to do**:
  - Implement `service/datacloud-agent-service/routers/langgraph.py`:
    - GET /ok - Health check
    - POST /threads - Create thread (session)
    - POST /threads/{id}/runs - Create run (chat)
    - GET /threads/{id}/history - Get history
  - Map to GatewayClient operations
  - Ensure compatibility with deep-agents-ui

  **Must NOT do**:
  - Don't implement full LangGraph API
  - Don't implement streaming runs yet

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T17, T18)
  - **Parallel Group**: Wave 4
  - **Blocks**: T20
  - **Blocked By**: T16

  **References**:
  - `docs/openclaw-gateway-architecture.md:269-295` - LangGraph API

  **Acceptance Criteria**:
  - [ ] Test file: `service/datacloud-agent-service/tests/test_langgraph.py`
  - [ ] `pytest service/datacloud-agent-service/tests/test_langgraph.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Test LangGraph health endpoint
    Tool: Bash
    Steps:
      1. cd service/datacloud-agent-service
      2. python -c "
         from fastapi.testclient import TestClient
         from server import app
         client = TestClient(app)
         response = client.get('/ok')
         print(response.json().get('status'))
         "
    Expected: Output "ok"
  ```

  **Commit**: YES
  - Message: `feat(service): implement LangGraph compatibility routes`
  - Files: `service/datacloud-agent-service/routers/langgraph.py`
  - Pre-commit: `pytest service/datacloud-agent-service/tests/test_langgraph.py`

- [x] **T20. Service Integration Tests**

  **What to do**:
  - Create `service/datacloud-agent-service/tests/integration/`:
    - Test full HTTP API flow
    - Test WebSocket flow
    - Test LangGraph API compatibility
  - Test with mocked GatewayClient

  **Must NOT do**:
  - Don't test with real LLM
  - Don't test actual file operations

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Wave 4)
  - **Parallel Group**: Wave 4
  - **Blocks**: T21-T23
  - **Blocked By**: T17, T18, T19

  **Acceptance Criteria**:
  - [ ] Test file: `service/datacloud-agent-service/tests/integration/test_service.py`
  - [ ] `pytest service/datacloud-agent-service/tests/integration/ -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Run service integration tests
    Tool: Bash
    Steps:
      1. cd service/datacloud-agent-service
      2. pytest tests/integration/ -v --tb=short
    Expected: All tests pass
  ```

  **Commit**: YES
  - Message: `test(service): add service integration tests`
  - Files: `service/datacloud-agent-service/tests/integration/*.py`
  - Pre-commit: `pytest service/datacloud-agent-service/tests/integration/`

### Wave 5: UI Integration

- [x] **T21. deep-agents-ui Submodule Setup**

  **What to do**:
  - Add deep-agents-ui as git submodule: `ui/deep-agents-ui`
  - Create `.gitmodules` entry
  - Document UI setup in README

  **Must NOT do**:
  - Don't modify UI code
  - Don't commit UI build artifacts

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Wave 4)
  - **Parallel Group**: Wave 5
  - **Blocks**: T22-T23
  - **Blocked By**: T20

  **References**:
  - `docs/openclaw-gateway-architecture.md:331-362` - UI integration

  **Acceptance Criteria**:
  - [ ] Submodule added
  - [ ] `git submodule update --init` works

  **QA Scenarios**:
  ```
  Scenario: Verify submodule
    Tool: Bash
    Steps:
      1. ls ui/deep-agents-ui/package.json
    Expected: File exists
  ```

  **Commit**: YES
  - Message: `chore(ui): add deep-agents-ui submodule`
  - Files: `.gitmodules`, `ui/`

- [x] **T22. Start Scripts**

  **What to do**:
  - Create `service/datacloud-agent-service/scripts/start.sh`:
    - Start FastAPI server
    - Configure port/host
  - Create `service/datacloud-agent-service/scripts/start_with_ui.sh`:
    - Start service
    - Start UI dev server
    - Document usage

  **Must NOT do**:
  - Don't implement production deployment scripts
  - Don't implement Docker

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with T21)
  - **Parallel Group**: Wave 5
  - **Blocks**: T23
  - **Blocked By**: T20

  **References**:
  - `docs/openclaw-gateway-architecture.md:248-251` - Scripts

  **Acceptance Criteria**:
  - [ ] Scripts are executable
  - [ ] Scripts have proper error handling

  **QA Scenarios**:
  ```
  Scenario: Verify scripts exist
    Tool: Bash
    Steps:
      1. ls -la service/datacloud-agent-service/scripts/
    Expected: start.sh and start_with_ui.sh exist
  ```

  **Commit**: YES
  - Message: `feat(service): add start scripts`
  - Files: `service/datacloud-agent-service/scripts/*.sh`

- [x] **T23. E2E Verification**

  **What to do**:
  - Create `docs/usage.md` with:
    - SDK usage examples
    - Service API examples
    - UI configuration guide
  - Verify end-to-end flow:
    1. Start service
    2. Connect UI
    3. Send message
    4. Verify response
  - Document any issues or workarounds

  **Must NOT do**:
  - Don't automate E2E tests with real browser
  - Don't test all edge cases

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Wave 5)
  - **Parallel Group**: Wave 5
  - **Blocks**: TF1-TF3
  - **Blocked By**: T21, T22

  **Acceptance Criteria**:
  - [ ] Documentation complete
  - [ ] Manual E2E test passes

  **QA Scenarios**:
  ```
  Scenario: Documentation exists
    Tool: Bash
    Steps:
      1. ls docs/usage.md
      2. head -20 docs/usage.md
    Expected: File exists with content
  ```

  **Commit**: YES
  - Message: `docs: add usage documentation and E2E verification`
  - Files: `docs/usage.md`

---

## Final Verification Wave

- [x] **TF1. Plan Compliance Audit**

  **What to do**:
  - Verify all TODO items completed
  - Check file structure matches design
  - Verify exports in `__init__.py` files
  - Run full test suite

  **Recommended Agent Profile**:
  - **Category**: `oracle`
  - **Skills**: []

  **Acceptance Criteria**:
  - [ ] All tasks from plan are implemented
  - [ ] `pytest` passes for all modules

  **QA Scenarios**:
  ```
  Scenario: Run all tests
    Tool: Bash
    Steps:
      1. pytest datacloud-agent/tests/ -v
      2. pytest service/datacloud-agent-service/tests/ -v
    Expected: All tests pass
  ```

- [x] **TF2. Code Quality Review**

  **What to do**:
  - Run `ruff check .`
  - Run `mypy datacloud-agent/src/`
  - Fix any issues

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Acceptance Criteria**:
  - [ ] `ruff check .` passes
  - [ ] `mypy` passes (or has acceptable errors)

  **QA Scenarios**:
  ```
  Scenario: Run linters
    Tool: Bash
    Steps:
      1. ruff check datacloud-agent/src/
      2. mypy datacloud-agent/src/
    Expected: No critical errors
  ```

- [x] **TF3. Final Integration Test**

  **What to do**:
  - Run full integration test suite
  - Verify SDK + Service work together
  - Document any remaining issues

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Acceptance Criteria**:
  - [ ] All integration tests pass
  - [ ] Manual smoke test passes

  **QA Scenarios**:
  ```
  Scenario: Full integration test
    Tool: Bash
    Steps:
      1. pytest --tb=short
    Expected: All tests pass
  ```

---

## Commit Strategy

- **Wave 1**: `chore(structure):`, `feat(config):`, `feat(events):`, `feat(tenant):`, `feat(backend):`
- **Wave 2**: `feat(session):`, `feat(registry):`, `feat(router):`, `feat(queue):`, `feat(runner):`
- **Wave 3**: `feat(prompts):`, `feat(runner):`, `feat(api):`, `test(integration):`
- **Wave 4**: `feat(service):`, `test(service):`
- **Wave 5**: `chore(ui):`, `feat(service):`, `docs:`
- **Final**: `chore(quality):`, `test(integration):`

---

## Success Criteria

### Verification Commands
```bash
# SDK tests
pytest datacloud-agent/tests/ -v

# Service tests
pytest service/datacloud-agent-service/tests/ -v

# Linting
ruff check .
mypy datacloud-agent/src/

# Import test
python -c "from datacloud_agent import GatewayClient; print('OK')"
```

### Final Checklist
- [ ] All SDK modules implemented with tests
- [ ] Service layer runs and passes tests
- [ ] GatewayClient high-level API works
- [ ] CommandRouter handles `/model`, `/reset`, `/help`
- [ ] Queue system supports COLLECT and STEER modes
- [ ] Multi-tenant isolation works
- [ ] SystemPromptBuilder loads four-layer files
- [ ] LangGraph API compatibility routes work
- [ ] Code quality checks pass
- [ ] Documentation complete
