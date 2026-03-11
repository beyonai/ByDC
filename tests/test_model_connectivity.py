import os
from openai import OpenAI

api_key = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
base_url = "https://lab.iwhalecloud.com/gpt-proxy/v1"

client = OpenAI(api_key=api_key, base_url=base_url)

try:
    # 尝试列出模型
    models = client.models.list()
    print(f"连接成功，获取到 {len(models.data)} 个模型")
    for model in models.data[:5]:
        print(f"  - {model.id}")
except Exception as e:
    print(f"连接失败: {e}")
    import traceback

    traceback.print_exc()
