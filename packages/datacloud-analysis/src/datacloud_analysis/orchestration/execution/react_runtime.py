"""Single-todo ReAct capability selector.

Provides a best-effort function-call based selector and deterministic fallback.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from typing import Any, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from datacloud_analysis.orchestration.shared import (
    resolve_reasoning_api_key,
    resolve_reasoning_base_url,
    resolve_reasoning_model_spec,
)

logger = logging.getLogger(__name__)


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


def _trim_log_text(value: str, limit: int = 1200) -> str:
    """Return a log-safe truncated string."""
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...(truncated)"


def _exception_response_text(exc: Exception) -> str:
    """Extract response body text from HTTP/client exceptions when present."""
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    text = getattr(response, "text", "")
    return text if isinstance(text, str) else ""


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
        logger.info(
            "react_runtime: skipping LLM (function-call disabled) candidates=%s round=%d",
            candidates,
            round_index,
        )
        return _fallback_selection(candidates, reason="function_call_disabled")

    model_spec = resolve_reasoning_model_spec(
        os.getenv("DATACLOUD_LLM_REASONING_MODEL", "Qwen/Qwen3-235B-A22B")
    )
    raw_model = model_spec["raw_model"]
    model = model_spec["model"]
    model_provider = model_spec["model_provider"]
    provider_prefixed = model_spec["provider_prefixed"]
    api_key = resolve_reasoning_api_key()
    base_url = resolve_reasoning_base_url()
    todo_id = str(todo.get("todo_id") or "")

    logger.info(
        "react_runtime: preparing bind_tools for function-call "
        "model=%s raw_model=%s model_provider=%s provider_prefixed=%s "
        "base_url=%s api_key_present=%s round=%d todo_id=%s candidate_count=%d candidates=%s",
        model,
        raw_model,
        model_provider,
        provider_prefixed,
        base_url or "",
        bool(api_key),
        round_index,
        todo_id,
        len(candidates),
        candidates,
    )

    try:
        llm = init_chat_model(
            model,
            model_provider=model_provider,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            streaming=False,
        )
        llm = llm.bind_tools([choose_capability], tool_choice="choose_capability")
        logger.info(
            "react_runtime: bind_tools success model=%s raw_model=%s model_provider=%s "
            "round=%d todo_id=%s candidates=%s",
            model,
            raw_model,
            model_provider,
            round_index,
            todo_id,
            candidates,
        )
    except Exception as exc:
        response_text = _exception_response_text(exc)
        logger.warning(
            "react_runtime: bind_tools failed, fallback to first candidate: %s; "
            "model=%s raw_model=%s model_provider=%s provider_prefixed=%s "
            "base_url=%s api_key_present=%s candidates=%s round=%d todo_id=%s response_text=%s",
            exc,
            model,
            raw_model,
            model_provider,
            provider_prefixed,
            base_url or "",
            bool(api_key),
            candidates,
            round_index,
            todo_id,
            _trim_log_text(response_text, 2000),
        )
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
    system_content = "".join(system_parts)
    human_content = (
        f"round={round_index}\n"
        f"user_query={user_query}\n"
        f"todo_goal={goal}\n"
        f"candidates={candidates}\n"
        f"term_context={term_context_text}\n"
        "只选择一个最合适能力。"
    )
    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=human_content),
    ]
    logger.info(
        "react_runtime: llm request (function-call choose_capability) model=%s raw_model=%s "
        "model_provider=%s provider_prefixed=%s base_url=%s api_key_present=%s "
        "round=%d candidate_count=%d candidates=%s function_call_enabled=%s "
        "system_len=%d user_msg_len=%d todo_md_len=%d observe_len=%d todo_id=%s",
        model,
        raw_model,
        model_provider,
        provider_prefixed,
        base_url or "",
        bool(api_key),
        round_index,
        len(candidates),
        candidates,
        _is_function_call_enabled(state),
        len(system_content),
        len(human_content),
        len(todo_md_summary or ""),
        len(observe or ""),
        todo_id,
    )
    try:
        ai_message = await llm.ainvoke(messages)
    except Exception as exc:
        response_text = _exception_response_text(exc)
        logger.warning(
            "react_runtime: llm ainvoke failed, fallback to first candidate: %s; "
            "model=%s raw_model=%s model_provider=%s provider_prefixed=%s base_url=%s "
            "candidates=%s round=%d todo_id=%s response_text=%s",
            exc,
            model,
            raw_model,
            model_provider,
            provider_prefixed,
            base_url or "",
            candidates,
            round_index,
            todo_id,
            _trim_log_text(response_text, 2000),
        )
        return _fallback_selection(candidates, reason="llm_invoke_failed")

    choice = _extract_tool_call_choice(ai_message, candidates)
    if choice is not None:
        logger.info(
            "react_runtime: selection ok capability_id=%s source=%s reason=%s round=%d todo_id=%s",
            choice.get("capability_id"),
            choice.get("source"),
            _trim_log_text(str(choice.get("reason") or ""), 300),
            round_index,
            todo_id,
        )
        return choice
    logger.warning(
        "react_runtime: no valid tool_call in model output, fallback to first candidate; "
        "candidates=%s round=%d todo_id=%s fallback_reason=%s",
        candidates,
        round_index,
        todo_id,
        "no_valid_tool_call",
    )
    return _fallback_selection(candidates, reason="no_valid_tool_call")
