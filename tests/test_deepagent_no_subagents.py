import os
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model

api_key = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
base_url = "https://lab.iwhalecloud.com/gpt-proxy/v1"

print("初始化模型...")
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=api_key,
    base_url=base_url,
    use_responses_api=False,
)

print("创建不带子Agent的DeepAgent...")
agent = create_deep_agent(model=model)
print(f"Agent 类型: {type(agent)}")

print("\n执行简单查询...")
result = agent.invoke({"messages": [{"role": "user", "content": "What is 2+2?"}]})
print(f"调用完成")
print(f"结果键: {list(result.keys())}")
if "messages" in result:
    msg = result["messages"][-1]
    print(f"响应: {msg.content[:100] if msg.content else 'None'}")
