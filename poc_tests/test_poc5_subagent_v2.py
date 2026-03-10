# test_poc5_subagent_v2.py - 改进版子Agent测试
from deepagents import create_deep_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langchain.chat_models import init_chat_model
import os

# 设置环境变量
os.environ["OPENAI_API_KEY"] = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
os.environ["OPENAI_BASE_URL"] = "https://lab.iwhalecloud.com/gpt-proxy/v1"

print("=== POC 5: 子 Agent 验证 ===")

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)
print("✓ 模型初始化成功")


@tool
def get_user_data(query: str) -> str:
    """Mock data for the current user."""
    return f"Data for user user-123: {query}"

# 配置子 Agent
subagents = [
    {
        "name": "researcher",
        "description": "Research specialist",
        "system_prompt": "You are a research expert.",
        "tools": [get_user_data],
    }
]
print(f"✓ 子 Agent 配置: {subagents}")

agent = create_deep_agent(
    model=model, 
    subagents=subagents,
)
print("✓ Agent 创建成功")
print(f"  Agent 类型: {type(agent)}")

# 执行并观察子 Agent 调用
print("\n--- 执行查询: Research Python async patterns ---")
try:
    result = agent.invoke({"messages": [{"role": "user", "content": "Look up my recent activity"}]})
    print("✓ 调用完成")
    print(f"  结果类型: {type(result)}")
    print(f"  结果键: {list(result.keys())}")
except Exception as e:
    print(f"✗ 调用失败: {e}")
    import traceback

    traceback.print_exc()

print("\n=== POC 5 验证完成 ===")
