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
