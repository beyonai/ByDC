import os, sys

sys.stdout.flush()
os.environ["OPENAI_API_KEY"] = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
os.environ["OPENAI_BASE_URL"] = "https://lab.iwhalecloud.com/gpt-proxy/v1"

from langchain.chat_models import init_chat_model

print("1. 导入 deepagents...")
from deepagents import create_deep_agent

print("2. 初始化模型...")
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)
print("3. 模型初始化完成")
print(f"   模型类型: {type(model)}")

subagents = [
    {
        "name": "researcher",
        "description": "Research specialist",
        "system_prompt": "You are a research expert.",
    }
]
print("4. 子 Agent 配置准备完成")

print("5. 创建 deep agent...")
try:
    agent = create_deep_agent(model=model, subagents=subagents)
    print("6. Agent 创建成功")
    print(f"   Agent 类型: {type(agent)}")
except Exception as e:
    print(f"6. Agent 创建失败: {e}")
    import traceback

    traceback.print_exc()

print("7. 脚本完成")
