"""Single-todo ReAct capability selector.

Provides a best-effort function-call based selector and deterministic fallback.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool


class ReactSelection(TypedDict):
    """Capability selection result for one ReAct round."""

    capability_id: str
    source: str
    reason: str
    tool_call_id: str | None
    param_overrides: dict[str, Any]


@tool("choose_capability")
def choose_capability(
    capability_id: str,
    reason: str = "",
    param_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Choose one capability from candidate list for current todo."""
    return {
        "capability_id": capability_id,
        "reason": reason,
        "param_overrides": dict(param_overrides or {}),
    }


def _is_function_call_enabled(state: Mapping[str, Any]) -> bool:
    raw = state.get("react_function_call_enabled")
    if raw is None:
        env_raw = os.getenv("DATACLOUD_REACT_FUNCTION_CALL_ENABLED", "true").strip().lower()
        return env_raw not in {"0", "false", "no", "off"}
    return bool(raw)


def _extract_tool_call_choice(ai_message: Any, candidates: list[str]) -> ReactSelection | None:
    tool_calls = getattr(ai_message, "tool_calls", None) or []
    if not isinstance(tool_calls, list):
        return None
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        args = call.get("args")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (TypeError, ValueError):
                args = {}
        if not isinstance(args, dict):
            args = {}
        capability_id = str(args.get("capability_id") or "").strip()
        if capability_id in candidates:
            raw_param_overrides = args.get("param_overrides")
            param_overrides = raw_param_overrides if isinstance(raw_param_overrides, dict) else {}
            return {
                "capability_id": capability_id,
                "source": "llm_function_call",
                "reason": str(args.get("reason") or ""),
                "tool_call_id": str(call.get("id") or "") or None,
                "param_overrides": dict(param_overrides),
            }
    return None


def _fallback_selection(candidates: list[str], *, reason: str = "") -> ReactSelection:
    return {
        "capability_id": candidates[0] if candidates else "",
        "source": "fallback",
        "reason": reason,
        "tool_call_id": None,
        "param_overrides": {},
    }


def _trim_text(value: str, *, limit: int = 2000) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[:limit]


async def select_react_capability(
    *,
    state: Mapping[str, Any],
    todo: dict[str, Any],
    candidates: list[str],
    round_index: int,
    todo_md_summary: str | None = None,
    observe: str | None = None,
) -> ReactSelection:
    """Select one capability for current round.

    Selection order:
    1) LLM function-call (`choose_capability`) when enabled and model available.
    2) Deterministic fallback to first candidate.
    """
    if not candidates:
        return _fallback_selection([], reason="empty_candidates")

    if not _is_function_call_enabled(state):
        return _fallback_selection(candidates, reason="function_call_disabled")

    model = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    if not model.startswith("openai:"):
        model = f"openai:{model}"

    try:
        llm = init_chat_model(
            model,
            model_provider="openai",
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
            temperature=0,
            streaming=False,
        ).bind_tools([choose_capability], tool_choice="choose_capability")
    except Exception:
        return _fallback_selection(candidates, reason="bind_tools_unavailable")

    goal = str(todo.get("goal") or "")
    term_context = todo.get("term_context")
    term_context_text = json.dumps(term_context, ensure_ascii=False)[:1000]
    user_query = str(state.get("enriched_query") or state.get("user_query") or "")
    system_parts = [
        "你是执行器能力选择器。必须调用工具 choose_capability，"
        "并从候选 capability_id 中精确选择一个。"
    ]
    if todo_md_summary:
        system_parts.append(f"\n## 当前任务进度\n{_trim_text(todo_md_summary)}")
    if observe:
        system_parts.append(f"\n## 上一轮执行结果\n{_trim_text(observe)}")
    messages = [
        SystemMessage(content="".join(system_parts)),
        HumanMessage(
            content=(
                f"round={round_index}\n"
                f"user_query={user_query}\n"
                f"todo_goal={goal}\n"
                f"candidates={candidates}\n"
                f"term_context={term_context_text}\n"
                "只选择一个最合适能力。"
            )
        ),
    ]
    try:
        ai_message = await llm.ainvoke(messages)
    except Exception:
        return _fallback_selection(candidates, reason="llm_invoke_failed")

    choice = _extract_tool_call_choice(ai_message, candidates)
    if choice is not None:
        return choice
    return _fallback_selection(candidates, reason="no_valid_tool_call")

