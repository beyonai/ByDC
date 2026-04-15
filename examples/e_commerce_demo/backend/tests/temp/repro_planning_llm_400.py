"""Reproduce planning LLM 400 errors with the backend `.env` settings.

This script mirrors the request shape used by
`datacloud_analysis.orchestration.planning.decomposer.decompose_analysis_plan()`
and prints the raw HTTP response body so we can determine whether the failure
comes from model naming, gateway validation, or request payload shape.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage


PLANNER_STATIC_SYSTEM = """你是一个任务规划专家。请将分析目标拆解为具体子任务。\
如果单次数据查询即可解答，只输出一个子任务。

## 支持的任务类型

| type | 使用场景 |
|------|---------|
| [来自本轮 HumanMessage 的可用动态工具名] | 向挂载的外部服务查询原始数据，将其本身作为 type 名并根据工具要求在 params 中提供请求参数 |
| code_exec | 对已查询到的数据文件进行计算/统计/关联分析，必须有 deps，须在 params.code 中提供 Python 代码 |
| render_report | 生成报告 |

## 判断规则（重要）

- 问候、寒暄、感谢等与数据分析无关的闲聊：不应由本节点处理（上游应路由为 chitchat）；若仍进入本节点，禁止单独规划仅有 render_report 的任务
- render_report 仅用于在已有查询或 code_exec 结果之后组装最终报告，且不得作为全 plan 中唯一任务，除非前置任务已提供可引用的数据摘要
- 任务需要"从系统查询/获取数据" -> 必须从【可用动态工具】列表中挑选动作作为 type，deps 可为空
- 任务是"基于已查结果进行统计/汇总/计算/关联"且有前置任务 -> 必须使用 code_exec，不得使用查询工具
- deps 为空的任务禁止使用 code_exec
- 对于任何 `*_query` 类型任务，`params` 里必须包含 `query`（或 `question`），禁止返回空 `params`

## code_exec 的 Python 代码约定

- 变量 `input_files` 已注入，类型为 dict，key = 前置任务 id，value = JSONL 文件绝对路径
- JSONL 格式：第一行是 meta（含 columns、total 字段），后续每行是一条数据记录
- 可直接使用 `pandas`（as pd）和 `json` 模块，无需 import（已预置）
- 将最终计算结果赋值给 `_result` 变量（类型为 list[dict] 或 dict）
- 同时用 print() 输出关键结果摘要

## 返回格式

返回严格的 JSON 数组，每个元素包含：
- "id": 任务ID（如 t1、t2）
- "type": 任务类型
- "description": 任务描述
- "status": "pending"
- "deps": 依赖的前置任务ID列表
- "params": 执行所需的参数对象
"""


def _load_env() -> Path:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path)
    return env_path


def _reasoning_config() -> tuple[str, str, str]:
    model = os.getenv("DATACLOUD_LLM_MODEL", "Qwen/Qwen3-235B-A22B")
    api_key = os.getenv("DATACLOUD_LLM_API_KEY", "")
    base_url = os.getenv("DATACLOUD_LLM_API_BASE", "")
    return model, api_key, base_url


def _build_messages(*, intent: str, tools: list[str]) -> list[dict[str, str]]:
    tools_line = ", ".join(sorted(tools)) if tools else "（无动态工具）"
    return [
        {"role": "system", "content": PLANNER_STATIC_SYSTEM},
        {
            "role": "user",
            "content": (
                f"【可用动态工具列表】：{tools_line}\n\n"
                f"【需要分析的目标】：{intent}\n\n"
                "请输出 JSON 任务数组。"
            ),
        },
    ]


def _trim_text(value: str, limit: int = 1200) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...(truncated)"


async def _call_httpx(*, model: str, api_key: str, base_url: str, messages: list[dict[str, str]]) -> None:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print("\n=== httpx direct request ===")
    print(f"url={url}")
    print(f"model={model}")
    print(f"message_count={len(messages)}")
    print(f"system_len={len(messages[0]['content'])}")
    print(f"user_len={len(messages[1]['content'])}")
    print(f"payload_preview={_trim_text(json.dumps(payload, ensure_ascii=False))}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        print(f"status_code={response.status_code}")
        print(f"response_text={_trim_text(response.text, 4000)}")
        try:
            print(f"response_json={json.dumps(response.json(), ensure_ascii=False, indent=2)[:4000]}")
        except Exception:
            print("response_json=<not-json>")


async def _call_langchain(*, model: str, api_key: str, base_url: str, messages: list[dict[str, str]]) -> None:
    lc_model = model if model.startswith("openai:") else f"openai:{model}"
    llm = init_chat_model(
        model=lc_model,
        api_key=api_key,
        base_url=base_url,
    )

    print("\n=== langchain request ===")
    print(f"langchain_model={lc_model}")
    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=messages[0]["content"]),
                HumanMessage(content=messages[1]["content"]),
            ]
        )
        print(f"response_type={type(response).__name__}")
        print(f"response_content={_trim_text(str(response.content), 4000)}")
    except Exception as exc:  # noqa: BLE001
        print(f"langchain_exception_type={type(exc).__name__}")
        print(f"langchain_exception={exc}")
        body = getattr(getattr(exc, "response", None), "text", None)
        if body:
            print(f"langchain_response_text={_trim_text(str(body), 4000)}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduce planning LLM 400 responses.")
    parser.add_argument("--intent", default="查询企业综合分析表的100条数据")
    parser.add_argument(
        "--tools",
        nargs="*",
        default=["debug_10005080", "group_agg", "time_series"],
        help="Dynamic tools shown to the planner",
    )
    parser.add_argument("--httpx-only", action="store_true")
    args = parser.parse_args()

    env_path = _load_env()
    model, api_key, base_url = _reasoning_config()
    messages = _build_messages(intent=args.intent, tools=args.tools)

    print(f"loaded_env={env_path}")
    print(f"base_url={base_url}")
    print(f"model={model}")
    print(f"api_key_present={bool(api_key)}")

    await _call_httpx(model=model, api_key=api_key, base_url=base_url, messages=messages)
    if not args.httpx_only:
        await _call_langchain(model=model, api_key=api_key, base_url=base_url, messages=messages)


if __name__ == "__main__":
    asyncio.run(main())
