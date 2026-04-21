"""Helpers for reading LangGraph ``messages`` (Human/AI turns)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage


def last_human_text(messages: list[Any] | None) -> str:
    """Return the trimmed text of the most recent HumanMessage, or empty string."""
    if not messages:
        return ""
    for m in reversed(messages):
        if not isinstance(m, HumanMessage):
            continue
        raw = m.content
        if isinstance(raw, str):
            return raw.strip()
        return str(raw).strip()
    return ""


def extract_ai_text(content: Any) -> str:
    """从 AIMessage.content 提取纯文字（text block）内容，过滤 thinking 等非文字块。

    兼容三种情况：
    - OpenAI / 普通 LLM：content 为 str，直接返回
    - Anthropic extended thinking：content 为 list，只拼接 type=="text" 的块
    - 对象形式（ThinkingBlock / TextBlock）：通过 attr 访问 type / text
    - 其他意外类型：安全降级为 str()，不抛异常
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            try:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(str(block.get("text", "")))
                else:
                    if getattr(block, "type", None) == "text":
                        parts.append(str(getattr(block, "text", "")))
            except Exception:  # noqa: BLE001
                pass
        return "".join(parts)
    try:
        return str(content)
    except Exception:  # noqa: BLE001
        return ""
