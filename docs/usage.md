# OpenClaw Gateway Usage Guide

This guide covers how to use the OpenClaw Gateway for AI-powered data analysis and chat interactions.

---

## Table of Contents

1. [SDK Usage](#sdk-usage)
2. [Service API](#service-api)
3. [UI Configuration](#ui-configuration)
4. [E2E Verification](#e2e-verification)
5. [Troubleshooting](#troubleshooting)

---

## SDK Usage

The OpenClaw Gateway SDK provides a Python interface for interacting with the agent system.

### Installation

```bash
# Install the SDK
pip install datacloud-agent

# Or with uv
uv add datacloud-agent
```

### Basic Chat

Send a simple message and get a response:

```python
import asyncio
from datacloud_agent import GatewayClient

async def basic_chat():
    # Create a client instance
    client = GatewayClient()
    
    # Send a message
    response = await client.chat("What were our sales figures last quarter?")
    
    # Print the response
    print(response.content)
    print(f"Session ID: {response.session_id}")

# Run the example
asyncio.run(basic_chat())
```

### Streaming Responses

For real-time responses, use the streaming API:

```python
import asyncio
from datacloud_agent import GatewayClient

async def stream_chat():
    client = GatewayClient()
    
    # Stream the response
    async for chunk in client.chat_stream("Analyze our customer churn data"):
        if chunk.type == "content":
            print(chunk.content, end="", flush=True)
        elif chunk.type == "tool_call":
            print(f"\n[Using tool: {chunk.tool_name}]")
        elif chunk.type == "complete":
            print(f"\n\nSession ID: {chunk.session_id}")

asyncio.run(stream_chat())
```

### Agent Switching

Switch between different agents using slash commands:

```python
import asyncio
from datacloud_agent import GatewayClient

async def switch_agents():
    client = GatewayClient()
    
    # List available agents
    agents = await client.list_agents()
    print(f"Available agents: {[a.name for a in agents]}")
    
    # Switch to a specific agent
    await client.switch_agent("data_analyst")
    
    # Now chat with the data analyst agent
    response = await client.chat("Generate a sales report")
    print(response.content)
    
    # Switch to another agent
    await client.switch_agent("code_helper")
    response = await client.chat("Write a Python script to parse CSV files")
    print(response.content)

asyncio.run(switch_agents())
```

### Session Management

Manage conversation sessions programmatically:

```python
import asyncio
from datacloud_agent import GatewayClient

async def session_management():
    client = GatewayClient()
    
    # Create a new session
    session = await client.create_session(
        tenant_id="tenant_123",
        metadata={"project": "Q4 Analysis"}
    )
    print(f"Created session: {session.id}")
    
    # Chat within this session
    response = await client.chat(
        "Remember this: our target is $1M revenue",
        session_id=session.id
    )
    
    # Continue the conversation (context is preserved)
    response = await client.chat(
        "What's our progress toward the target?",
        session_id=session.id
    )
    
    # List all sessions for a tenant
    sessions = await client.list_sessions(tenant_id="tenant_123")
    print(f"Active sessions: {len(sessions)}")
    
    # Delete a session
    await client.delete_session(session.id)

asyncio.run(session_management())
```

### Command Execution

Execute commands directly:

```python
import asyncio
from datacloud_agent import GatewayClient

async def execute_commands():
    client = GatewayClient()
    
    # Execute a slash command
    result = await client.execute_command("/help")
    print(result.output)
    
    # Reset the conversation
    await client.execute_command("/reset")
    
    # Switch model
    await client.execute_command("/model gpt-4")
    
    # Check system status
    result = await client.execute_command("/status")
    print(result.output)

asyncio.run(execute_commands())
```

### Advanced Configuration

Configure the client with custom settings:

```python
from datacloud_agent import GatewayClient, GatewayConfig

# Create a custom configuration
config = GatewayConfig(
    base_url="http://localhost:2024",
    api_key="your-api-key",
    default_agent="gateway",
    timeout=60,
    max_retries=3
)

# Initialize client with config
client = GatewayClient(config=config)
```

### Multi-Tenant Usage

Work with tenant isolation:

```python
import asyncio
from datacloud_agent import GatewayClient, TenantContext

async def multi_tenant_example():
    # Create client with tenant context
    tenant_ctx = TenantContext(
        tenant_id="acme_corp",
        tenant_type="user_private"
    )
    
    client = GatewayClient(tenant_context=tenant_ctx)
    
    # All operations are now scoped to this tenant
    response = await client.chat("Show my private data")
    
    # Switch to public tenant
    public_ctx = TenantContext(
        tenant_id="public",
        tenant_type="public"
    )
    client.set_tenant_context(public_ctx)
    
    response = await client.chat("Show public datasets")

asyncio.run(multi_tenant_example())
```

---

## Service API

The Service layer provides HTTP and WebSocket APIs for external integration.

### HTTP API

#### Chat Completions (OpenAI Compatible)

```bash
# Basic chat request
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_123" \
  -d '{
    "model": "gateway",
    "messages": [
      {"role": "user", "content": "What is the sales trend?"}
    ],
    "stream": false
  }'
```

#### Streaming Response

```bash
# Stream the response
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_123" \
  -d '{
    "model": "gateway",
    "messages": [
      {"role": "user", "content": "Analyze the data"}
    ],
    "stream": true
  }'
```

#### Using Python (httpx)

```python
import httpx

async def http_chat():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8080/v1/chat/completions",
            headers={"X-Tenant-ID": "tenant_123"},
            json={
                "model": "gateway",
                "messages": [
                    {"role": "user", "content": "Hello!"}
                ]
            }
        )
        result = response.json()
        print(result["choices"][0]["message"]["content"])
```

### Session Management API

```bash
# Create a new session
curl -X POST http://localhost:8080/v1/sessions \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_123" \
  -d '{
    "metadata": {"project": "Analysis"}
  }'

# List sessions
curl http://localhost:8080/v1/sessions \
  -H "X-Tenant-ID: tenant_123"

# Get session details
curl http://localhost:8080/v1/sessions/{session_id} \
  -H "X-Tenant-ID: tenant_123"

# Delete a session
curl -X DELETE http://localhost:8080/v1/sessions/{session_id} \
  -H "X-Tenant-ID: tenant_123"
```

### WebSocket Connection

Connect for real-time bidirectional communication:

```python
import asyncio
import websockets
import json

async def websocket_chat():
    uri = "ws://localhost:8080/ws"
    
    async with websockets.connect(uri) as websocket:
        # Send authentication
        await websocket.send(json.dumps({
            "type": "auth",
            "tenant_id": "tenant_123"
        }))
        
        # Send a message
        await websocket.send(json.dumps({
            "type": "chat",
            "content": "Analyze Q4 data",
            "session_id": "session_abc"
        }))
        
        # Receive responses
        async for message in websocket:
            data = json.loads(message)
            
            if data["type"] == "chunk":
                print(data["content"], end="")
            elif data["type"] == "tool_call":
                print(f"\n[Tool: {data['tool_name']}]")
            elif data["type"] == "complete":
                print("\n[Complete]")
                break

asyncio.run(websocket_chat())
```

### LangGraph API Compatibility

The service provides LangGraph-compatible endpoints for UI integration:

```bash
# Health check
curl http://localhost:2024/ok

# Create a thread (session)
curl -X POST http://localhost:2024/threads \
  -H "Content-Type: application/json" \
  -d '{}'

# Create a run
curl -X POST http://localhost:2024/threads/{thread_id}/runs \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "gateway",
    "input": {
      "messages": [
        {"type": "human", "content": "Hello!"}
      ]
    }
  }'

# Get thread state
curl http://localhost:2024/threads/{thread_id}/state

# List threads
curl http://localhost:2024/threads
```

---

## UI Configuration

### Connecting deep-agents-ui

The OpenClaw Gateway works with the deep-agents-ui interface for interactive chat.

#### Prerequisites

1. Node.js 18+ and yarn installed
2. The Gateway service running

#### Setup

```bash
# Clone the UI (if not already present)
git submodule update --init --recursive

# Install UI dependencies
cd ui/deep-agents-ui
yarn install

# Build the UI
yarn build
```

#### Configuration

When you open the UI at `http://localhost:3000`, configure these settings:

| Setting | Value | Description |
|---------|-------|-------------|
| Deployment URL | `http://127.0.0.1:2024` | The Gateway service endpoint |
| Assistant ID | `gateway` | The default agent identifier |
| LangSmith API Key | (optional) | For LangSmith integration |

#### Environment Variables

You can also set configuration via environment variables:

```bash
# Create .env file in ui/deep-agents-ui/
echo 'NEXT_PUBLIC_LANGSMITH_API_KEY="lsv2_xxxx"' > .env
```

**Note:** UI settings take precedence over environment variables.

#### Starting the UI

```bash
# From the service directory
cd service/datacloud-agent-service
./scripts/start_with_ui.sh

# Or manually
cd ui/deep-agents-ui
yarn dev
```

The UI will be available at `http://localhost:3000`.

---

## E2E Verification

Follow these steps to verify the complete system is working.

### Step 1: Start the Service

```bash
# Navigate to the service directory
cd service/datacloud-agent-service

# Start the service
uv run python server.py

# Or use the startup script
./scripts/start.sh
```

Verify the service is running:

```bash
# Health check
curl http://localhost:2024/ok

# Expected response: {"status": "ok"}
```

### Step 2: Test the HTTP API

```bash
# Send a test message
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gateway",
    "messages": [
      {"role": "user", "content": "Hello, are you working?"}
    ]
  }'

# You should receive a JSON response with the assistant's reply
```

### Step 3: Connect the UI

1. Open your browser to `http://localhost:3000`
2. Click the Settings button (gear icon)
3. Enter the configuration:
   - Deployment URL: `http://127.0.0.1:2024`
   - Assistant ID: `gateway`
4. Click Save

### Step 4: Send a Test Message

1. In the chat interface, type: "Hello, can you help me analyze data?"
2. Press Enter or click Send
3. You should see:
   - A loading indicator
   - The agent's response appearing
   - Any tool calls being executed

### Step 5: Verify Session Persistence

1. Send a message: "Remember that my target is 1000 units"
2. Send a follow-up: "What was my target again?"
3. The agent should remember the context

### Step 6: Test Agent Switching

1. Type: `/help` to see available commands
2. Type: `/model` to see available models
3. The agent should respond appropriately

### Verification Checklist

- [ ] Service starts without errors
- [ ] Health check returns `{"status": "ok"}`
- [ ] HTTP API responds to chat requests
- [ ] UI loads without errors
- [ ] UI connects to service successfully
- [ ] Chat messages are sent and received
- [ ] Sessions maintain context
- [ ] Slash commands work

---

## Troubleshooting

### Common Issues

#### Service Won't Start

**Symptom:** `uv run python server.py` fails with import errors

**Solutions:**
1. Ensure you're in the correct directory: `service/datacloud-agent-service`
2. Install dependencies: `uv sync`
3. Check Python version: `python --version` (should be 3.12+)

```bash
# Reinstall dependencies
uv sync --reinstall

# Check workspace setup
cd ../..
uv sync
```

#### Port Already in Use

**Symptom:** `Address already in use` error

**Solution:**
```bash
# Find and kill the process using port 2024
lsof -ti:2024 | xargs kill -9

# Or use a different port
uv run python server.py --port 2025
```

#### UI Cannot Connect to Service

**Symptom:** "Connection failed" or timeout in UI

**Solutions:**
1. Verify the service is running: `curl http://localhost:2024/ok`
2. Check the Deployment URL in UI settings (should be `http://127.0.0.1:2024`)
3. Ensure no firewall is blocking the connection
4. Try using `localhost` instead of `127.0.0.1`

#### No Response from Agent

**Symptom:** Messages sent but no response received

**Solutions:**
1. Check service logs for errors
2. Verify API keys are configured in `.env`
3. Test with a simple message first
4. Check if the model is available

```bash
# Check service logs
uv run python server.py 2>&1 | tee service.log

# Test with curl
curl -v -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gateway", "messages": [{"role": "user", "content": "test"}]}'
```

#### Session Not Persisting

**Symptom:** Agent forgets context between messages

**Solutions:**
1. Ensure `session_id` is being passed correctly
2. Check that the session exists: `curl http://localhost:8080/v1/sessions/{session_id}`
3. Verify tenant isolation isn't causing issues

#### WebSocket Connection Drops

**Symptom:** Real-time updates stop working

**Solutions:**
1. Check network stability
2. Increase timeout settings
3. Implement reconnection logic in client

### Debug Tips

#### Enable Debug Logging

```python
# In your Python code
import logging
logging.basicConfig(level=logging.DEBUG)

# Or set environment variable
export LOG_LEVEL=DEBUG
```

#### Test Individual Components

```bash
# Test SDK directly
python -c "from datacloud_agent import GatewayClient; print('SDK OK')"

# Test HTTP endpoint
curl http://localhost:8080/health

# Test WebSocket
wscat -c ws://localhost:8080/ws
```

#### Check Configuration

```bash
# Verify environment variables
echo $DATACLOUD_API_KEY
echo $DATACLOUD_BASE_URL

# Check config files
cat service/datacloud-agent-service/config.py
cat datacloud-agent/src/datacloud_agent/config/models.py
```

#### Monitor System Resources

```bash
# Check CPU and memory
top

# Check disk space
df -h

# Check open files
lsof -p $(pgrep -f "python server.py")
```

### Getting Help

If issues persist:

1. Check the logs: `cat service/datacloud-agent-service/logs/*.log`
2. Review the architecture document: `docs/openclaw-gateway-architecture.md`
3. Run the test suite: `uv run pytest`
4. Open an issue with:
   - Error messages
   - Steps to reproduce
   - Environment details (OS, Python version, etc.)

---

## Additional Resources

- [Architecture Documentation](./openclaw-gateway-architecture.md)
- [API Reference](./api-reference.md) (if available)
- [deep-agents-ui Repository](https://github.com/langchain-ai/deep-agents-ui)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
