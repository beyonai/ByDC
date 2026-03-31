"""Knowledge enhancement node for the 5-node main pipeline."""

from __future__ import annotations

import json
import logging
from typing import Any

from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tools.knowledge import search_knowledge

logger = logging.getLogger(__name__)
_DEFAULT_TERM_HINT_CONFIDENCE_THRESHOLD = 0.8
_EMPTY_PREVIEW = "无"


def _last_user_text(messages: list[Any]) -> str:
    if not messages:
        return ""
    last = messages[-1]
    content = getattr(last, "content", "")
    if isinstance(content, str):
        return content
    return str(content)


def _term_hint_confidence_threshold(state: AgentState) -> float:
    raw = state.get("term_hint_confidence_threshold")
    if raw is None:
        return _DEFAULT_TERM_HINT_CONFIDENCE_THRESHOLD
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "knowledge_enhance_node: invalid term_hint_confidence_threshold=%r fallback=%s",
            raw,
            _DEFAULT_TERM_HINT_CONFIDENCE_THRESHOLD,
        )
        return _DEFAULT_TERM_HINT_CONFIDENCE_THRESHOLD


def _extract_term_hints(
    payload: dict[str, Any] | None,
    *,
    confidence_threshold: float,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    hints: list[dict[str, Any]] = []
    for row in payload.get("term_matches", []) or []:
        if not isinstance(row, dict):
            continue
        confidence = float(row.get("match_score", 0.0) or 0.0)
        if confidence < confidence_threshold:
            continue
        hints.append(
            {
                "mention": str(row.get("term_name", "")),
                "normalized_term": str(row.get("term_name", "")),
                "term_id": str(row.get("term_id", "")),
                "confidence": confidence,
                "source": "knowledge_match",
                "semantic_type": "",
                "note": "",
            }
        )
    return hints


def _build_knowledge_snippets(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    snippets: list[dict[str, Any]] = []
    if payload.get("term_matches"):
        snippets.append({"source": "term_matches", "data": payload.get("term_matches", [])})
    if payload.get("fuzzy_term_matches"):
        snippets.append({"source": "fuzzy_term_matches", "data": payload.get("fuzzy_term_matches", [])})
    return snippets


async def knowledge_enhance_node(
    state: AgentState,
    gateway_context: Any = None,
) -> dict[str, Any]:
    """Build structured enhancement artifacts for downstream planning."""
    _ = gateway_context
    user_query = _last_user_text(list(state.get("messages", [])))
    if not user_query.strip():
        return {
            "user_query": "",
            "enriched_query": "",
            "term_hints": [],
            "knowledge_snippets": [],
            "knowledge_payload": {},
            "knowledge_preview": _EMPTY_PREVIEW,
        }

    payload_raw = await search_knowledge.ainvoke({"query": user_query})
    payload = payload_raw if isinstance(payload_raw, dict) else {}
    preview = json.dumps(payload, ensure_ascii=False)[:500] if payload else _EMPTY_PREVIEW
    confidence_threshold = _term_hint_confidence_threshold(state)

    return {
        "user_query": user_query,
        "enriched_query": user_query,
        "term_hints": _extract_term_hints(payload, confidence_threshold=confidence_threshold),
        "knowledge_snippets": _build_knowledge_snippets(payload),
        "knowledge_payload": payload,
        "knowledge_preview": preview,
    }
