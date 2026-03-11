# 13. SDK API 参考

> 本文档详细描述 OpenClaw Gateway Python SDK 的公共 API

## 目录

- [GatewayClient](#gatewayclient) - 高级客户端 API
- [GatewayConfig](#gatewayconfig) - 配置管理
- [ChatResponse / ChatChunk](#chatresponse--chatchunk) - 响应类型
- [EventEmitter](#eventemitter) - 事件系统
- [底层组件](#底层组件)

---

## GatewayClient

高级客户端，封装所有底层复杂性，提供直观的对话接口。

### 初始化

```python
from openclaw_gateway import GatewayClient, GatewayConfig

# 使用默认配置
client = GatewayClient()

# 使用自定义配置
config = GatewayConfig(
    workspace_root="./my_workspace",
    session_store_path="./sessions"
)
client = GatewayClient(config=config)

# 指定默认 Agent
client = GatewayClient(agent_id="coder")

# 多租户场景
client = GatewayClient(tenant_id="user_123")
```

### chat()

发送消息并获取完整响应。

```python
async def chat(
    self,
    message: str,
    agent_id: Optional[str] = None,
    queue_mode: QueueMode = QueueMode.COLLECT
) -> ChatResponse
```

**参数**:
- `message` (str): 用户消息
- `agent_id` (Optional[str]): 可选的 Agent ID 覆盖
- `queue_mode` (QueueMode): 队列模式，默认 COLLECT

**返回**: `ChatResponse`

**示例**:
```python
response = await client.chat("你好，请介绍自己")
print(response.text)
print(f"Session: {response.session_id}")
print(f"Agent: {response.agent_id}")
```

### chat_stream()

发送消息并获取流式响应。

```python
async def chat_stream(
    self,
    message: str,
    agent_id: Optional[str] = None,
    queue_mode: QueueMode = QueueMode.COLLECT
) -> AsyncIterator[ChatChunk]
```

**参数**: 同 `chat()`

**返回**: `AsyncIterator[ChatChunk]`

**示例**:
```python
async for chunk in client.chat_stream("写一首短诗"):
    print(chunk.text, end="")
    if chunk.is_tool_call:
        print(f"[Tool: {chunk.tool_name}]")
```

### switch_agent()

切换到指定 Agent。

```python
async def switch_agent(self, agent_id: str) -> None
```

**示例**:
```python
await client.switch_agent("coder")
response = await client.chat("写一个快速排序")
```

### reset_session()

重置当前会话。

```python
async def reset_session(self) -> None
```

### list_agents()

列出所有可用 Agent。

```python
def list_agents(self) -> List[AgentInfo]
```

**示例**:
```python
agents = client.list_agents()
for agent in agents:
    print(f"{agent.id}: {agent.name}")
```

---

## GatewayConfig

配置管理类。

```python
@dataclass
class GatewayConfig:
    workspace_root: Path = Path("~/.openclaw/workspace")
    session_store_path: Path = Path("~/.openclaw/sessions")
    agents_config_path: Path = Path("~/.openclaw/agents.yaml")
    default_agent: str = "default"
    default_model: str = "anthropic/claude-sonnet-4-6"
    
    @classmethod
    def load_default(cls) -> "GatewayConfig":
        """从默认位置加载配置"""
        ...
    
    @classmethod
    def from_file(cls, path: Path) -> "GatewayConfig":
        """从文件加载配置"""
        ...
```

---

## ChatResponse / ChatChunk

响应类型定义。

```python
@dataclass
class ChatResponse:
    """完整响应"""
    text: str
    session_id: str
    agent_id: str
    usage: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ChatChunk:
    """流式响应块"""
    text: str
    is_tool_call: bool = False
    tool_name: Optional[str] = None
    is_complete: bool = False
```

---

## EventEmitter

事件系统，替代 WebSocket 的事件流。

```python
from openclaw_gateway import EventEmitter

emitter = EventEmitter()

# 注册回调
async def on_event(event: dict):
    print(f"Event: {event}")

emitter.on_event(on_event)

# 发射事件
await emitter.emit({"type": "text", "content": "Hello"})

# 获取历史
history = emitter.get_history()
```

---

## 底层组件

### SessionManager

```python
from openclaw_gateway.core import SessionManager

session_manager = SessionManager(store_path="./sessions")

# 获取或创建会话
session = await session_manager.get_or_create_session(
    tenant_context=TenantContext(tenant_id="user_123"),
    agent_id="my_agent"
)

# 保存会话
await session_manager.save(session)

# 重置会话
await session_manager.reset_session(session.session_key)
```

### AgentRegistry

```python
from openclaw_gateway.core import AgentRegistry

registry = AgentRegistry(config_path="./config/agents.yaml")

# 列出 Agent
agents = registry.list_agents()

# 创建 Agent 实例
agent = registry.create_deep_agent(
    agent_id="coder",
    tenant_context=TenantContext(tenant_id="user_123")
)
```

### AgentRunner

```python
from openclaw_gateway.core import AgentRunner, RunParams

runner = AgentRunner(registry, session_manager, config)

# 运行 Agent
result = await runner.run(
    params=RunParams(
        session_id=session.session_id,
        prompt="你好",
        provider="anthropic",
        model="claude-sonnet-4-6"
    ),
    tenant_context=TenantContext(tenant_id="user_123")
)
```

---

## 完整示例

### 基础对话

```python
import asyncio
from openclaw_gateway import GatewayClient

async def main():
    client = GatewayClient()
    
    # 简单对话
    response = await client.chat("你好")
    print(response.text)
    
    # 流式输出
    async for chunk in client.chat_stream("讲一个故事"):
        print(chunk.text, end="")

asyncio.run(main())
```

### 多 Agent 协作

```python
async def multi_agent_workflow():
    client = GatewayClient()
    
    # 研究员 Agent 收集信息
    await client.switch_agent("researcher")
    research = await client.chat("研究 Python 异步编程")
    
    # 编码 Agent 实现代码
    await client.switch_agent("coder")
    code = await client.chat(f"基于以下研究实现示例代码:\n{research.text}")
    
    print(code.text)
```

### 带事件监听

```python
async def with_events():
    client = GatewayClient()
    
    # 监听所有事件
    async def on_event(event):
        if event.get("type") == "tool_start":
            print(f"开始调用工具: {event.get('tool_name')}")
        elif event.get("type") == "tool_end":
            print(f"工具调用完成")
    
    # 通过底层 runner 访问事件
    # (GatewayClient 高级 API 会自动处理事件)
    
    response = await client.chat("使用工具查找文件")
```

---
