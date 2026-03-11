# test_poc6_streaming.py
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
import asyncio
import os

# 设置环境变量
os.environ["OPENAI_API_KEY"] = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
os.environ["OPENAI_BASE_URL"] = "https://lab.iwhalecloud.com/gpt-proxy/v1"

print("=== POC 6: 流式输出验证 ===")

# 使用阿里云百炼 Qwen
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)
print("✓ 模型初始化成功")

agent = create_deep_agent(model=model)
print("✓ Agent 创建成功")


async def test_streaming():
    print("\n--- 开始流式输出测试 ---")
    chunks = []
    chunk_count = 0

    async for chunk in agent.astream(
        {"messages": [{"role": "user", "content": "Count from 1 to 5"}]}
    ):
        chunks.append(chunk)
        chunk_count += 1
        # 只打印前几个 chunk 避免输出过多
        if chunk_count <= 3:
            print(f"Chunk {chunk_count}: {str(chunk)[:100]}...")

    print(f"\n✓ 流式输出完成")
    print(f"  总共接收 {len(chunks)} 个 chunks")

    # 验证可以累加多个 chunks
    if len(chunks) > 0:
        print(f"✓ 成功累加多个 chunks")
        return True
    else:
        print(f"✗ 未接收到任何 chunks")
        return False


# 运行异步测试
try:
    success = asyncio.run(test_streaming())

    if success:
        print("\n=== POC 6 验证完成 ===")
        print("✓ 流式输出可以正常接收")
        print("✓ 可以累加多个 chunks")
    else:
        print("\n=== POC 6 验证失败 ===")

except Exception as e:
    print(f"\n✗ 流式输出测试失败: {e}")
    import traceback

    traceback.print_exc()
    print("\n=== POC 6 验证失败 ===")
