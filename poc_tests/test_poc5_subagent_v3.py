# test_poc5_subagent_v3.py - 验证子Agent工具调用
from deepagents import create_deep_agent
from langchain_core.tools import tool
from langchain_core.messages import AIMessage, ToolMessage
from langchain.chat_models import init_chat_model
import os

# 设置环境变量
os.environ["OPENAI_API_KEY"] = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
os.environ["OPENAI_BASE_URL"] = "https://lab.iwhalecloud.com/gpt-proxy/v1"

print("=== POC 5 v3: 子 Agent 工具调用验证 ===")

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)
print("✓ 模型初始化成功")


# 定义工具（用于验证子Agent调用）
@tool
def get_user_data(query: str) -> str:
    """
    获取用户数据的工具。用于查询当前用户的相关信息。

    Args:
        query: 要查询的数据类型或关键词

    Returns:
        用户数据查询结果
    """
    result = f"User data for user-123: {query}"
    print(f"  [工具被调用] get_user_data: {result}")
    return result


# 配置子 Agent（带工具）
subagents = [
    {
        "name": "data_assistant",
        "description": "数据助手，擅长查询用户数据",
        "system_prompt": "你是一个数据助手。当用户需要查询数据时，你必须使用 get_user_data 工具。",
        "tools": [get_user_data],
    }
]
print(f"✓ 子 Agent 配置成功")
print(f"  子Agent: data_assistant")
print(f"  工具: get_user_data")

# 创建父 Agent
agent = create_deep_agent(
    model=model,
    subagents=subagents,
    system_prompt="你有权限调用 data_assistant 子Agent来查询用户数据。",
)
print("✓ Agent 创建成功")

# 执行查询（触发子Agent调用）
print("\n--- 执行查询: 查询我的用户数据 ---")
try:
    result = agent.invoke({"messages": [{"role": "user", "content": "请帮我查询我的用户数据"}]})
    print("✓ 调用完成")

    # 分析消息链，验证子Agent调用
    messages = result.get("messages", [])
    print(f"\n  消息链分析（共 {len(messages)} 条消息）:")

    tool_call_found = False
    tool_message_found = False

    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", [])
            if tool_calls:
                tool_call_found = True
                print(f"  [{i}] {msg_type}: 包含工具调用")
                for tc in tool_calls:
                    print(f"      → 工具: {tc.get('name', 'unknown')}, 参数: {tc.get('args', {})}")
            else:
                content = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
                print(f"  [{i}] {msg_type}: {content}")
        elif isinstance(msg, ToolMessage):
            tool_message_found = True
            content = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
            print(f"  [{i}] {msg_type}: {content}")
        else:
            print(f"  [{i}] {msg_type}")

    # 验证结果
    print("\n--- 验证结果 ---")
    if tool_call_found:
        print("✓ 检测到工具调用")
    else:
        print("⚠ 未检测到工具调用")

    if tool_message_found:
        print("✓ 检测到工具返回结果")
    else:
        print("⚠ 未检测到工具返回结果")

    if tool_call_found and tool_message_found:
        print("\n✅ 子 Agent 工具调用验证成功！")
        print("   子Agent配置正确，工具调用链路完整")
    else:
        print("\n⚠️ 子 Agent 调用链路不完整")
        print("   可能原因：模型未触发子Agent调用，或查询不够明确")

except Exception as e:
    print(f"✗ 调用失败: {e}")
    import traceback

    traceback.print_exc()

print("\n=== POC 5 v3 验证完成 ===")
