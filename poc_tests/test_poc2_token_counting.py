# test_poc2_token_counting.py
from deepagents import create_deep_agent
from langchain_core.messages import AIMessage
from langchain.chat_models import init_chat_model
import os

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)

agent = create_deep_agent(model=model)

result = agent.invoke({"messages": [{"role": "user", "content": "Count tokens in this message."}]})

# 验证点: 提取 usage_metadata
for msg in reversed(result.get("messages", [])):
    if isinstance(msg, AIMessage):
        print(f"✓ AIMessage found")
        print(f"  usage_metadata: {msg.usage_metadata}")
        if msg.usage_metadata:
            print(f"  input_tokens: {msg.usage_metadata.get('input_tokens')}")
            print(f"  output_tokens: {msg.usage_metadata.get('output_tokens')}")
            print(f"  total_tokens: {msg.usage_metadata.get('total_tokens')}")
