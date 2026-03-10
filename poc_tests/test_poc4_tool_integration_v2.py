# test_poc4_tool_integration_v2.py - 改进版工具调用测试
from deepagents import create_deep_agent
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from langchain.chat_models import init_chat_model
import os

# 设置环境变量
os.environ["OPENAI_API_KEY"] = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
os.environ["OPENAI_BASE_URL"] = "https://lab.iwhalecloud.com/gpt-proxy/v1"

# 使用阿里云百炼 Qwen - 尝试使用支持工具调用的模型
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)


# 定义自定义工具 - 改进工具描述，更明确
@tool
def know(query: str) -> str:
    """
    知识检索工具。用于查询特定主题的知识信息。

    Args:
        query: 要查询的主题或关键词

    Returns:
        关于该主题的知识信息
    """
    return f"Knowledge about: {query}"


@tool
def query(data: str) -> str:
    """
    数据查询工具。用于查询特定数据的详细信息。

    Args:
        data: 要查询的数据标识或关键词

    Returns:
        查询到的数据结果
    """
    return f"Query result for: {data}"


# 创建带工具的 agent - 使用更明确的系统提示
agent = create_deep_agent(
    model=model,
    tools=[know, query],
    system_prompt="""你是一个智能助手。当用户询问任何问题时，你必须使用可用的工具来获取信息。

可用的工具：
- know: 用于检索知识信息
- query: 用于查询数据

重要：对于每个用户查询，请分析是否需要使用工具。如果需要获取信息，请主动调用相应的工具。
""",
)

print("✓ 自定义工具可以注册")
print(f"  工具列表: {[tool.name for tool in [know, query]]}")

# 测试1: 直接明确的工具调用指令
print("\n=== 测试1: 直接明确的工具调用指令 ===")
result = agent.invoke(
    {"messages": [{"role": "user", "content": "我需要测试 know 工具，请调用工具，query是‘这是一个测试！’"}]}
)

aimessage = [mes for mes in result["messages"] if isinstance(mes, AIMessage)]
tool_calls = [
    getattr(mes, "tool_calls", []) for mes in aimessage]
if tool_calls:
    print(f"✓ 工具调用发生: {sum([len(parallel_tool_call) for parallel_tool_call in tool_calls])} 次")
    for parallel_tool_call in tool_calls:
        for tc in parallel_tool_call:
            print(f"  工具名称: {tc.get('name', 'unknown')}, 参数: {tc.get('args', {})}")
else:
    print("⚠ 未检测到工具调用")
    print(
        f"  AI最终响应: {aimessage[-1].content[:200]}..."
        if len(aimessage[-1].content) > 200
        else f"  AI最终响应: {aimessage[-1].content}"
    )

# 测试2: 使用更自然的查询，但系统提示明确要求使用工具
print("\n=== 测试2: 自然语言查询（系统提示要求使用工具）===")
result2 = agent.invoke({"messages": [{"role": "user", "content": "告诉我关于 Python 的知识"}]})

aimessage2 = [mes for mes in result2["messages"] if isinstance(mes, AIMessage)]
tool_calls2 = [
    getattr(mes, "tool_calls", []) for mes in aimessage2]
if tool_calls2:
    print(f"✓ 工具调用发生: {sum([len(parallel_tool_call) for parallel_tool_call in tool_calls2])} 次")
    for parallel_tool_call in tool_calls2:
        for tc in parallel_tool_call:
            print(f"  工具名称: {tc.get('name', 'unknown')}, 参数: {tc.get('args', {})}")
else:
    print("⚠ 未检测到工具调用")
    print(
        f"  AI最终响应: {aimessage2[-1].content[:200]}..."
        if len(aimessage2[-1].content) > 200
        else f"  AI最终响应: {aimessage2[-1].content}"
    )

# 测试3: 使用 query 工具
print("\n=== 测试3: 使用 query 工具 ===")
result3 = agent.invoke(
    {"messages": [{"role": "user", "content": "请使用 query 工具查询关于 async 的数据"}]}
)

aimessage3 = [mes for mes in result3["messages"] if isinstance(mes, AIMessage)]
tool_calls3 = [
    getattr(mes, "tool_calls", []) for mes in aimessage3]
if tool_calls3:
    print(f"✓ 工具调用发生: {sum([len(parallel_tool_call) for parallel_tool_call in tool_calls3])} 次")
    for parallel_tool_call in tool_calls3:
        for tc in parallel_tool_call:
            print(f"  工具名称: {tc.get('name', 'unknown')}, 参数: {tc.get('args', {})}")
else:
    print("⚠ 未检测到工具调用")
    print(
        f"  AI最终响应: {aimessage3[-1].content[:200]}..."
        if len(aimessage3[-1].content) > 200
        else f"  AI最终响应: {aimessage3[-1].content}"
    )

# 直接验证工具返回结果正确
print("\n=== 直接工具调用验证 ===")
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

print("\n=== POC 4 重验证完成 ===")
