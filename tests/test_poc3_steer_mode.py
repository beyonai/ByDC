# test_poc3_steer_mode.py
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langchain.chat_models import init_chat_model
import os

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)

# 创建带 checkpointer 的 agent
checkpointer = InMemorySaver()
agent = create_deep_agent(model=model, checkpointer=checkpointer)

# 启动对话
config = {"configurable": {"thread_id": "test-session-001"}}
result1 = agent.invoke(
    {"messages": [{"role": "user", "content": "Tell me a story"}]}, config=config
)
print(f"✓ First turn completed")

# 使用 Command(resume=...) 注入新消息
result2 = agent.invoke(Command(resume="Make it about a robot"), config=config)
print(f"✓ Steer injection completed")
