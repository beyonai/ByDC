import os
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
print(f"模型类型: {type(model)}")
print(f"模型名称: {model.model_name}")

# 尝试简单的调用
from langchain_core.messages import HumanMessage

print("\n尝试简单调用...")
try:
    response = model.invoke([HumanMessage(content="Hello")])
    print(f"响应类型: {type(response)}")
    print(f"响应内容: {response.content}")
except Exception as e:
    print(f"调用失败: {e}")
    import traceback

    traceback.print_exc()
