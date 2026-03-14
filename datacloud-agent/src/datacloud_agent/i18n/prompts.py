"""Locale-specific system prompts for datacloud-agent.

To add a new language, insert a new key into ``_SYSTEM_PROMPTS``.
No other module needs to change.
"""

from __future__ import annotations

_SYSTEM_PROMPTS: dict[str, str] = {
    "zh_CN": (
        "你是 DataCloud 数据云分析助手，帮助用户进行数据分析与业务洞察。\n\n"
        "## 工具使用规则\n"
        "- **先调用 `search_knowledge`** 获取相关知识（如 KPI 定义、评价标准、实体关系等）。"
        "例如用户问「王小明优秀吗」时，需先查知识图谱了解优秀的标准和关联的 KPI。\n"
        "- 若获取到多个知识片段且涉及多个对象（如多人、多指标），"
        "**需多次调用 `data_query`** 分别查询各相关对象的数据，再综合判断。\n"
        "- 当用户询问业务数据（商机、客户、订单、合同等 CRM 记录）时，"
        "**直接调用 `data_query` 工具**，不要委托给子 agent。\n"
        "- 请用中文回复，回答简洁准确。"
    ),
    "en_US": (
        "You are a DataCloud data analysis assistant, "
        "helping users with data analysis and business insights.\n\n"
        "## Tool usage rules\n"
        "- **Call `search_knowledge` first** to retrieve relevant knowledge "
        "(e.g. KPI definitions, evaluation criteria, entity relationships). "
        "For example, when asked \"Is Wang Xiaoming excellent?\", first query "
        "the knowledge graph for excellence criteria and related KPIs.\n"
        "- If multiple knowledge snippets are returned and multiple objects "
        "(e.g. multiple people, multiple metrics) need to be queried, "
        "**call `data_query` multiple times** — once per relevant object — "
        "then synthesize the results.\n"
        "- When the user asks about business data (opportunities, customers, "
        "orders, deals, or any CRM records), call the `data_query` tool "
        "**DIRECTLY** — do NOT delegate to a subagent.\n"
        "- Please respond in English, concisely and accurately."
    ),
}

_FALLBACK_LOCALE = "zh_CN"


def get_system_prompt(locale: str | None = None) -> str:
    """Return the system prompt for the given locale.

    Resolution order:
    1. ``locale`` argument (if provided)
    2. ``DATACLOUD_AGENT_LOCALE`` environment variable
    3. Hard-coded fallback: ``zh_CN``

    If the resolved locale is not in the supported list, falls back to
    ``zh_CN`` and does NOT raise an error (graceful degradation).
    """
    if locale is None:
        from datacloud_agent.config.env import LocaleSettings
        locale = LocaleSettings().locale
    return _SYSTEM_PROMPTS.get(locale, _SYSTEM_PROMPTS[_FALLBACK_LOCALE])


def get_supported_locales() -> list[str]:
    """Return the list of supported locale codes (e.g. ['zh_CN', 'en_US'])."""
    return list(_SYSTEM_PROMPTS.keys())
