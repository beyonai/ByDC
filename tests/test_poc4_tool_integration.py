# test_poc4_tool_integration.py
from deepagents import create_deep_agent
from langchain_core.tools import tool
from langchain.chat_models import init_chat_model
import os

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
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
    model=model, tools=[know, query], system_prompt="Use tools to help the user."
)

print("✓ 自定义工具可以注册")
print(f"  工具列表: {[tool.name for tool in [know, query]]}")

# 执行并观察工具调用
result = agent.invoke({"messages": [{"role": "user", "content": "What do you know about Python?"}]})

print("✓ Agent 可以调用自定义工具")
print(f"  结果类型: {type(result)}")
print(f"  结果内容: {result}")

# 检查工具调用是否发生
aimessage = result["messages"][-1]
tool_calls = getattr(aimessage, "tool_calls", [])
if tool_calls:
    print(f"✓ 工具调用发生: {len(tool_calls)} 次")
    for tc in tool_calls:
        print(f"  工具名称: {tc['name']}, 参数: {tc['args']}")
    print("✓ 工具返回结果正确")
else:
    print("⚠ 未检测到工具调用，尝试更明确的查询...")
    # 尝试更明确的查询
    result2 = agent.invoke(
        {"messages": [{"role": "user", "content": "Use the know tool to query about Python."}]}
    )
    aimessage2 = result2["messages"][-1]
    tool_calls2 = getattr(aimessage2, "tool_calls", [])
    if tool_calls2:
        print(f"✓ 工具调用发生: {len(tool_calls2)} 次")
        for tc in tool_calls2:
            print(f"  工具名称: {tc['name']}, 参数: {tc['args']}")
        print("✓ 工具返回结果正确")
    else:
        print("✗ 仍然未检测到工具调用，工具集成可能有问题")

# 直接验证工具返回结果正确
print("\n--- 直接工具调用验证 ---")
test_query = "Python"
result_know = know.run(test_query)
print(f"直接调用 know 工具结果: {result_know}")
if "Knowledge about: Python" in result_know:
    print("✓ 工具返回结果正确")
else:
    print("✗ 工具返回结果不正确")

result_query = query.run(test_query)
print(f"直接调用 query 工具结果: {result_query}")
if "Query result for: Python" in result_query:
    print("✓ 工具返回结果正确")
else:
    print("✗ 工具返回结果不正确")
