"""Clarification runtime shim for execution node."""

from __future__ import annotations

from typing import Any

from datacloud_analysis.orchestration.state import AgentState


async def clarification_node(
    state: AgentState,
    *,
    gateway_context: Any = None,
) -> dict[str, Any]:
    """Return clarification updates for execution stage.

    Current implementation keeps unresolved ambiguous terms unchanged and
    lets the execution node trigger HITL interruption path.
    """
    _ = gateway_context
    return {
        "ambiguous_terms": list(state.get("ambiguous_terms") or []),
        "confirmed_terms": list(state.get("confirmed_terms") or []),
        "clarify_needed": bool(state.get("ambiguous_terms")),
    }
