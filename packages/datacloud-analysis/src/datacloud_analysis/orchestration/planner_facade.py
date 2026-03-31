"""Facade to resolve planning context without hard coupling in planning node."""

from __future__ import annotations

from typing import Any

from datacloud_analysis.orchestration.planner_contract import PlanningContext
from datacloud_analysis.orchestration.state import AgentState


def _context_from_state(state: AgentState, query_input: str) -> PlanningContext:
    raw_tool_params = state.get("tool_params")
    return {
        "intent": str(state.get("intent") or query_input),
        "query_mode": str(state.get("query_mode") or "analysis"),
        "target_tool": str(state.get("target_tool") or ""),
        "tool_params": raw_tool_params if isinstance(raw_tool_params, dict) else {},
        "confirmed_terms": list(state.get("confirmed_terms") or []),
        "ambiguous_terms": list(state.get("ambiguous_terms") or []),
        "term_hints": list(state.get("term_hints") or []),
        "clarify_needed": bool(state.get("clarify_needed")),
        "chitchat_reply": str(state.get("chitchat_reply") or ""),
        "planning_context_source": "state",
    }


async def resolve_planning_context(
    state: AgentState,
    *,
    query_input: str,
    gateway_context: Any = None,
    default_prompts: dict[str, Any] | None = None,
    default_tools: dict[str, Any] | None = None,
) -> PlanningContext:
    """Resolve planning context directly from graph state."""
    _ = gateway_context
    _ = default_prompts
    _ = default_tools
    return _context_from_state(state, query_input)

