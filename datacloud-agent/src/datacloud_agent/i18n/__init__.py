"""Internationalization (i18n) helpers for datacloud-agent.

Usage::

    from datacloud_agent.i18n import get_system_prompt, get_supported_locales

    prompt = get_system_prompt("zh_CN")   # explicit locale
    prompt = get_system_prompt()          # reads DATACLOUD_AGENT_LOCALE env var
"""

from datacloud_agent.i18n.prompts import get_supported_locales, get_system_prompt

__all__ = ["get_system_prompt", "get_supported_locales"]
