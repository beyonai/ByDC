"""测试阿里云百炼各模型 OpenAI 兼容接口连通性.

使用 openai SDK 通过 OpenAI 兼容协议测试每个模型的 chat completions 接口。
"""

import os
import time

from openai import OpenAI

BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "sk-7dc821fff0e7459ab74a2cc65bdcbe8c")

MODELS = [
    "qwen3.6-35b-a3b",
    "qwen3.6-27b",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "kimi-k2.6",
    "glm-5.1",
]

TEST_PROMPT = "请用一句话介绍你自己。"
TIMEOUT = 120.0


def test_model(model: str, client: OpenAI) -> dict:
    """测试单个模型连通性."""
    result: dict = {
        "model": model,
        "status": "fail",
        "duration": 0.0,
        "error": "",
        "usage": {},
    }

    start = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": TEST_PROMPT}],
            max_tokens=256,
            timeout=TIMEOUT,
        )
        result["duration"] = round(time.time() - start, 2)

        content = response.choices[0].message.content or ""
        result["status"] = "ok"
        result["reply_preview"] = content[:100]
        result["usage"] = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
    except Exception as e:
        result["duration"] = round(time.time() - start, 2)
        result["error"] = f"{type(e).__name__}: {e}"

    return result


def print_report(results: list[dict]) -> None:
    """打印测试报告."""
    print("\n" + "=" * 90)
    print(f"{'模型':<25} {'状态':<8} {'耗时(s)':<10} {'摘要'}")
    print("-" * 90)

    ok_count = 0
    for r in results:
        status = r["status"]
        if status == "ok":
            ok_count += 1
            tokens = r["usage"].get("total_tokens", "?")
            summary = f"{r['reply_preview'][:50]}  (tokens: {tokens})"
        else:
            summary = r.get("error", "")[:60]

        print(f"{r['model']:<25} {status:<8} {r['duration']:<10} {summary}")

    print("-" * 90)
    print(f"总计: {ok_count}/{len(results)} 连通")
    print("=" * 90)


def main() -> None:
    """运行全部模型测试."""
    print("开始测试阿里云百炼模型连通性 ...")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key:  {API_KEY[:8]}****{API_KEY[-4:]}")

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

    # 先测试 /models 接口
    print("\n[1] 测试 /models 接口 ...")
    try:
        models_page = client.models.list()
        model_list = list(models_page)
        print(f"    可用模型数: {len(model_list)}")
        model_ids = [m.id for m in model_list[:10]]
        print(f"    前10个: {', '.join(model_ids)}")
    except Exception as e:
        print(f"    异常: {e}")

    # 逐个测试对话模型
    print("\n[2] 逐个测试对话模型 ...")
    results: list[dict] = []
    for model in MODELS:
        print(f"  测试 {model} ...", end="", flush=True)
        result = test_model(model, client)
        results.append(result)
        status_icon = "OK" if result["status"] == "ok" else "FAIL"
        print(f" [{status_icon}] {result['duration']}s")

    print_report(results)


if __name__ == "__main__":
    main()
