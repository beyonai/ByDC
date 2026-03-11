from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain.chat_models import init_chat_model
import os

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)

# 验证点 1: 创建 agent
agent = create_deep_agent(model=model, system_prompt="You are a helpful assistant.")
print(f"✓ Agent created: {type(agent)}")

# 验证点 2: 执行 invoke
result = agent.invoke({"messages": [{"role": "user", "content": "Hello, what is 2+2?"}]})
print(f"✓ Result: {result}")

# 验证点 3: 异步执行
import asyncio


async def test_async():
    result = await agent.ainvoke({"messages": [{"role": "user", "content": "Hello async!"}]})
    print(f"✓ Async result: {result}")


asyncio.run(test_async())
