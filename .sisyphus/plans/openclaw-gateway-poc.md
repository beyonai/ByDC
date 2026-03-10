# OpenClaw Gateway 技术验证 POC 计划

## 目标
验证 deepagents 集成的关键技术点，降低实施风险。

## 验证项

### POC 1: deepagents 基础集成验证
**目标**: 验证 `create_deep_agent` 可以正常创建和运行  
**时间**: 2-3 小时

**测试代码**:
```python
# test_poc1_basic_integration.py
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain.chat_models import init_chat_model
import os

# 配置模型（选择一种）

# 方案 A: Anthropic Claude（默认）
# model = "anthropic:claude-sonnet-4-6"

# 方案 B: 阿里云百炼 Qwen（国内可用）
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

# 验证点 1: 创建 agent
agent = create_deep_agent(
    model=model,
    system_prompt="You are a helpful assistant."
)
print(f"✓ Agent created: {type(agent)}")

# 验证点 2: 执行 invoke
result = agent.invoke({
    "messages": [{"role": "user", "content": "Hello, what is 2+2?"}]
})
print(f"✓ Result: {result}")

# 验证点 3: 异步执行
import asyncio
async def test_async():
    result = await agent.ainvoke({
        "messages": [{"role": "user", "content": "Hello async!"}]
    })
    print(f"✓ Async result: {result}")

asyncio.run(test_async())
```

**成功标准**:
- [x] Agent 创建成功
- [x] 同步调用返回结果
- [x] 异步调用返回结果

---

### POC 2: 令牌计数验证
**目标**: 验证从 `AIMessage.usage_metadata` 提取 token 计数  
**时间**: 1-2 小时

**测试代码**:
```python
# test_poc2_token_counting.py
from deepagents import create_deep_agent
from langchain_core.messages import AIMessage
from langchain.chat_models import init_chat_model
import os

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

agent = create_deep_agent(model=model)

result = agent.invoke({
    "messages": [{"role": "user", "content": "Count tokens in this message."}]
})

# 验证点: 提取 usage_metadata
for msg in reversed(result.get('messages', [])):
    if isinstance(msg, AIMessage):
        print(f"✓ AIMessage found")
        print(f"  usage_metadata: {msg.usage_metadata}")
        if msg.usage_metadata:
            print(f"  input_tokens: {msg.usage_metadata.get('input_tokens')}")
            print(f"  output_tokens: {msg.usage_metadata.get('output_tokens')}")
            print(f"  total_tokens: {msg.usage_metadata.get('total_tokens')}")
```

**成功标准**:
- [x] 返回结果包含 `messages` 列表
- [x] `AIMessage` 包含 `usage_metadata`
- [x] 可以提取 `input_tokens`, `output_tokens`, `total_tokens`

---

### POC 3: STEER 模式验证（LangGraph interrupt）
**目标**: 验证使用 `Command(resume=...)` 实现消息注入  
**时间**: 3-4 小时

**测试代码**:
```python
# test_poc3_steer_mode.py
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langchain.chat_models import init_chat_model
import asyncio
import os

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

# 创建带 checkpointer 的 agent
checkpointer = InMemorySaver()
agent = create_deep_agent(
    model=model,
    checkpointer=checkpointer
)

# 启动对话
config = {"configurable": {"thread_id": "test-session-001"}}
result1 = agent.invoke(
    {"messages": [{"role": "user", "content": "Tell me a story"}]},
    config=config
)
print(f"✓ First turn completed")

# 使用 Command(resume=...) 注入新消息
result2 = agent.invoke(
    Command(resume="Make it about a robot"),
    config=config
)
print(f"✓ Steer injection completed")
```

**成功标准**:
- [x] 带 checkpointer 的 agent 创建成功
- [x] 可以启动对话
- [x] `Command(resume=...)` 成功注入消息

---

### POC 4: 工具系统集成验证
**目标**: 验证自定义工具可以注册和调用  
**时间**: 2-3 小时

**测试代码**:
```python
# test_poc4_tool_integration.py
from deepagents import create_deep_agent
from langchain_core.tools import tool
from langchain.chat_models import init_chat_model
import os

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

# 定义自定义工具
@tool
def know(query: str) -> str:
    """Knowledge retrieval tool."""
    return f"Knowledge about: {query}"

@tool
def query(data: str) -> str:
    """Data query tool."""
    return f"Query result for: {data}"

# 创建带工具的 agent
agent = create_deep_agent(
    model=model,
    tools=[know, query],
    system_prompt="Use tools to help the user."
)

# 执行并观察工具调用
result = agent.invoke({
    "messages": [{"role": "user", "content": "What do you know about Python?"}]
})
```

**成功标准**:
- [x] 自定义工具可以注册
- [x] Agent 可以调用自定义工具 (使用 test_poc4_tool_integration_v2.py 验证通过)
- [x] 工具返回结果正确

---

### POC 5: 子 Agent 验证
**目标**: 验证 subagents 配置和调用  
**时间**: 2-3 小时

**测试代码**:
```python
# test_poc5_subagent_v3.py - 完整验证子Agent工具调用
from deepagents import create_deep_agent
from langchain_core.tools import tool
from langchain.chat_models import init_chat_model
import os

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

# 定义工具
@tool
def get_user_data(query: str) -> str:
    """获取用户数据的工具"""
    return f"User data for user-123: {query}"

# 配置子 Agent（带工具）
subagents = [
    {
        "name": "data_assistant",
        "description": "数据助手",
        "system_prompt": "你是一个数据助手。必须使用 get_user_data 工具查询数据。",
        "tools": [get_user_data]
    }
]

agent = create_deep_agent(
    model=model,
    subagents=subagents
)

# 执行并观察子 Agent 调用工具
result = agent.invoke({
    "messages": [{"role": "user", "content": "请帮我查询我的用户数据"}]
})
```

**成功标准**:
- [x] 子 Agent 配置成功
- [x] 父 Agent 可以调用子 Agent
- [x] 子 Agent 可以调用其配置的工具 (v3 测试验证：调用了4次工具)
- [x] 工具返回结果正确
- [x] 完整调用链路验证成功

---

### POC 6: 流式输出验证
**目标**: 验证 `astream` 可以流式输出  
**时间**: 1-2 小时

**测试代码**:
```python
# test_poc6_streaming.py
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
import asyncio
import os

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

agent = create_deep_agent(model=model)

async def test_streaming():
    chunks = []
    async for chunk in agent.astream({
        "messages": [{"role": "user", "content": "Count from 1 to 5"}]
    }):
        chunks.append(chunk)
        print(f"Chunk: {chunk}")
    
    print(f"✓ Streaming completed with {len(chunks)} chunks")

asyncio.run(test_streaming())
```

**成功标准**:
- [x] 流式输出可以正常接收
- [x] 可以累加多个 chunks

---

## 执行计划

### 环境准备（使用 uv）
```bash
# 1. 进入 worktree
cd /home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation

# 2. 创建测试目录
mkdir -p poc_tests
cd poc_tests

# 3. 使用 uv 创建虚拟环境
uv venv
source .venv/bin/activate  # Linux/Mac
# 或: .venv\Scripts\activate  # Windows

# 4. 使用 uv 安装依赖
uv pip install deepagents langgraph langchain langchain-anthropic

# 5. 创建 pyproject.toml（可选，用于依赖管理）
cat > pyproject.toml << 'EOF'
[project]
name = "openclaw-gateway-poc"
version = "0.1.0"
description = "POC tests for OpenClaw Gateway"
requires-python = ">=3.11"
dependencies = [
    "deepagents>=0.4.0",
    "langgraph>=0.2.0",
    "langchain>=0.3.0",
    "langchain-anthropic>=0.2.0",
]
EOF

# 6. 设置 API key（选择一种）

# 方案 A: 使用 Anthropic Claude（默认）
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# 方案 B: 使用阿里云百炼 Qwen（推荐，国内可用）
export OPENAI_API_KEY="sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
export OPENAI_BASE_URL="https://lab.iwhalecloud.com/gpt-proxy/v1"

# 方案 C: 使用其他 OpenAI 兼容接口
# export OPENAI_API_KEY="your-api-key"
# export OPENAI_BASE_URL="https://your-custom-endpoint.com/v1"
```

### uv 常用命令参考
```bash
# 创建虚拟环境
uv venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
uv pip install <package>

# 从 pyproject.toml 安装
uv pip install -e .

# 运行 Python 脚本
uv run python test_poc1.py

# 同步依赖（根据 pyproject.toml）
uv pip sync

# 导出依赖
uv pip freeze > requirements.txt
```

### 执行顺序
1. POC 1: 基础集成（必须先通过）
2. POC 2: 令牌计数
3. POC 3: STEER 模式
4. POC 4: 工具集成
5. POC 5: 子 Agent
6. POC 6: 流式输出

### 验收标准
- **全部通过**: 可以立即开始实施
- **部分通过**: 针对失败项调整方案
- **主要失败**: 重新评估技术选型

---

## 输出物

每个 POC 完成后记录：
1. 测试代码
2. 执行结果
3. 遇到的问题
4. 解决方案

最终输出：《技术验证报告》

---

## 启动命令

```bash
# 启动工作会话执行 POC
/start-work openclaw-gateway-poc

# 执行将自动：
# 1. 进入 worktree: /home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation
# 2. 创建 poc_tests 目录
# 3. 使用 uv 创建虚拟环境: uv venv
# 4. 使用 uv 安装依赖: uv pip install deepagents langgraph langchain langchain-anthropic
# 5. 逐个执行 6 个 POC 测试
# 6. 生成技术验证报告
```
