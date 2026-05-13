"""i18n helpers for datacloud-knowledge prompts and labels."""

from __future__ import annotations

import os

from .prompts import (
    _FALLBACK_LOCALE,
    _SYSTEM_PROMPTS,
    get_annotation_format,
    get_confirm_labels,
    get_confirm_prompt,
    get_paradigm_labels,
    get_supported_locales,
)


def resolve_locale(locale: str | None = None) -> str:
    """Resolve locale from explicit value, env var, or fallback.

    Args:
        locale: Explicit locale code. If None, reads ``DATACLOUD_AGENT_LOCALE``.

    Returns:
        Validated locale code, falling back to ``"zh_CN"``.
    """
    resolved = locale or os.getenv("DATACLOUD_AGENT_LOCALE", _FALLBACK_LOCALE)
    if resolved not in _SYSTEM_PROMPTS:
        return _FALLBACK_LOCALE
    return resolved


__all__ = [
    "get_annotation_format",
    "get_confirm_labels",
    "get_confirm_prompt",
    "get_paradigm_labels",
    "get_supported_locales",
    "resolve_locale",
]
