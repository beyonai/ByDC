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
    }
]
print("创建 deep agent...")
agent = create_deep_agent(model=model, subagents=subagents)
print(f"Agent 类型: {type(agent)}")

print("\n执行查询: 'Use the researcher subagent to research Python async patterns'")
try:
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Use the researcher subagent to research Python async patterns",
                }
            ]
        }
    )
    print("调用成功!")
    print(f"结果键: {list(result.keys())}")
    if "messages" in result:
        messages = result["messages"]
        print(f"消息数量: {len(messages)}")
        for i, msg in enumerate(messages[-3:]):  # 最后3条消息
            print(f"  消息 {i}: {type(msg).__name__}")
            if hasattr(msg, "content"):
                content = msg.content
                if content:
                    print(f"    内容预览: {str(content)[:200]}...")
            if hasattr(msg, "tool_calls"):
                tool_calls = msg.tool_calls
                if tool_calls:
                    print(f"    工具调用: {len(tool_calls)}")
                    for tc in tool_calls:
                        print(f"      工具名称: {tc.get('name')}")
                        if tc.get("name") == "task":
                            print("      ✓ 检测到 task 工具调用（调用子 Agent）")
                            print(f"      参数: {tc.get('args')}")
except Exception as e:
    print(f"调用失败: {e}")
    import traceback

    traceback.print_exc()

print("测试完成")
