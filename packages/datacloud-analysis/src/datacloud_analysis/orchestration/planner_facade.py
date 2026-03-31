"""Facade to resolve planning context without hard coupling in planning node."""

from __future__ import annotations

import logging
import os
from typing import Any

from datacloud_analysis.orchestration.planner_contract import PlanningContext
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)

_INTENT_COMPAT_ENV = "DATACLOUD_PLANNING_INTENT_COMPAT"


def _is_intent_compat_enabled() -> bool:
    raw = str(os.getenv(_INTENT_COMPAT_ENV, "true")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


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


def _needs_intent_compat(ctx: PlanningContext) -> bool:
    query_mode = str(ctx.get("query_mode") or "").strip().lower()
    target_tool = str(ctx.get("target_tool") or "").strip()
    if query_mode in {"online_query", "agent_delegate"} and target_tool:
        return False
    if query_mode in {"analysis", "chitchat"}:
        return False
    return True


async def resolve_planning_context(
    state: AgentState,
    *,
    query_input: str,
    gateway_context: Any = None,
    default_prompts: dict[str, Any] | None = None,
    default_tools: dict[str, Any] | None = None,
) -> PlanningContext:
    """Resolve planning context from state, with optional legacy intent fallback."""
    ctx = _context_from_state(state, query_input)
    if not _needs_intent_compat(ctx):
        return ctx
    if not _is_intent_compat_enabled():
        logger.info("planning_facade: intent compat disabled, using state context only")
        return ctx

    try:
        from datacloud_analysis.orchestration.intent import intent_node

        intent_updates = await intent_node(
            state,
            gateway_context=gateway_context,
            default_prompts=default_prompts,
            default_tools=default_tools,
            query_override=query_input,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("planning_facade: intent compat fallback failed, using state context: %s", exc)
        return ctx

    raw_tool_params = intent_updates.get("tool_params")
    return {
        "intent": str(intent_updates.get("intent") or query_input),
        "query_mode": str(intent_updates.get("query_mode") or "analysis"),
        "target_tool": str(intent_updates.get("target_tool") or ""),
        "tool_params": raw_tool_params if isinstance(raw_tool_params, dict) else {},
        "confirmed_terms": list(intent_updates.get("confirmed_terms") or []),
        "ambiguous_terms": list(intent_updates.get("ambiguous_terms") or []),
        "term_hints": list(intent_updates.get("term_hints") or state.get("term_hints") or []),
        "clarify_needed": bool(intent_updates.get("clarify_needed")),
        "chitchat_reply": str(intent_updates.get("chitchat_reply") or ""),
        "planning_context_source": "intent_compat",
    }

