"""Compatibility clarification node for execution-stage ambiguous terms."""

from __future__ import annotations

from typing import Any, cast

from langgraph.types import interrupt

from datacloud_analysis.orchestration.state import AgentState


def _build_prompt(term: dict[str, Any]) -> str:
    mention = str(term.get("mention") or term.get("term_name") or "").strip()
    if not mention:
        mention = "该术语"
    return f"「{mention}」未找到匹配的业务术语，请描述它的含义，或回车跳过。"


def _resolve_reply(raw: Any) -> str:
    if isinstance(raw, dict):
        value = (
            raw.get("user_input")
            or raw.get("answer")
            or raw.get("content")
            or raw.get("value")
            or ""
        )
        return str(value).strip()
    return str(raw or "").strip()


async def clarification_node(
    state: AgentState,
    gateway_context: Any = None,
) -> dict[str, Any]:
    """Clarify one ambiguous term via interrupt/resume.

    This module keeps compatibility for execution node imports after orchestration
    package restructuring. It resolves at most one ambiguous term per invocation.
    """
    _ = gateway_context
    ambiguous_terms = list(state.get("ambiguous_terms") or [])
    if not ambiguous_terms:
        return {"ambiguous_terms": [], "clarify_needed": False}

    current = cast(dict[str, Any], ambiguous_terms[0])
    prompt = _build_prompt(current)
    resume_value = interrupt(
        {
            "reason_code": "TERM_CLARIFICATION_REQUIRED",
            "prompt": prompt,
            "required_fields": ["user_input"],
            "todo_id": str(state.get("todo_active_id") or ""),
            "react_step_id": str(state.get("todo_active_id") or ""),
            "interrupt_reason": "term_clarification",
        }
    )

    user_reply = _resolve_reply(resume_value)
    if not user_reply:
        # Empty reply means skip this term and continue.
        remaining = ambiguous_terms[1:]
        return {
            "ambiguous_terms": remaining,
            "clarify_needed": bool(remaining),
        }

    mention = str(current.get("mention") or current.get("term_name") or "").strip() or user_reply
    confirmed_terms = list(state.get("confirmed_terms") or [])
    confirmed_terms.append(
        {
            **current,
            "mention": mention,
            "term_name": user_reply,
            "source": "user_clarification",
            "confidence": 1.0,
        }
    )
    session_alias_map = dict(state.get("session_alias_map") or {})
    session_alias_map[mention] = user_reply
    remaining = ambiguous_terms[1:]
    return {
        "confirmed_terms": confirmed_terms,
        "session_alias_map": session_alias_map,
        "ambiguous_terms": remaining,
        "clarify_needed": bool(remaining),
    }

