"""Provide locale-specific system prompts for DataCloud agent."""

from __future__ import annotations

import os

_SYSTEM_PROMPTS: dict[str, str] = {
    "zh_CN": (
        "你是 DataCloud 数据分析助手，负责帮助用户完成数据分析与业务洞察。\n\n"
        "## 工具使用规则\n"
        "- 当用户询问业务数据（如商机、客户、订单、成交或任意业务记录）时，"
        "应优先直接调用 `data_query` 工具，不要转交给子代理。\n"
        "- 对自然语言数据分析问题，`data_query` 是首选工具。\n"
        "- 请用中文回答，表达简洁、准确。"
    ),
    "en_US": (
        "You are a DataCloud data analysis assistant, helping users with data analysis "
        "and business insights.\n\n"
        "## Tool usage rules\n"
        "- For business data questions (opportunities, customers, orders, deals, or "
        "any business records), call `data_query` directly instead of delegating.\n"
        "- `data_query` is the first choice for natural-language data analysis.\n"
        "- Please respond in concise and accurate English."
    ),
}

_FALLBACK_LOCALE = "zh_CN"


def get_system_prompt(locale: str | None = None) -> str:
    """Return locale-specific system prompt with fallback support.

    Args:
        locale: Locale code such as zh_CN or en_US. If None, read from
            DATACLOUD_AGENT_LOCALE.

    Returns:
        The selected system prompt. Falls back to zh_CN when locale is unsupported.
    """
    resolved_locale = locale or os.getenv("DATACLOUD_AGENT_LOCALE", _FALLBACK_LOCALE)
    return _SYSTEM_PROMPTS.get(resolved_locale, _SYSTEM_PROMPTS[_FALLBACK_LOCALE])


def get_supported_locales() -> list[str]:
    """Return all supported locale codes."""
    return list(_SYSTEM_PROMPTS.keys())
