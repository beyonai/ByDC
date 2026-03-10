# 3. 核心组件设计（基于 OpenClaw 架构分析）- SDK 版本

> **注意**: 此版本已剥离 WebSocket/HTTP 服务器层，仅提供 SDK 级 API

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│  OpenClaw Gateway SDK (Python)                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │  SDK API Layer (用户直接调用)                      │   │
│  │  - GatewayClient (高级API)                        │   │
│  │  - SessionManager (底层API)                       │   │
│  │  - AgentRunner (底层API)                          │   │
│  └─────────────────────────────────────────────────┘   │
│                         │                               │
│  ┌──────────────────────┼──────────────────────────┐   │
│  │                      ▼                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │   │
│  │  │  Session    │  │   Agent     │  │ Command │ │   │
│  │  │  Manager    │  │   Registry  │  │ Router  │ │   │
│  │  └──────┬──────┘  └──────┬──────┘  └────┬────┘ │   │
│  │         │                │               │      │   │
│  │  ┌──────┴────────────────┴───────────────┘      │   │
│  │  │           Message Queue System               │   │
│  │  │  ┌─────────┐  ┌─────────┐  ┌─────────┐      │   │
│  │  │  │ Enqueue │  │  Drain  │  │ Dedupe  │      │   │
│  │  │  │ Handler │  │ Handler │  │  Cache  │      │   │
│  │  │  └─────────┘  └─────────┘  └─────────┘      │   │
│  │  └─────────────────────────────────────────────┘   │
│  │                      │                            │   │
│  │  ┌───────────────────┴────────────────────────┐   │   │
│  │  │           deepagents SDK                    │   │   │
│  │  │  - create_deep_agent()                      │   │   │
│  │  │  - CompiledStateGraph.invoke()              │   │   │
│  │  │  - Tool calling + Streaming                 │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 3.1 SDK API 设计

### 3.1.1 高级 API - GatewayClient

**设计目标**: 提供最简单的方式使用 Gateway 功能，一行代码即可开始对话。

```python
from openclaw_gateway import GatewayClient, GatewayConfig

# 最简单的使用方式
client = GatewayClient()

# 发送消息并获取响应
response = await client.chat("你好，请帮我写一个Python函数")
print(response.text)

# 流式输出
async for chunk in client.chat_stream("讲一个故事"):
    print(chunk.text, end="")

# 切换 Agent
await client.switch_agent("coder")

# 执行命令
result = await client.execute_command("/reset")
```

**完整实现**:

```python
@dataclass
class ChatResponse:
    """聊天响应"""
    text: str
    session_id: str
    agent_id: str
    usage: Optional[Dict[str, int]] = None  # token 使用情况
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ChatChunk:
    """流式响应块"""
    text: str
    is_tool_call: bool = False
    tool_name: Optional[str] = None
    is_complete: bool = False

class GatewayClient:
    """
    高级 SDK 客户端 - 简化版 API
    
    封装了所有底层复杂性，提供直观的对话接口。
    自动处理: 会话管理、Agent 创建、队列系统、事件流
    """
    
    def __init__(
        self,
        config: Optional[GatewayConfig] = None,
        agent_id: str = "default",
        session_key: Optional[str] = None,
        tenant_id: str = "default"
    ):
        """
        初始化 Gateway 客户端
        
        Args:
            config: 网关配置，默认使用 ~/.openclaw/config.yaml
            agent_id: 默认 Agent ID
            session_key: 会话键，默认自动创建
            tenant_id: 租户 ID，多租户场景使用
        """
        self.config = config or GatewayConfig.load_default()
        self.tenant_context = TenantContext(
            tenant_id=tenant_id,
            tenant_type="user_private"
        )
        
        # 初始化核心组件
        self.session_manager = SessionManager(self.config.session_store_path)
        self.agent_registry = AgentRegistry(self.config.agents_config_path)
        self.command_router = CommandRouter()
        self.agent_runner = AgentRunner(
            registry=self.agent_registry,
            session_manager=self.session_manager,
            config=self.config
        )
        
        # 当前会话状态
        self._current_agent_id = agent_id
        self._session_key = session_key
        self._session: Optional[SessionEntry] = None
        
    async def _get_or_create_session(self) -> SessionEntry:
        """获取或创建会话"""
        if self._session is None:
            self._session = await self.session_manager.get_or_create_session(
                tenant_context=self.tenant_context,
                session_key=self._session_key,
                agent_id=self._current_agent_id
            )
            self._session_key = self._session.session_key
        return self._session
    
    async def chat(
        self,
        message: str,
        agent_id: Optional[str] = None,
        queue_mode: QueueMode = QueueMode.COLLECT
    ) -> ChatResponse:
        """
        发送消息并获取完整响应
        
        Args:
            message: 用户消息
            agent_id: 可选的 Agent ID 覆盖
            queue_mode: 队列模式
            
        Returns:
            ChatResponse: 包含完整响应文本和元数据
        """
        session = await self._get_or_create_session()
        
        # 检查是否是命令
        command = self.command_router.parse_command(message)
        if command:
            result = self.command_router.execute_command(
                command, session, self.tenant_context,
                AgentContext(registry=self.agent_registry)
            )
            
            # 处理命令结果
            if result.action == "switch_agent" and result.new_agent_id:
                self._current_agent_id = result.new_agent_id
                await self._switch_session_agent(result.new_agent_id)
            elif result.action == "reset_session":
                await self.reset_session()
            elif result.action == "update_metadata":
                for key, value in (result.metadata_updates or {}).items():
                    setattr(session, key, value)
                await self.session_manager.save(session)
            
            return ChatResponse(
                text=result.message or "",
                session_id=session.session_id,
                agent_id=self._current_agent_id,
                metadata={"command_result": result.action}
            )
        
        # 使用指定 Agent 或当前 Agent
        target_agent = agent_id or self._current_agent_id
        if agent_id and agent_id != self._current_agent_id:
            await self._switch_session_agent(agent_id)
            session = await self._get_or_create_session()
        
        # 运行 Agent
        result = await self.agent_runner.handle_message(
            session_key=session.session_key,
            prompt=message,
            tenant_context=self.tenant_context,
            queue_mode=queue_mode
        )
        
        # 构建响应
        text_content = self._extract_text_from_result(result)
        
        return ChatResponse(
            text=text_content,
            session_id=session.session_id,
            agent_id=target_agent,
            usage=result.get("meta", {}).get("usage") if isinstance(result, dict) else None
        )
    
    async def chat_stream(
        self,
        message: str,
        agent_id: Optional[str] = None,
        queue_mode: QueueMode = QueueMode.COLLECT
    ) -> AsyncIterator[ChatChunk]:
        """
        发送消息并获取流式响应
        
        Args:
            message: 用户消息
            agent_id: 可选的 Agent ID 覆盖
            queue_mode: 队列模式
            
        Yields:
            ChatChunk: 响应块，可迭代获取
        """
        session = await self._get_or_create_session()
        
        # 检查是否是命令
        command = self.command_router.parse_command(message)
        if command:
            result = self.command_router.execute_command(
                command, session, self.tenant_context,
                AgentContext(registry=self.agent_registry)
            )
            
            # 处理命令结果
            if result.action == "switch_agent" and result.new_agent_id:
                self._current_agent_id = result.new_agent_id
                await self._switch_session_agent(result.new_agent_id)
            elif result.action == "reset_session":
                await self.reset_session()
            elif result.action == "update_metadata":
                for key, value in (result.metadata_updates or {}).items():
                    setattr(session, key, value)
                await self.session_manager.save(session)
            
            yield ChatChunk(
                text=result.message or "",
                is_complete=True
            )
            return
        
        # 使用指定 Agent 或当前 Agent
        target_agent = agent_id or self._current_agent_id
        if agent_id and agent_id != self._current_agent_id:
            await self._switch_session_agent(agent_id)
            session = await self._get_or_create_session()
        
        # 运行 Agent 并流式输出
        async for event in self.agent_runner.run_stream(
            session_key=session.session_key,
            prompt=message,
            tenant_context=self.tenant_context,
            queue_mode=queue_mode
        ):
            # 转换事件为 ChatChunk
            chunk = self._convert_event_to_chunk(event)
            yield chunk
    
    async def switch_agent(self, agent_id: str) -> None:
        """切换到指定 Agent"""
        await self._switch_session_agent(agent_id)
        self._current_agent_id = agent_id
    
    async def reset_session(self) -> None:
        """重置当前会话"""
        if self._session:
            await self.session_manager.reset_session(self._session.session_key)
            self._session = None
    
    async def list_agents(self) -> List[AgentInfo]:
        """列出所有可用 Agent"""
        return self.agent_registry.list_agents()
    
    def _extract_text_from_result(self, result: dict) -> str:
        """从结果中提取文本内容"""
        if isinstance(result, dict) and "result" in result:
            payloads = result["result"].get("payloads", [])
            return "".join(p.get("text", "") for p in payloads)
        return str(result)
    
    def _convert_event_to_chunk(self, event: dict) -> ChatChunk:
        """将事件转换为 ChatChunk"""
        # 根据事件类型转换
        event_type = event.get("type", "")
        
        if event_type == "text":
            return ChatChunk(text=event.get("content", ""))
        elif event_type == "tool_start":
            return ChatChunk(
                text=f"",
                is_tool_call=True,
                tool_name=event.get("tool_name")
            )
        elif event_type == "done":
            return ChatChunk(text="", is_complete=True)
        else:
            return ChatChunk(text=str(event))
    
    async def _switch_session_agent(self, agent_id: str) -> None:
        """内部方法：切换会话的 Agent"""
        if self._session:
            # 保存当前会话
            await self.session_manager.save(self._session)
            
            # 创建或加载新 Agent 的会话
            self._session = await self.session_manager.get_or_create_session(
                tenant_context=self.tenant_context,
                session_key=None,  # 生成新的 session_key
                agent_id=agent_id
            )
            self._session_key = self._session.session_key
```

### 3.1.2 底层 API - 核心组件直接访问

对于需要更精细控制的场景，可以直接使用底层组件：

```python
from openclaw_gateway import SessionManager, AgentRegistry, AgentRunner

# 直接使用 SessionManager
session_manager = SessionManager(store_path)
session = await session_manager.get_or_create_session(
    tenant_context=tenant_context,
    agent_id="my_agent"
)

# 直接使用 AgentRegistry
registry = AgentRegistry(config_path)
agent = registry.create_deep_agent(
    agent_id="coder",
    tenant_context=tenant_context
)

# 直接使用 AgentRunner
runner = AgentRunner(registry, session_manager, config)
result = await runner.run(
    params=RunParams(...),
    tenant_context=tenant_context
)
```

### 3.1.3 事件系统与回调机制

替代 WebSocket 的事件流，使用 Python 的异步回调和迭代器：

```python
from typing import Callable, Awaitable

EventCallback = Callable[[dict], Awaitable[None]]

class EventEmitter:
    """
    事件发射器 - 替代 WebSocket 的事件流机制
    
    支持:
    - 回调函数注册
    - 异步事件分发
    - 事件过滤和转换
    """
    
    def __init__(self):
        self._callbacks: List[EventCallback] = []
        self._event_history: List[dict] = []
        self._max_history = 1000
    
    def on_event(self, callback: EventCallback) -> None:
        """注册事件回调"""
        self._callbacks.append(callback)
    
    def off_event(self, callback: EventCallback) -> None:
        """移除事件回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    async def emit(self, event: dict) -> None:
        """发射事件到所有回调"""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
        
        # 并行调用所有回调
        await asyncio.gather(
            *[cb(event) for cb in self._callbacks],
            return_exceptions=True
        )
    
    def get_history(self) -> List[dict]:
        """获取事件历史"""
        return self._event_history.copy()
```

## 3.2 会话管理 (Session Manager)

**与原设计保持一致**，详见原 3.1 节。主要变更：
- 移除与 WebSocket 相关的会话跟踪
- 保留租户感知设计
- 保留 JSONL 持久化格式

## 3.3 Agent 管理 (Agent Registry)

**与原设计保持一致**，详见原 3.2 节。

## 3.4 命令路由 (Command Router)

**与原设计保持一致**，详见原 3.3 节。

## 3.5 Agent 运行器 (Agent Runner)

**与原设计保持一致**，详见原 3.4 节。主要变更：
- 移除 WebSocket 事件发送相关代码
- 使用 EventEmitter 替代直接 WebSocket 发送
- 保留队列系统完整功能

## 3.6 系统提示词构建 (System Prompt Builder)

**与原设计保持一致**，详见原 3.6 节。

---

## 已移除的组件

以下组件在 SDK 版本中已移除：

### 原 3.5 Gateway 服务器 (Gateway Server)

**移除原因**: SDK 版本不需要 WebSocket/HTTP 服务器层

**移除内容**:
- `GatewayServer` 类
- WebSocket 端点 (`/ws`)
- HTTP API 端点 (`/v1/chat/completions`)
- 握手协议处理 (`connect` 帧)
- WebSocket 消息循环

**替代方案**: 
- 使用 `GatewayClient` 提供高级 API
- 使用 `EventEmitter` 替代 WebSocket 事件流
- 使用 Python 异步迭代器替代流式响应

### 认证机制变更

**原设计**: Token/Password/Tailscale 认证（WebSocket 握手时）

**新设计**: SDK 级认证
- 配置级认证（API keys 在配置文件中）
- 应用层负责用户认证
- SDK 本身不处理传输层认证

---

## SDK 使用示例

### 基础用法

```python
import asyncio
from openclaw_gateway import GatewayClient

async def main():
    # 创建客户端
    client = GatewayClient()
    
    # 简单对话
    response = await client.chat("你好，请介绍自己")
    print(response.text)
    
    # 流式输出
    async for chunk in client.chat_stream("写一首短诗"):
        print(chunk.text, end="")

asyncio.run(main())
```

### 多 Agent 切换

```python
async def multi_agent_example():
    client = GatewayClient()
    
    # 使用默认 Agent
    response = await client.chat("你好")
    
    # 切换到 coder Agent
    await client.switch_agent("coder")
    response = await client.chat("写一个快速排序")
    
    # 使用命令切换
    response = await client.chat("/model researcher")
    response = await client.chat("研究一下 Python 的 GIL")
```

### 多租户场景

```python
async def multi_tenant_example():
    # 租户 A
    client_a = GatewayClient(tenant_id="tenant_a")
    response_a = await client_a.chat("你好")
    
    # 租户 B - 完全隔离
    client_b = GatewayClient(tenant_id="tenant_b")
    response_b = await client_b.chat("你好")
```

### 底层 API 使用

```python
from openclaw_gateway import SessionManager, AgentRegistry, AgentRunner

async def low_level_example():
    # 直接操作核心组件
    session_manager = SessionManager("./sessions")
    registry = AgentRegistry("./config/agents.yaml")
    
    # 创建自定义工作流
    session = await session_manager.create_session(
        tenant_context=TenantContext(tenant_id="user_123"),
        agent_id="custom_agent"
    )
    
    # 手动运行 Agent
    runner = AgentRunner(registry, session_manager, config)
    result = await runner.run(
        params=RunParams(
            session_id=session.session_id,
            prompt="自定义消息",
            provider="anthropic",
            model="claude-sonnet-4-6"
        ),
        tenant_context=TenantContext(tenant_id="user_123")
    )
```
