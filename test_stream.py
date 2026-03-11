import asyncio
from langchain.chat_models import init_chat_model

async def main():
    model = init_chat_model(
        model='openai:Qwen/Qwen3-235B-A22B',
        api_key='sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf',
        base_url='https://lab.iwhalecloud.com/gpt-proxy/v1'
    )
    try:
        async for c in model.astream('tell me a short joke'):
            print(repr(c.content))
    except Exception as e:
        print(f"ERROR: {type(e).__name__} - {e}")

asyncio.run(main())
