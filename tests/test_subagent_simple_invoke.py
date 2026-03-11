import os, sys

sys.stdout.flush()
os.environ["OPENAI_API_KEY"] = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
os.environ["OPENAI_BASE_URL"] = "https://lab.iwhalecloud.com/gpt-proxy/v1"

from langchain.chat_models import init_chat_model
from deepagents import create_deep_agent

print("初始化模型...")
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    use_responses_api=False,
)

subagents = [
    {
        "name": "researcher",
        "description": "Research specialist",
        "system_prompt": "You are a research expert.",
        "model": model,  # 显式传递模型实例
        "tools": [],  # 空工具列表
    }
]
print("创建 deep agent...")
agent = create_deep_agent(model=model, subagents=subagents)
print(f"Agent 类型: {type(agent)}")

print("\n执行简单查询: 'Hello'")
try:
    result = agent.invoke({"messages": [{"role": "user", "content": "Hello"}]})
    print("调用成功!")
    print(f"结果键: {list(result.keys())}")
    if "messages" in result:
        msg = result["messages"][-1]
        print(f"响应: {msg.content[:100] if msg.content else 'None'}")
except Exception as e:
    print(f"调用失败: {e}")
    import traceback

    traceback.print_exc()

print("测试完成")
