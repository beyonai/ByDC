# DeepAgents Integration Architecture

## Overview

The OpenClaw Gateway integrates with deepagents to provide a production-ready Agent execution engine. This integration is built on 7 POC (Proof of Concept) validations that confirmed key capabilities including tool calling, token counting, STEER mode, subAgent orchestration, and streaming support.

The architecture follows a multi-tenant design with strict resource isolation, supporting both public and private workspaces. The system is built on LangGraph for state management and deepagents for Agent orchestration.

## POC Validation Results

All 7 POCs have been validated and inform the current architecture:

| POC | Function | Status | Key Finding |
|-----|----------|--------|-------------|
| 1 | Basic Integration | ✅ | `create_deep_agent()` works correctly with LangChain models |
| 2 | Token Counting | ✅ | Extract from `AIMessage.usage_metadata`, no tiktoken needed |
| 3 | STEER Mode | ✅ | Use `Command(resume=...)` with checkpointer for state injection |
| 4 | Tool System | ✅ | Alibaba Cloud Bailian Qwen supports tool calling with detailed descriptions |
| 5 | SubAgent | ✅ | SubAgents called via `task` tool, can have their own tools |
| 6 | Streaming | ✅ | `astream()` returns async iterator for real-time output |
| 7 | Multi-turn | ✅ | Checkpointer maintains conversation state across turns |

### POC 1: Basic Integration
Confirmed that `create_deep_agent()` correctly initializes Agents with:
- Model configuration via `init_chat_model()`
- System prompts for behavior control
- Tool integration for capability extension

### POC 2: Token Counting
Token usage is extracted directly from `AIMessage.usage_metadata`:

```python
for msg in reversed(result.get("messages", [])):
    if isinstance(msg, AIMessage) and msg.usage_metadata:
        usage = {
            "input_tokens": msg.usage_metadata.get("input_tokens", 0),
            "output_tokens": msg.usage_metadata.get("output_tokens", 0),
            "total_tokens": msg.usage_metadata.get("total_tokens", 0),
        }
        break
```

### POC 3: STEER Mode
STEER mode allows interrupting an active Agent run and injecting new input:

```python
from langgraph.types import Command

result = await agent.ainvoke(
    Command(resume=prompt),
    config={"configurable": {"thread_id": session_key}},
)
```

### POC 4: Tool System
Tools must have detailed descriptions with Args and Returns sections:

```python
@tool
def know(query: str) -> str:
    """
    Knowledge retrieval tool for querying business knowledge.
    
    Args:
        query: Topic or keyword to query
        
    Returns:
        Knowledge information about the topic
    """
    return f"[Knowledge] Information about: {query}"
```

### POC 5: SubAgent
SubAgents are configured and called via the `task` tool:

```python
subagent_config = {
    "name": "researcher",
    "description": "Research expert for knowledge queries",
    "system_prompt": "You are a research expert. Use the know tool.",
    "tools": [know],
}
```

### POC 6: Streaming
Streaming provides real-time output via async iteration:

```python
async for chunk in agent.astream(
    {"messages": messages},
    config={"configurable": {"thread_id": session_key}},
):
    # Process each chunk in real-time
    yield chunk
```

### POC 7: Multi-turn
Checkpointer enables conversation state persistence:

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
agent = create_deep_agent(
    model=model,
    tools=tools,
    checkpointer=checkpointer,
)
```

## Key Configuration Specifications

### Tool Definition

Tools follow the LangChain `@tool` decorator pattern with detailed docstrings:

```python
from langchain_core.tools import tool

@tool
def know(query: str) -> str:
    """
    Knowledge retrieval tool. Queries business knowledge and ontologies.
    
    Use this when users ask about business concepts, term definitions,
    or data model explanations.
    
    Args:
        query: Topic or keyword to query, e.g., "user", "order model"
        
    Returns:
        Knowledge information including concept definitions and business rules
    """
    return f"[Knowledge] About '{query}'"

@tool
def query(data: str) -> str:
    """
    Data query tool. Executes NL2Data queries.
    
    Use this when users need data from the warehouse, SQL execution,
    or business statistics.
    
    Args:
        data: Query request describing needed data and conditions
        
    Returns:
        Query results in table, statistics, or other formats
    """
    return f"[Query] Result for: '{data}'"

@tool
def compute(expression: str) -> str:
    """
    Computation tool. Executes math and data analysis.
    
    Use this for numerical calculations, statistical analysis,
    data aggregation, or formula evaluation.
    
    Args:
        expression: Calculation expression or analysis request
        
    Returns:
        Calculation results including values and analysis reports
    """
    return f"[Compute] Result: '{expression}'"

@tool
def render(format_type: str, content: str) -> str:
    """
    Rendering tool. Generates visualizations and reports.
    
    Use this for charts, tables, reports, or other visual presentations.
    
    Args:
        format_type: Format type: "chart", "table", "markdown", "html"
        content: Content data to render
        
    Returns:
        Rendered output: chart URL, HTML code, Markdown table, etc.
    """
    return f"[Render] Format: {format_type}, Content: '{content}'"

@tool
def store(key: str, value: str) -> str:
    """
    Storage tool. Saves data to memory service.
    
    Use this to persist query results, calculation data, or
    information needed across sessions.
    
    Args:
        key: Storage key for identifying the data
        value: Value to store as string
        
    Returns:
        Storage confirmation with key and status
    """
    return f"[Store] Saved key='{key}', value='{value}'"
```

**Critical Requirements:**
- Must include `Args` and `Returns` sections
- Descriptions must be clear and specific
- Use Chinese descriptions for Chinese models (Alibaba Cloud Bailian Qwen)
- Tool names should be concise and descriptive

### System Prompt Template

The system prompt enforces tool usage and provides context:

```python
def get_system_prompt() -> str:
    """Get system prompt enforcing tool usage."""
    return """You are an intelligent data analysis assistant.
When users ask any question, you MUST use available tools to get information.

Available tools:
- know: Retrieve business knowledge and ontologies
- query: Execute data queries (NL2Data)
- compute: Execute math and data analysis
- render: Generate visualizations and reports
- store: Save data to memory service

Important: For each user query, analyze if tools are needed.
If information retrieval or operations are required, actively call the appropriate tool.
"""
```

**Key Elements:**
- Explicitly enforce tool usage with "MUST"
- List all available tools with brief descriptions
- Provide clear guidance on when to use each tool
- Use imperative tone for instructions

## Architecture Components

### 1. ModelConfig

**File**: `datacloud-agent/src/datacloud_agent/core/model_config.py`

Responsible for model initialization and configuration:

```python
import os
from typing import Any
from langchain_openai import ChatOpenAI

def get_default_model_config() -> dict[str, Any]:
    """Get default model configuration."""
    return {
        "model": "openai:qwen3.5-plus",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL"),
    }

def create_model(config: dict[str, Any] | None = None) -> ChatOpenAI:
    """Create model instance with configuration."""
    if config is None:
        config = {}
    
    model_name = config.get("model", "openai:qwen3.5-plus")
    api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
    base_url = config.get("base_url") or os.getenv("OPENAI_BASE_URL")
    
    if not api_key:
        raise ValueError("API key required. Set OPENAI_API_KEY environment variable.")
    
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )
```

**Responsibilities:**
- Environment variable management for API keys
- Model provider abstraction (supports Alibaba Cloud Bailian Qwen)
- Temperature and parameter configuration
- Error handling for missing credentials

### 2. Tools

**File**: `datacloud-agent/src/datacloud_agent/core/tools.py`

Defines the 5 atomic business tools:

```python
from langchain_core.tools import tool

@tool
def know(query: str) -> str:
    """Knowledge retrieval tool..."""
    return f"[Knowledge] About '{query}'"

@tool
def query(data: str) -> str:
    """Data query tool..."""
    return f"[Query] Result: '{data}'"

@tool
def compute(expression: str) -> str:
    """Computation tool..."""
    return f"[Compute] Result: '{expression}'"

@tool
def render(format_type: str, content: str) -> str:
    """Rendering tool..."""
    return f"[Render] Format: {format_type}, Content: '{content}'"

@tool
def store(key: str, value: str) -> str:
    """Storage tool..."""
    return f"[Store] Saved key='{key}', value='{value}'"

def get_business_tools():
    """Get all 5 business tools."""
    return [know, query, compute, render, store]
```

**Design Principles:**
- Atomic operations: each tool does one thing well
- Composable: tools can be combined for complex workflows
- Self-documenting: detailed docstrings for LLM understanding

### 3. SubAgents

**File**: `datacloud-agent/src/datacloud_agent/core/subagents.py`

Configures specialized subAgents called via the `task` tool:

```python
from typing import Any
from dataclasses import dataclass

@dataclass
class SubAgentConfig:
    """SubAgent configuration."""
    name: str
    description: str
    system_prompt: str
    tools: list[Any] | None = None
    model: Any | None = None

def get_default_subagents() -> list[dict[str, Any]]:
    """Get default subAgent configurations."""
    return [
        {
            "name": "researcher",
            "description": "Research expert for knowledge queries",
            "system_prompt": """You are a research expert.
Available tools:
- know: Retrieve business knowledge and ontologies

Important: For each research request, actively call the know tool.
""",
        },
        {
            "name": "data_analyst",
            "description": "Data analyst for data queries and analysis",
            "system_prompt": """You are a data analyst.
Available tools:
- query: Execute data queries (NL2Data)
- compute: Execute math calculations

Important: For each analysis request, actively call appropriate tools.
""",
        },
        {
            "name": "visualizer",
            "description": "Visualization expert for charts and reports",
            "system_prompt": """You are a visualization expert.
Available tools:
- render: Generate visualizations and reports

Important: For each visualization request, actively call the render tool.
""",
        },
    ]
```

**Architecture Pattern:**
```
Parent Agent → task tool → SubAgent → SubAgent tools
```

### 4. AgentRunner

**File**: `datacloud-agent/src/datacloud_agent/core/runner.py`

Core execution engine integrating deepagents:

```python
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

class AgentRunner:
    """Runner for Agent execution with deduplication, debouncing, and queuing."""
    
    def __init__(
        self,
        session_manager: SessionManager,
        agent_registry: AgentRegistry,
        queue_manager: QueueManager,
        event_emitter: EventEmitter,
        config: GatewayConfig,
    ):
        self.session_manager = session_manager
        self.agent_registry = agent_registry
        self.queue_manager = queue_manager
        self.event_emitter = event_emitter
        self.config = config
        
        # Deduplication and debouncing
        self.dedupe_cache = DedupeCache(window_ms=config.inbound.dedupe_window_ms)
        self.debouncer = InboundDebouncer(debounce_ms=config.inbound.debounce_ms)
        
        # Active session tracking
        self._active_sessions: set[str] = set()
        self._active_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._running_tasks: dict[str, asyncio.Task[Any]] = {}
        
        # Checkpointers for session persistence
        self._checkpointers: dict[str, InMemorySaver] = {}
    
    async def handle_message(
        self, session_key: str, prompt: str, queue_mode: QueueMode
    ) -> dict[str, Any]:
        """Handle incoming messages with queue policy."""
        # 1. Deduplication check
        dedupe_key = f"{session_key}:{prompt}"
        if self.dedupe_cache.is_duplicate(dedupe_key):
            return {"status": "duplicate", "session_key": session_key}
        
        # 2. Debouncing check
        if not self.debouncer.should_process(session_key):
            return {"status": "debounced", "session_key": session_key}
        
        # 3. Resolve action based on queue policy
        action, was_active = await self._resolve_action(session_key, queue_mode)
        
        # 4. Execute action: EXECUTE, ENQUEUE, STEER, INTERRUPT, DROP
        ...
    
    async def _execute_agent(self, session_key: str, messages: list[str]) -> dict[str, Any]:
        """Execute Agent with deepagents integration."""
        # Extract agent_id from session_key
        parts = session_key.split(":")
        agent_id = parts[3]
        
        # Get agent config
        config = self.agent_registry.get(agent_id)
        
        # Create or get checkpointer
        if session_key not in self._checkpointers:
            self._checkpointers[session_key] = InMemorySaver()
        checkpointer = self._checkpointers[session_key]
        
        # Create model
        model = create_model({"model": config.model})
        
        # Create Agent with deepagents
        agent = create_deep_agent(
            model=model,
            system_prompt=config.system_prompt or get_system_prompt(),
            tools=get_business_tools(),
            checkpointer=checkpointer,
        )
        
        # Execute
        invoke_config = {"configurable": {"thread_id": session_key}}
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": m} for m in messages]},
            config=invoke_config,
        )
        
        # Extract token usage
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.usage_metadata:
                usage = {
                    "input_tokens": msg.usage_metadata.get("input_tokens", 0),
                    "output_tokens": msg.usage_metadata.get("output_tokens", 0),
                    "total_tokens": msg.usage_metadata.get("total_tokens", 0),
                }
                break
        
        return {
            "agent_id": agent_id,
            "messages": result.get("messages", []),
            "response": final_content,
            "usage": usage,
        }
```

**Key Features:**
- Deduplication: prevents duplicate message processing
- Debouncing: rate limits rapid successive messages
- Queue policies: COLLECT, STEER, STEER_BACKLOG, INTERRUPT, QUEUE, FOLLOWUP
- Session persistence via checkpointers
- Token usage tracking

### 5. MessageQueue

**File**: `datacloud-agent/src/datacloud_agent/queue/manager.py`

Manages message queues with multiple drop policies:

```python
from datacloud_agent.queue.types import (
    DropPolicy,
    QueuedMessage,
    QueueSettings,
    QueueState,
)

class QueueManager:
    """Manages queues for different sessions."""
    
    def __init__(self):
        self._queues: dict[str, QueueState] = {}
        self._locks: dict[str, asyncio.Lock] = {}
    
    async def enqueue(self, session_key: str, message: QueuedMessage) -> bool:
        """Add message to queue with drop policy handling."""
        lock = self._get_lock(session_key)
        async with lock:
            if session_key not in self._queues:
                return False
            
            queue = self._queues[session_key]
            
            # Handle queue full with drop policy
            if len(queue.messages) >= queue.max_size:
                if queue.drop_policy == DropPolicy.NEW:
                    return False  # Reject new messages
                elif queue.drop_policy == DropPolicy.OLD:
                    queue.messages.pop(0)  # Drop oldest
                elif queue.drop_policy == DropPolicy.SUMMARIZE:
                    await self._summarize_old_messages(session_key, queue)
            
            queue.messages.append(message)
            queue.last_activity = datetime.now()
            return True
    
    async def _summarize_old_messages(self, session_key: str, queue: QueueState) -> None:
        """Summarize old messages when queue is full."""
        if len(queue.messages) <= 10:
            queue.messages.pop(0)
            return
        
        # Keep most recent 10, summarize the rest
        messages_to_summarize = queue.messages[:-10]
        queue.messages = queue.messages[-10:]
        
        # Async summarization
        asyncio.create_task(self._async_summarize(session_key, messages_to_summarize))
```

**Drop Policies:**
- `NEW`: Reject new messages when queue is full
- `OLD`: Drop oldest messages to make room
- `SUMMARIZE`: Summarize old messages using lightweight LLM

### 6. AgentRegistry

**File**: `datacloud-agent/src/datacloud_agent/core/registry.py`

Manages Agent configurations with tenant isolation:

```python
from dataclasses import dataclass, field

@dataclass
class AgentConfig:
    """Configuration for an Agent."""
    agent_id: str
    provider: str
    model: str
    system_prompt: str | None = None
    tools: list[str] = field(default_factory=list)
    subagents: list[dict[str, Any]] = field(default_factory=list)

class AgentRegistry:
    """Registry for Agent configurations with tenant support."""
    
    def __init__(
        self,
        config_path: Path | None = None,
        allowed_tenants: list[str] | None = None,
    ):
        self._agents: dict[str, AgentConfig] = {}
        self._allowed_tenants: list[str] = allowed_tenants or []
        if config_path:
            self.load_from_yaml(config_path)
    
    def register(
        self,
        agent_id: str,
        config: AgentConfig,
        tenant_id: str | None = None,
    ) -> None:
        """Register an Agent configuration."""
        if tenant_id:
            self._check_tenant_access(tenant_id)
        if agent_id in self._agents:
            raise ValueError(f"Agent '{agent_id}' already registered")
        self._agents[agent_id] = config
    
    def get(self, agent_id: str, tenant_id: str | None = None) -> AgentConfig | None:
        """Get Agent configuration."""
        if tenant_id:
            self._check_tenant_access(tenant_id)
        return self._agents.get(agent_id)
    
    def create_default_agent(
        self,
        agent_id: str,
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-20250514",
        tenant_id: str | None = None,
    ) -> AgentConfig:
        """Create Agent with default tools and subAgents."""
        business_tools = get_business_tools()
        tool_names = [tool.name for tool in business_tools]
        default_subagents = get_default_subagents()
        default_system_prompt = get_system_prompt()
        
        config = AgentConfig(
            agent_id=agent_id,
            provider=provider,
            model=model,
            system_prompt=default_system_prompt,
            tools=tool_names,
            subagents=default_subagents,
        )
        self.register(agent_id, config, tenant_id=tenant_id)
        return config
```

**Tenant Validation:**
```python
# Tenant ID format: 3-64 chars, lowercase letters, numbers, underscores, hyphens
TENANT_ID_PATTERN = re.compile(r"^[a-z0-9_-]{3,64}$")
```

## Multi-tenant Architecture Components

### 1. TenantContext

**File**: `datacloud-agent/src/datacloud_agent/tenant/context.py`

Provides request-level tenant isolation using contextvars:

```python
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class TenantType(Enum):
    PUBLIC = "public"
    USER_PUBLIC = "user_public"
    USER_PRIVATE = "user_private"

@dataclass
class TenantContext:
    """Tenant context for request-level isolation."""
    tenant_id: str
    tenant_type: TenantType
    session_id: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def get_path_prefix(self) -> str:
        """Get path prefix: {tenant_type}/{tenant_id}"""
        return f"{self.tenant_type.value}/{self.tenant_id}"

# Context variable for tenant context
tenant_context_var: ContextVar[TenantContext | None] = ContextVar(
    "tenant_context", default=None
)

@contextmanager
def tenant_scope(context: TenantContext):
    """Context manager for tenant scope."""
    token = tenant_context_var.set(context)
    try:
        yield context
    finally:
        tenant_context_var.reset(token)
```

**Usage:**
```python
from datacloud_agent.tenant.context import TenantContext, tenant_scope

ctx = TenantContext(
    tenant_id="user_001",
    tenant_type=TenantType.USER_PRIVATE
)

with tenant_scope(ctx):
    # All operations are isolated to this tenant
    result = await agent_runner.execute(...)
```

### 2. TenantAwareFileBackend

**File**: `datacloud-agent/src/datacloud_agent/backend/composite.py`

Routes file operations to tenant-specific paths:

```python
from pathlib import Path

class TenantAwareFileBackend:
    """Tenant-aware file backend with automatic path routing."""
    
    def __init__(self, base_dir: Path, tenant_context_getter=None):
        self.base_dir = Path(base_dir).resolve()
        self._tenant_context_getter = tenant_context_getter
    
    def get_full_path(self, path: str) -> Path:
        """
        Convert logical path to absolute path.
        
        Supported prefixes:
        - public/test.txt → base_dir/public/test.txt
        - user_public/doc.txt → base_dir/user_public/{tenant_id}/doc.txt
        - user_private/data.txt → base_dir/user_private/{tenant_id}/data.txt
        """
        if path.startswith("public/"):
            return self.base_dir / path
        elif path.startswith("user_public/"):
            ctx = self._get_tenant_context()
            return self.base_dir / f"user_public/{ctx.tenant_id}/{path[12:]}"
        elif path.startswith("user_private/"):
            ctx = self._get_tenant_context()
            return self.base_dir / f"user_private/{ctx.tenant_id}/{path[13:]}"
        else:
            # Default to user_private for unqualified paths
            ctx = self._get_tenant_context()
            return self.base_dir / f"user_private/{ctx.tenant_id}/{path}"
    
    async def read(self, path: str) -> bytes:
        full_path = self.get_full_path(path)
        return await asyncio.to_thread(full_path.read_bytes)
    
    async def write(self, path: str, content: bytes) -> None:
        full_path = self.get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(full_path.write_bytes, content)
```

**Integration with deepagents:**
```python
from deepagents import create_deep_agent
from datacloud_agent.backend.composite import TenantAwareFileBackend

file_backend = TenantAwareFileBackend(
    base_dir="./workspaces",
    tenant_context_getter=TenantContext.get_current
)

agent = create_deep_agent(
    model=model,
    tools=tools,
    backend=file_backend  # Inject tenant-aware backend
)
```

### 3. TenantResolver

**File**: `datacloud-agent/src/datacloud_agent/tenant/resolver.py`

Extracts tenant information from requests:

```python
from fastapi import Request

class TenantResolver:
    """Resolves tenant information from requests."""
    
    @staticmethod
    def from_headers(request: Request) -> TenantContext:
        """Parse tenant from HTTP headers."""
        tenant_id = request.headers.get("X-Tenant-ID", "default")
        return TenantContext(
            tenant_id=tenant_id,
            tenant_type=TenantType.USER_PRIVATE
        )
    
    @staticmethod
    def from_session_key(session_key: str) -> TenantContext:
        """Parse tenant from session key.
        Format: tenant:{tenantId}:agent:{agentId}:{mainKey}
        """
        parts = session_key.split(":")
        if len(parts) >= 2 and parts[0] == "tenant":
            return TenantContext(
                tenant_id=parts[1],
                tenant_type=TenantType.USER_PRIVATE
            )
        return TenantContext(
            tenant_id="default",
            tenant_type=TenantType.USER_PRIVATE
        )
```

## Message Flow Diagrams

### Basic Flow

```
┌─────────────┐
│ User Request │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  AgentRunner    │
│  handle_message │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│   QueuePolicy       │
│   resolve(action)   │
└────────┬────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐  ┌────────┐
│EXECUTE│  │ ENQUEUE│
└───┬───┘  └───┬────┘
    │          │
    ▼          ▼
┌─────────────────────┐
│  create_deep_agent  │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│        LLM          │
└────────┬────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐  ┌──────────┐
│ Tool  │  │ SubAgent │
│ Call  │  │ (task)   │
└───┬───┘  └────┬─────┘
    │           │
    ▼           ▼
┌─────────────────────┐
│   Business Services │
└─────────────────────┘
```

### Multi-tenant Flow (with File Isolation)

```
HTTP Request
    │
    ▼
┌─────────────────┐
│ X-Tenant-ID     │
│ Header Parse    │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ TenantContext       │  ← contextvars isolation
│ (tenant_id, type)   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ TenantAwareFileBackend
│                     │
│ Path Routing:       │
│ public/ → shared    │
│ user_public/ → tenant public
│ user_private/ → tenant private
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ create_deep_agent   │
│ backend=file_backend│
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ Tool Execution      │
│ - read_file         │
│ - write_file        │
│ - execute           │
│ (auto-routed paths) │
└─────────────────────┘
```

### Queue Mode Flow

```
┌─────────────────────────────────────────────────────┐
│                    Queue Modes                       │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐         │
│  │ COLLECT │    │  STEER  │    │INTERRUPT│         │
│  └────┬────┘    └────┬────┘    └────┬────┘         │
│       │              │              │               │
│       ▼              ▼              ▼               │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐         │
│  │ Enqueue │    │ Command │    │ Cancel  │         │
│  │ (merge) │    │(resume) │    │  Task   │         │
│  └────┬────┘    └────┬────┘    └────┬────┘         │
│       │              │              │               │
│       ▼              ▼              ▼               │
│  ┌─────────────────────────────────────────┐       │
│  │         MessageQueue Manager            │       │
│  │  - Priority sorting                    │       │
│  │  - Drop policies (NEW/OLD/SUMMARIZE)   │       │
│  └─────────────────────────────────────────┘       │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### STEER Mode Flow

```
┌────────────────────────────────────────────────────┐
│ Active Session with STEER                          │
├────────────────────────────────────────────────────┤
│                                                     │
│  User Input 1                                       │
│       │                                             │
│       ▼                                             │
│  ┌─────────────┐     ┌─────────────┐               │
│  │   Agent     │────▶│ Checkpointer│               │
│  │  Running    │     │ (state)     │               │
│  └─────────────┘     └─────────────┘               │
│       │                                             │
│       │  User Input 2 (STEER)                       │
│       ▼                                             │
│  ┌─────────────┐                                    │
│  │   Cancel    │                                    │
│  │ Current Run │                                    │
│  └──────┬──────┘                                    │
│         │                                           │
│         ▼                                           │
│  ┌─────────────────┐                                │
│  │ Command(resume) │                                │
│  │ Inject new msg  │                                │
│  └────────┬────────┘                                │
│           │                                         │
│           ▼                                         │
│  ┌─────────────────┐                                │
│  │  Continue with  │                                │
│  │  merged context │                                │
│  └─────────────────┘                                │
│                                                     │
└────────────────────────────────────────────────────┘
```

## Configuration Examples

### Basic Agent Configuration

```python
from datacloud_agent.core.registry import AgentConfig
from datacloud_agent.core.tools import get_system_prompt
from datacloud_agent.core.subagents import get_default_subagents

config = AgentConfig(
    agent_id="my-agent",
    provider="openai",
    model="qwen3.5-plus",
    system_prompt=get_system_prompt(),
    tools=["know", "query", "compute", "render", "store"],
    subagents=get_default_subagents(),
)
```

### Multi-tenant Agent Configuration

```python
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
from datacloud_agent.tenant.context import TenantContext, tenant_scope
from datacloud_agent.backend.composite import TenantAwareFileBackend

async def create_tenant_aware_agent(
    tenant_id: str,
    agent_config: AgentConfig
):
    """Create tenant-aware Agent."""
    
    # 1. Create tenant context
    tenant_ctx = TenantContext(
        tenant_id=tenant_id,
        tenant_type=TenantType.USER_PRIVATE
    )
    
    # 2. Create tenant-aware file backend
    file_backend = TenantAwareFileBackend(
        base_dir="./workspaces",
        tenant_context_getter=lambda: tenant_ctx
    )
    
    # 3. Create Agent in tenant scope
    with tenant_scope(tenant_ctx):
        agent = create_deep_agent(
            model=init_chat_model(agent_config.model),
            system_prompt=build_system_prompt(tenant_ctx),
            tools=agent_config.tools,
            backend=file_backend,
            subagents=agent_config.subagents
        )
    
    return agent, tenant_ctx

# Usage
async def handle_request(tenant_id: str, message: str):
    agent, ctx = await create_tenant_aware_agent(
        tenant_id=tenant_id,
        agent_config=default_config
    )
    
    with tenant_scope(ctx):
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": message}]
        })
    
    return result
```

### YAML Configuration

```yaml
# agents.yaml
agents:
  default:
    provider: "openai"
    model: "qwen3.5-plus"
    system_prompt: |
      You are an intelligent data analysis assistant.
      Use available tools to help users.
    tools:
      - know
      - query
      - compute
      - render
      - store
    subagents:
      - name: researcher
        description: Research expert
        system_prompt: "You are a research expert."
      - name: data_analyst
        description: Data analyst
        system_prompt: "You are a data analyst."
```

### HTTP API Usage

```bash
# Create session (with tenant)
curl -X POST http://localhost:18789/v1/sessions \
  -H "X-Tenant-ID: user_001" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "default"
  }'

# Send message
curl -X POST http://localhost:18789/v1/chat \
  -H "X-Tenant-ID: user_001" \
  -H "X-Session-ID: session-abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Analyze my data and generate a report"
  }'

# STEER mode (interrupt and redirect)
curl -X POST http://localhost:18789/v1/chat \
  -H "X-Tenant-ID: user_001" \
  -H "X-Session-ID: session-abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Focus on Q4 data instead",
    "mode": "steer"
  }'
```

## Security Considerations

### 1. API Key Management

```python
# Use environment variables, never hardcode
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not set")
```

### 2. Tenant Isolation

- **Path Isolation**: Files are routed based on `public/`, `user_public/`, `user_private/` prefixes
- **ContextVar Propagation**: TenantContext must be propagated through all async calls
- **Validation**: Tenant IDs validated against `^[a-z0-9_-]{3,64}$` pattern

### 3. Input Validation

```python
# Session key format validation
parts = session_key.split(":")
if len(parts) != 5 or parts[0] != "tenant" or parts[2] != "agent":
    raise ValueError(f"Invalid session key format: {session_key}")
```

### 4. Resource Limits

- **Queue Size**: Configurable max queue size per session
- **Drop Policies**: NEW, OLD, SUMMARIZE for queue overflow
- **Deduplication**: Prevents duplicate message processing within time window

### 5. Trust Boundaries

- **Tenant ID Trust**: Design assumes upstream authentication has verified tenant_id
- **Service Layer**: Must validate tenant_id legitimacy before processing
- **File Access**: No explicit permission checks, relies on path prefix isolation

## Known Limitations

### 1. Tenant Context Propagation

**Issue**: ContextVar does not automatically propagate to subprocesses.

**Workaround**: Manually pass TenantContext to subprocess workers:
```python
# Parent process
ctx = TenantContext.get_current()
result = await subprocess_worker.run(task, tenant_context=ctx)

# Child process
with tenant_scope(tenant_context):
    # Execute task
```

### 2. Concurrent File Access

**Issue**: Multiple instances writing to the same directory may conflict.

**Mitigation**: 
- Use file locks for critical operations
- Consider shared backend (S3, NFS) for multi-instance deployments
- Implement optimistic concurrency with version checks

### 3. Checkpointer Persistence

**Issue**: `InMemorySaver` loses state on service restart.

**Future Enhancement**: Implement persistent checkpointer using Redis or database:
```python
from langgraph.checkpoint.redis import RedisSaver

checkpointer = RedisSaver(redis_url="redis://localhost:6379")
```

### 4. Token Counting Accuracy

**Issue**: Token counts from `usage_metadata` may vary by model provider.

**Note**: Current implementation uses provider-reported counts. For precise billing, consider using provider-specific tokenizers.

### 5. Tool Description Length

**Issue**: Very long tool descriptions may exceed model context limits.

**Guideline**: Keep tool descriptions under 500 tokens total for all tools combined.

### 6. Streaming with STEER

**Issue**: STEER mode interrupts streaming output, which may cause incomplete responses.

**Recommendation**: Use STEER mode primarily for non-streaming scenarios or implement client-side buffering.

---

**Document Version**: 1.0  
**Last Updated**: 2026-03-10  
**Maintainer**: OpenClaw Gateway Team
