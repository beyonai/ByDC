"""Contracts for planning context resolution."""

from __future__ import annotations

from typing import Any, TypedDict


class PlanningContext(TypedDict, total=False):
    """Normalized planning context consumed by planning_node."""

    intent: str
    query_mode: str
    target_tool: str
    tool_params: dict[str, Any]
    confirmed_terms: list[dict[str, Any]]
    ambiguous_terms: list[dict[str, Any]]
    term_hints: list[dict[str, Any]]
    clarify_needed: bool
    chitchat_reply: str
    planning_context_source: str

