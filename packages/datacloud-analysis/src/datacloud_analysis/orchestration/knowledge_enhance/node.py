"""Knowledge enhancement node for the 5-node main pipeline."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from by_framework import EventType, StreamChunkEvent
from by_framework.core.protocol.content_type import SseReasonMessageType

from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tools.knowledge import search_knowledge

logger = logging.getLogger(__name__)
_DEFAULT_TERM_HINT_CONFIDENCE_THRESHOLD = 0.8
_SUMMARY_MAX_ITEMS = 5
_SUMMARY_MAX_CHARS = 150
_SUMMARY_MIN_CHARS = 80
_SUMMARY_QUALITY_THRESHOLD = 0.4
_SNIPPET_ITEM_MAX_CHARS = 300
_SNIPPET_SIMILARITY_THRESHOLD = 0.8
_ENRICHED_MAX_CHARS = 1200
_ENRICHED_DEGRADE_MAX_ITEMS = 3
_LOG_PREVIEW_LIMIT = 200


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
        term_name = str(row.get("term_name", ""))
        normalized_term = str(row.get("normalized_term", term_name))
        hints.append(
            {
                "mention": term_name,
                "normalized_term": normalized_term,
                "term_id": str(row.get("term_id", "")),
                "confidence": confidence,
                "source": "knowledge_match",
                "semantic_type": "",
                "note": "",
            }
        )
    return hints


def _iterate_tree_nodes(tree: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(tree, dict):
        return
    stack: list[dict[str, Any]] = [tree]
    while stack:
        node = stack.pop()
        yield node
        children = node.get("children", [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    stack.append(child)


def _collect_term_knowledge(payload: dict[str, Any] | None) -> dict[str, list[str]]:
    knowledge_map: dict[str, list[str]] = {}
    if not isinstance(payload, dict):
        return knowledge_map

    def _append(term_id: str, text: str) -> None:
        if not term_id or not text:
            return
        knowledge_map.setdefault(term_id, []).append(text)

    for match in payload.get("term_matches", []) or []:
        if not isinstance(match, dict):
            continue
        term_id = str(match.get("term_id", "")).strip()
        for key in ("term_desc", "definition", "description"):
            raw_text = match.get(key)
            text = str(raw_text).strip() if raw_text is not None else ""
            _append(term_id, text)

    for subgraph in payload.get("term_subgraphs", []) or []:
        if not isinstance(subgraph, dict):
            continue
        tree = subgraph.get("tree")
        for node in _iterate_tree_nodes(tree):
            term_id = str(node.get("term_id", "")).strip()
            for raw_text in node.get("knowledge", []) or []:
                text = str(raw_text).strip()
                _append(term_id, text)

    return knowledge_map


def _truncate_text(value: str, *, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _parse_update_time(value: Any) -> datetime:
    if value is None:
        return datetime.min
    text = str(value).strip()
    if not text:
        return datetime.min
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.min


def _summary_quality_score(term_name: str, summary: str) -> float:
    text = summary.strip()
    if not text:
        return 0.0
    score = 0.0
    length = len(text)
    if length >= _SUMMARY_MIN_CHARS:
        score += 0.45
    else:
        score += max(0.0, (length / _SUMMARY_MIN_CHARS) * 0.45)
    if "：" in text or ":" in text:
        score += 0.2
    if term_name and term_name in text:
        score += 0.2
    unique_chars = len(set(text))
    if unique_chars >= 20:
        score += 0.15
    return min(score, 1.0)


def _summary_text(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if len(text) > _SUMMARY_MAX_CHARS:
        return _truncate_text(text, limit=_SUMMARY_MAX_CHARS)
    return text


def _summary_sort_key(
    hint: dict[str, Any],
    match: dict[str, Any],
) -> tuple[float, datetime]:
    confidence = float(hint.get("confidence", 0.0) or 0.0)
    update_dt = _parse_update_time(
        match.get("updateTime")
        or match.get("update_time")
        or match.get("createTime")
        or match.get("create_time")
    )
    return confidence, update_dt


def _build_confirmed_knowledge_summaries(
    payload: dict[str, Any] | None,
    term_hints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    knowledge_map = _collect_term_knowledge(payload)
    match_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict):
        for row in payload.get("term_matches", []) or []:
            if not isinstance(row, dict):
                continue
            term_id = str(row.get("term_id", "")).strip()
            if term_id:
                match_by_id[term_id] = row
    ordered_hints = sorted(
        term_hints,
        key=lambda item: _summary_sort_key(
            item,
            match_by_id.get(str(item.get("term_id", "")).strip(), {}),
        ),
        reverse=True,
    )
    summaries: list[dict[str, Any]] = []
    seen_term_ids: set[str] = set()
    for hint in ordered_hints:
        term_id = str(hint.get("term_id", "")).strip()
        if not term_id or term_id in seen_term_ids:
            continue
        seen_term_ids.add(term_id)
        knowledge_entries = knowledge_map.get(term_id) or []
        if not knowledge_entries:
            continue
        term_name = str(hint.get("normalized_term") or hint.get("mention") or term_id)
        summary_text = _summary_text(knowledge_entries[0])
        if not summary_text:
            continue
        summary_quality = _summary_quality_score(term_name, summary_text)
        summaries.append(
            {
                "term_name": term_name,
                "summary": summary_text,
                "confidence": float(hint.get("confidence", 0.0) or 0.0),
                "summary_quality": summary_quality,
            }
        )
        if len(summaries) >= _SUMMARY_MAX_ITEMS:
            break
    return summaries


def _build_confirmed_terms(
    payload: dict[str, Any] | None,
    term_hints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    match_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict):
        for row in payload.get("term_matches", []) or []:
            if not isinstance(row, dict):
                continue
            term_id = str(row.get("term_id", "")).strip()
            if term_id:
                match_by_id[term_id] = row

    confirmed_terms: list[dict[str, Any]] = []
    for hint in term_hints:
        term_id = str(hint.get("term_id", "")).strip()
        match = match_by_id.get(term_id, {})
        mention = str(hint.get("mention") or match.get("term_name") or "").strip()
        term_name = str(hint.get("normalized_term") or match.get("normalized_term") or mention).strip()
        if not mention and not term_name:
            continue
        confirmed_terms.append(
            {
                "mention": mention or term_name,
                "term_name": term_name or mention,
                "term_id": term_id,
                "term_type_code": str(match.get("term_type_code") or match.get("term_type") or ""),
                "confidence": float(hint.get("confidence", 0.0) or 0.0),
                "source": str(hint.get("source", "knowledge_match")),
            }
        )
    return confirmed_terms


def _compose_enriched_query(
    user_query: str,
    knowledge_summaries: list[dict[str, Any]],
) -> tuple[str, str, float]:
    valid_summaries = [
        item
        for item in knowledge_summaries
        if float(item.get("summary_quality", 0.0) or 0.0) >= _SUMMARY_QUALITY_THRESHOLD
    ]
    if not valid_summaries:
        return user_query, "fallback_user_query", 0.0

    bullets = [f"- {item['term_name']}：{item['summary']}" for item in valid_summaries]
    enriched = f"原始问题：\n{user_query}\n\n补充知识：\n" + "\n".join(bullets)
    if len(enriched) > _ENRICHED_MAX_CHARS:
        fallback_items = valid_summaries[:_ENRICHED_DEGRADE_MAX_ITEMS]
        fallback_bullets = [f"- {item['term_name']}：{item['summary']}" for item in fallback_items]
        enriched = f"原始问题：\n{user_query}\n\n补充知识：\n" + "\n".join(fallback_bullets)
    confidence = max(
        (float(item.get("confidence", 0.0) or 0.0) for item in valid_summaries),
        default=0.0,
    )
    return enriched, "confirmed_terms", confidence


def _extract_ambiguities(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    ambiguities: list[dict[str, Any]] = []
    for item in payload.get("fuzzy_term_matches", []) or []:
        if not isinstance(item, dict):
            continue
        mention = str(item.get("mention") or item.get("original") or "").strip()
        candidates_raw = item.get("candidates") or item.get("matches") or []
        candidates: list[dict[str, Any]] = []
        if isinstance(candidates_raw, list):
            for candidate in candidates_raw:
                if not isinstance(candidate, dict):
                    continue
                candidates.append(
                    {
                        "term_id": str(candidate.get("term_id", "")),
                        "term_name": str(candidate.get("term_name") or candidate.get("term", "")),
                        "term_type_code": str(candidate.get("term_type_code") or candidate.get("term_type", "")),
                        "similarity": float(candidate.get("similarity", 0.0) or 0.0),
                        "edit_distance": int(candidate.get("edit_distance", 0) or 0),
                    }
                )
        if mention or candidates:
            reason = "multiple_candidates" if len(candidates) > 1 else "no_high_confidence_match"
            ambiguities.append({"mention": mention, "candidates": candidates, "reason": reason})
    return ambiguities


def _safe_preview(value: str) -> str:
    text = value.strip()
    if len(text) <= _LOG_PREVIEW_LIMIT:
        return text
    return f"{text[:_LOG_PREVIEW_LIMIT]}...(truncated)"


def _log_thinking(
    *,
    user_query: str,
    summaries: list[dict[str, Any]],
    ambiguities: list[dict[str, Any]],
    enriched_query: str,
    enriched_source: str,
) -> None:
    summary_preview = "; ".join(f"{item['term_name']}:{item['summary']}" for item in summaries)
    ambiguity_preview = "; ".join(
        f"{entry['mention']}({len(entry['candidates'])})" for entry in ambiguities if entry.get("mention")
    )
    logger.info(
        "knowledge_enhance_node: user_query=%s summaries=%s ambiguities=%s enriched_source=%s enriched_preview=%s",
        _safe_preview(user_query),
        _safe_preview(summary_preview),
        _safe_preview(ambiguity_preview),
        enriched_source,
        _safe_preview(enriched_query),
    )


def _build_thinking_log(
    *,
    user_query: str,
    recognized_terms: list[str],
    summaries: list[dict[str, Any]],
    ambiguities: list[dict[str, Any]],
    enriched_query: str,
    enriched_source: str,
) -> dict[str, Any]:
    return {
        "raw_question": user_query,
        "recognized_terms": recognized_terms,
        "ambiguous_terms": ambiguities,
        "confirmed_term_summaries": summaries,
        "enriched_query": enriched_query,
        "enriched_query_source": enriched_source,
        "ambiguous_terms_count": len(ambiguities),
        "confirmed_terms_count": len(summaries),
    }


def _normalize_term_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) < 2:
        return ""
    if text in {"无", "none", "null"}:
        return ""
    return text


def _extract_recognized_terms(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for row in payload.get("term_matches", []) or []:
        if not isinstance(row, dict):
            continue
        term = _normalize_term_text(row.get("normalized_term") or row.get("term_name"))
        if term and term not in seen:
            seen.add(term)
            terms.append(term)
    for row in payload.get("fuzzy_term_matches", []) or []:
        if not isinstance(row, dict):
            continue
        mention = _normalize_term_text(row.get("mention") or row.get("original"))
        if mention and mention not in seen:
            seen.add(mention)
            terms.append(mention)
    return terms


def _format_recognized_terms_line(recognized_terms: list[str]) -> str:
    if not recognized_terms:
        return "1、本次识别出来的术语清单：【无】"
    return f"1、本次识别出来的术语清单：【{'、'.join(recognized_terms)}】"


def _format_confirmed_terms_block(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return "2、已确权的清单是：【无】"
    names = [str(item.get("term_name") or "").strip() for item in summaries]
    names = [name for name in names if name]
    lines = [f"2、已确权的清单是：【{'、'.join(names) if names else '无'}】"]
    for index, item in enumerate(summaries, start=1):
        term_name = str(item.get("term_name") or "").strip() or "未命名术语"
        summary = str(item.get("summary") or "").strip() or "无补充知识"
        lines.append(f"{index}）{term_name}：{summary}")
    return "\n".join(lines)


def _format_ambiguous_terms_block(ambiguities: list[dict[str, Any]]) -> str:
    if not ambiguities:
        return "3、待澄清的清单是：【无】"
    mentions: list[str] = []
    lines: list[str] = []
    for index, entry in enumerate(ambiguities, start=1):
        mention = str(entry.get("mention") or entry.get("term") or "").strip() or "未命名术语"
        mentions.append(mention)
        candidates_raw = entry.get("candidates") or []
        candidate_names: list[str] = []
        if isinstance(candidates_raw, list):
            for candidate in candidates_raw[:5]:
                if not isinstance(candidate, dict):
                    continue
                name = str(candidate.get("term_name") or candidate.get("name") or "").strip()
                if name:
                    candidate_names.append(name)
        reason = str(entry.get("reason") or "").strip() or "待用户补充"
        candidate_text = "、".join(candidate_names) if candidate_names else "暂无候选"
        lines.append(f"{index}）{mention}：候选={candidate_text}；原因={reason}")
    return f"3、待澄清的清单是：【{'、'.join(mentions)}】\n" + "\n".join(lines)


def _format_enhanced_context_block(user_query: str, enriched_query: str) -> str:
    if enriched_query.strip() == user_query.strip():
        knowledge_text = "无（回退为原始问题）"
    else:
        knowledge_text = enriched_query
    return (
        "4、增强的上下文是如下：\n"
        f"{user_query}\n"
        f"{knowledge_text}"
    )


def _format_thinking_report(
    *,
    recognized_terms: list[str],
    summaries: list[dict[str, Any]],
    ambiguities: list[dict[str, Any]],
    user_query: str,
    enriched_query: str,
) -> str:
    blocks = [
        _format_recognized_terms_line(recognized_terms),
        _format_confirmed_terms_block(summaries),
        _format_ambiguous_terms_block(ambiguities),
        _format_enhanced_context_block(user_query, enriched_query),
    ]
    return "\n\n".join(blocks)


def _format_ambiguous_terms_notice(ambiguities: list[dict[str, Any]]) -> str:
    if not ambiguities:
        return "待澄清术语：无"
    lines: list[str] = []
    for entry in ambiguities:
        mention = str(entry.get("mention") or entry.get("term") or "").strip() or "未命名术语"
        candidates_raw = entry.get("candidates") or []
        candidate_names: list[str] = []
        if isinstance(candidates_raw, list):
            for candidate in candidates_raw[:5]:
                if not isinstance(candidate, dict):
                    continue
                name = str(candidate.get("term_name") or candidate.get("name") or "").strip()
                if name:
                    candidate_names.append(name)
        candidate_text = "、".join(candidate_names) if candidate_names else "无候选"
        lines.append(f"待澄清术语：{mention}（候选：{candidate_text}）")
    return "\n".join(lines)


def _format_confirmed_terms_notice(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return "已确权的术语：无"
    lines = ["已确权的术语："]
    for item in summaries:
        term_name = str(item.get("term_name") or "").strip() or "未命名术语"
        summary = str(item.get("summary") or "").strip()
        if summary:
            lines.append(f"- {term_name}：{summary}")
        else:
            lines.append(f"- {term_name}")
    return "\n".join(lines)


def _format_enriched_query_notice(user_query: str, enriched_query: str) -> str:
    return f"原始问题：\n{user_query}\n\n改写后的问题：\n{enriched_query}"


async def _emit_thinking_logs(
    *,
    gateway_context: Any,
    recognized_terms: list[str],
    user_query: str,
    summaries: list[dict[str, Any]],
    ambiguities: list[dict[str, Any]],
    enriched_query: str,
) -> None:
    if gateway_context is None:
        return
    chunks = [
        _format_thinking_report(
            recognized_terms=recognized_terms,
            summaries=summaries,
            ambiguities=ambiguities,
            user_query=user_query,
            enriched_query=enriched_query,
        )
    ]
    for content in chunks:
        try:
            await gateway_context.emit_chunk(
                StreamChunkEvent(content=content),
                event_type=EventType.REASONING_LOG_DELTA.value,
                content_type=SseReasonMessageType.think_text.value,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("knowledge_enhance_node: failed to emit thinking chunk: %s", exc)


def _is_duplicate_of_summary(text: str, summaries: list[str]) -> bool:
    for summary in summaries:
        if not summary:
            continue
        if SequenceMatcher(None, text, summary).ratio() >= _SNIPPET_SIMILARITY_THRESHOLD:
            return True
    return False


def _entry_similarity_text(entry: dict[str, Any]) -> str:
    text_parts: list[str] = []
    for key in ("term_desc", "definition", "description", "term_name", "normalized_term", "mention"):
        value = str(entry.get(key, "")).strip()
        if value:
            text_parts.append(value)
    if not text_parts:
        return json.dumps(entry, ensure_ascii=False)
    return " ".join(text_parts)


def _trim_entry_for_snippet(source_key: str, entry: dict[str, Any]) -> dict[str, Any]:
    if source_key == "term_matches":
        out = {
            "term_id": str(entry.get("term_id", "")),
            "term_name": str(entry.get("term_name", "")),
            "normalized_term": str(entry.get("normalized_term", "")),
            "term_type_code": str(entry.get("term_type_code", "")),
            "match_score": float(entry.get("match_score", 0.0) or 0.0),
        }
        desc = str(entry.get("term_desc") or entry.get("definition") or entry.get("description") or "").strip()
        if desc:
            out["summary"] = _truncate_text(desc, limit=140)
        return out

    if source_key == "fuzzy_term_matches":
        candidates_out: list[dict[str, Any]] = []
        for candidate in entry.get("candidates", []) or []:
            if not isinstance(candidate, dict):
                continue
            candidates_out.append(
                {
                    "term_id": str(candidate.get("term_id", "")),
                    "term_name": str(candidate.get("term_name", "")),
                    "term_type_code": str(candidate.get("term_type_code", "")),
                    "similarity": float(candidate.get("similarity", 0.0) or 0.0),
                    "edit_distance": int(candidate.get("edit_distance", 0) or 0),
                }
            )
            if len(candidates_out) >= 5:
                break
        return {
            "mention": str(entry.get("mention", "")),
            "candidates": candidates_out,
        }

    return dict(entry)


def _build_knowledge_snippets(
    payload: dict[str, Any] | None,
    knowledge_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    summary_texts = [item["summary"] for item in knowledge_summaries]
    snippets: list[dict[str, Any]] = []
    for source_key in ("term_matches", "fuzzy_term_matches"):
        entries = payload.get(source_key)
        if not isinstance(entries, list) or not entries:
            continue
        normalized_entries = [
            _trim_entry_for_snippet(source_key, entry)
            for entry in entries
            if isinstance(entry, dict)
        ]
        if not normalized_entries:
            continue
        selected_entries: list[dict[str, Any]] = []
        for entry in normalized_entries:
            similarity_text = _entry_similarity_text(entry)
            if _is_duplicate_of_summary(similarity_text, summary_texts):
                continue
            serialized = json.dumps(entry, ensure_ascii=False)
            if len(serialized) > _SNIPPET_ITEM_MAX_CHARS:
                continue
            selected_entries.append(entry)
        if not selected_entries:
            continue
        snippets.append(
            {
                "source": source_key,
                "data": selected_entries,
                "char_len": sum(len(json.dumps(item, ensure_ascii=False)) for item in selected_entries),
            }
        )
    return snippets


async def knowledge_enhance_node(
    state: AgentState,
    gateway_context: Any = None,
) -> dict[str, Any]:
    """Build structured enhancement artifacts for downstream planning."""
    user_query = _last_user_text(list(state.get("messages", [])))
    if not user_query.strip():
        return {
            "user_query": "",
            "enriched_query": "",
            "enriched_query_source": "empty_query",
            "enriched_query_confidence": 0.0,
            "confirmed_terms": [],
            "term_hints": [],
            "knowledge_snippets": [],
            "knowledge_payload": {},
            "ambiguous_terms": [],
        }

    payload: dict[str, Any] = {}
    try:
        payload_raw = await search_knowledge.ainvoke({"query": user_query})
        payload = payload_raw if isinstance(payload_raw, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge_enhance_node: search_knowledge failed, fallback to user query: %s", exc)

    confidence_threshold = _term_hint_confidence_threshold(state)
    term_hints = _extract_term_hints(payload, confidence_threshold=confidence_threshold)
    recognized_terms = _extract_recognized_terms(payload)
    confirmed_terms = _build_confirmed_terms(payload, term_hints)
    knowledge_summaries = _build_confirmed_knowledge_summaries(payload, term_hints)
    enriched_query, enriched_query_source, enriched_query_confidence = _compose_enriched_query(
        user_query,
        knowledge_summaries,
    )
    ambiguities = _extract_ambiguities(payload)
    knowledge_snippets = _build_knowledge_snippets(payload, knowledge_summaries)
    thinking_log = _build_thinking_log(
        user_query=user_query,
        recognized_terms=recognized_terms,
        summaries=knowledge_summaries,
        ambiguities=ambiguities,
        enriched_query=enriched_query,
        enriched_source=enriched_query_source,
    )
    _log_thinking(
        user_query=user_query,
        summaries=knowledge_summaries,
        ambiguities=ambiguities,
        enriched_query=enriched_query,
        enriched_source=enriched_query_source,
    )
    await _emit_thinking_logs(
        gateway_context=gateway_context,
        recognized_terms=recognized_terms,
        user_query=user_query,
        summaries=knowledge_summaries,
        ambiguities=ambiguities,
        enriched_query=enriched_query,
    )

    return {
        "user_query": user_query,
        "enriched_query": enriched_query,
        "enriched_query_source": enriched_query_source,
        "enriched_query_confidence": enriched_query_confidence,
        "confirmed_terms": confirmed_terms,
        "term_hints": term_hints,
        "knowledge_snippets": knowledge_snippets,
        "knowledge_payload": payload,
        "ambiguous_terms": ambiguities,
        "thinking_log": thinking_log,
    }
