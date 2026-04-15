"""意图理解公共工具函数。"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


def extract_json_from_text(text: str) -> dict[str, Any] | None:
    """从 LLM 文本输出中兜底提取 JSON 对象。

    解析策略（按优先级）：
    1. 提取 ```json ... ``` 代码块
    2. 查找最后一个含 select/query/decisions 关键字的 {...} 对象
    """
    # 策略 1：```json ... ``` 块
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        raw = m.group(1).strip()
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

    # 策略 2：最后一个含关键字段的 {...}
    matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    for candidate in reversed(matches):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and (
                "select" in obj or "query" in obj or "decisions" in obj
            ):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def build_llm() -> Any:
    """构建 LLM 实例（懒导入 langchain，不增加硬依赖）。

    按优先级读取环境变量：DATACLOUD_LLM → OPENAI 兜底。
    """
    from langchain.chat_models import init_chat_model  # noqa: PLC0415

    for env_prefix in ("DATACLOUD_LLM", "OPENAI"):
        api_base = os.getenv(f"{env_prefix}_API_BASE", "")
        api_key = os.getenv(f"{env_prefix}_API_KEY", "")
        model = os.getenv(f"{env_prefix}_MODEL", "")
        if api_base and api_key and model:
            temperature = float(os.getenv(f"{env_prefix}_TEMPERATURE", "0.0"))
            return init_chat_model(
                model=model,
                model_provider="openai",
                api_key=api_key,
                base_url=api_base,
                temperature=temperature,
            )
    # 兜底
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return init_chat_model(
        model=model,
        model_provider="openai",
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
    )
