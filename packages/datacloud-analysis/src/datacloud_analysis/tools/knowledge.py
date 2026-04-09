"""意图编排的知识工具模块。

本模块仅编排对 ``datacloud-knowledge`` 门面 API 的调用。
不应在此处包含 SQL/session 操作。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

CandidateDict = dict[str, Any]


def _normalize_tree(node: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    children_raw = node.get("children", [])
    children = []
    if isinstance(children_raw, list):
        for item in children_raw:
            normalized_child = _normalize_tree(item if isinstance(item, dict) else None)
            if normalized_child is not None:
                children.append(normalized_child)
    return {
        "term_id": str(node.get("id", "")),
        "term_name": str(node.get("name", "")),
        "term_type_code": str(node.get("node_type", "")),
        "relation_name": str(node.get("relation", "")) if node.get("relation") else "",
        "knowledge": node.get("properties", {}).get("knowledge", []),
        "children": children,
    }


def _normalize_search_payload(raw: dict[str, Any], *, query: str) -> dict[str, Any]:
    term_matches: list[dict[str, Any]] = []
    for item in raw.get("entities_found", []):
        if not isinstance(item, dict):
            continue
        term_matches.append(
            {
                "term_id": str(item.get("node_id", "")),
                "term_name": str(item.get("name", "")),
                "term_type_code": str(item.get("node_type", "")),
                "match_type": str(item.get("match_type", "")),
                "match_score": float(item.get("match_score", 0.0) or 0.0),
            }
        )

    fuzzy_term_matches: list[dict[str, Any]] = []
    for fuzzy_item in raw.get("fuzzy_suggestions", []):
        if not isinstance(fuzzy_item, dict):
            continue
        mention = str(fuzzy_item.get("original", ""))
        candidates: list[dict[str, Any]] = []
        for match in fuzzy_item.get("matches", []):
            if not isinstance(match, dict):
                continue
            candidates.append(
                {
                    "term_id": str(match.get("term_id", "")),
                    "term_name": str(match.get("term", "")),
                    "term_type_code": str(match.get("term_type", "")),
                    "similarity": float(match.get("similarity", 0.0) or 0.0),
                    "edit_distance": int(match.get("edit_distance", 0) or 0),
                }
            )
        fuzzy_term_matches.append({"mention": mention, "candidates": candidates})

    term_subgraphs: list[dict[str, Any]] = []
    for item in raw.get("results", []):
        if not isinstance(item, dict):
            continue
        center = item.get("center_entity", {})
        center_term = (
            {
                "term_id": str(center.get("node_id", "")),
                "term_name": str(center.get("name", "")),
                "term_type_code": str(center.get("node_type", "")),
                "match_type": str(center.get("match_type", "")),
            }
            if isinstance(center, dict)
            else {"term_id": "", "term_name": "", "term_type_code": "", "match_type": ""}
        )
        term_subgraphs.append(
            {
                "center_term": center_term,
                "hops": int(item.get("hops", 0) or 0),
                "node_count": int(item.get("node_count", 0) or 0),
                "edge_count": int(item.get("edge_count", 0) or 0),
                "tree": _normalize_tree(
                    item.get("tree") if isinstance(item.get("tree"), dict) else None
                ),
            }
        )

    return {
        "query": str(raw.get("query") or query),
        "term_matches": term_matches,
        "fuzzy_term_matches": fuzzy_term_matches,
        "term_subgraphs": term_subgraphs,
        "message": str(raw.get("message", "")),
    }


@tool
async def search_knowledge(query: str, n_hops: int = 4) -> dict[str, Any]:
    """搜索知识图谱，返回结构化载荷供 prompt 上下文使用。"""
    from datacloud_knowledge.query import get_singleton_service

    def _run_query() -> dict[str, Any]:
        service = get_singleton_service(n_hops=n_hops, fast=True, warm_pool=False)
        raw = service.query(query, n_hops=n_hops, include_knowledge=True)
        if not isinstance(raw, dict):
            return {
                "query": query,
                "term_matches": [],
                "fuzzy_term_matches": [],
                "term_subgraphs": [],
                "message": "",
                "error": "invalid_search_payload",
            }
        return _normalize_search_payload(raw, query=query)

    try:
        return await asyncio.to_thread(_run_query)
    except Exception as exc:  # noqa: BLE001
        logger.error("search_knowledge failed: %s", exc)
        return {
            "query": query,
            "term_matches": [],
            "fuzzy_term_matches": [],
            "term_subgraphs": [],
            "message": "",
            "error": str(exc),
        }


async def search_all_candidates(
    concept_terms: list[str],
    *,
    user_id: str | None = None,
    top_k: int = 5,
) -> dict[str, list[CandidateDict]]:
    """对所有概念术语执行 strict→bm25→vector 漏斗搜索。"""
    from datacloud_knowledge.intent import search_all_candidates_with_name_id

    if not concept_terms:
        return {}
    return await asyncio.to_thread(
        search_all_candidates_with_name_id,
        concept_terms,
        user_id=user_id,
        top_k=top_k,
    )


def _name_id_from_candidates(
    candidates_map: dict[str, list[CandidateDict]],
    *,
    mention: str,
    term_id: str,
) -> str | None:
    for candidate in candidates_map.get(mention, []):
        if str(candidate.get("term_id")) == term_id:
            name_id = candidate.get("name_id")
            return str(name_id) if name_id else None
    return None


async def disambiguate_candidates(
    candidates_map: dict[str, list[CandidateDict]],
    original_question: str,
    *,
    llm: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """三层消歧，返回 (confirmed_terms, ambiguous_terms)。"""
    from datacloud_knowledge.intent import (
        MatchCandidate,
        MatchResult,
        disambiguate_with_session,
    )

    if not candidates_map:
        return [], []

    exact: dict[str, tuple[MatchCandidate, ...]] = {}
    fuzzy: dict[str, tuple[MatchCandidate, ...]] = {}
    for word, candidates in candidates_map.items():
        converted = tuple(
            MatchCandidate(
                term_id=str(c["term_id"]),
                term_name=str(c["term_name"]),
                term_type_code=str(c["term_type_code"]),
                match_type=str(c["match_type"]),
                confidence=float(c["confidence"]),
                score=float(c["score"]),
            )
            for c in candidates
        )
        if converted and converted[0].match_type in ("exact", "alias"):
            exact[word] = converted
        else:
            fuzzy[word] = converted

    dis_result = await asyncio.to_thread(
        disambiguate_with_session, MatchResult(exact=exact, fuzzy=fuzzy)
    )
    confirmed_raw = dis_result.confirmed
    ambiguous_raw = dis_result.ambiguous

    confirmed_terms: list[dict[str, Any]] = []
    for mention, candidate in confirmed_raw.items():
        term_id = str(candidate.term_id)
        confirmed_terms.append(
            {
                "mention": mention,
                "term_id": term_id,
                "term_name": candidate.term_name,
                "term_type_code": candidate.term_type_code,
                "confidence": candidate.confidence,
                "name_id": _name_id_from_candidates(
                    candidates_map, mention=mention, term_id=term_id
                ),
            }
        )

    still_ambiguous: dict[str, tuple[Any, ...]] = {}
    if ambiguous_raw and llm is not None:
        llm_confirmed, still_ambiguous = await _llm_disambiguate(
            ambiguous_raw,
            original_question,
            llm,
            candidates_map=candidates_map,
        )
        confirmed_terms.extend(llm_confirmed)

    ambiguous_terms = [
        {
            "mention": mention,
            "candidates": [
                {
                    "term_id": c.term_id,
                    "term_name": c.term_name,
                    "term_type_code": c.term_type_code,
                    "match_type": c.match_type,
                    "confidence": c.confidence,
                    "score": c.score,
                    "name_id": _name_id_from_candidates(
                        candidates_map, mention=mention, term_id=str(c.term_id)
                    ),
                }
                for c in candidates
            ],
        }
        for mention, candidates in still_ambiguous.items()
    ]
    return confirmed_terms, ambiguous_terms


async def _llm_disambiguate(
    ambiguous_raw: dict[str, tuple[Any, ...]],
    original_question: str,
    llm: Any,
    *,
    candidates_map: dict[str, list[CandidateDict]],
) -> tuple[list[dict[str, Any]], dict[str, tuple[Any, ...]]]:
    """使用 LLM 上下文推理解决剩余歧义。"""
    candidates_text = ""
    for mention, candidates in ambiguous_raw.items():
        if not candidates:
            continue
        options = "\n".join(
            f"  {i + 1}. term_id={c.term_id} term_name={c.term_name} "
            f"type={c.term_type_code} confidence={c.confidence:.2f}"
            for i, c in enumerate(candidates[:3])
        )
        candidates_text += f"\n词：{mention}\n候选：\n{options}\n"

    if not candidates_text:
        return [], dict(ambiguous_raw)

    prompt = f"""你是术语消歧专家。根据用户问题上下文，从候选术语中选择最合适的一项。
用户问题：{original_question}

需要消歧的词及候选：{candidates_text}

请输出 JSON，格式如下（严格 JSON，无多余字段）：
{{
  "confirmed": [
    {{"mention": "词", "term_id": "选中的term_id", "term_name": "选中的term_name"}}
  ],
  "ambiguous": ["仍无法判断的词列表"]
}}"""

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content="你是术语消歧专家，只输出 JSON。"),
                HumanMessage(content=prompt),
            ]
        )
        content = str(response.content)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM disambiguate failed: %s", exc)
        return [], dict(ambiguous_raw)

    llm_confirmed: list[dict[str, Any]] = []
    for item in parsed.get("confirmed", []):
        mention = str(item.get("mention", ""))
        if mention not in ambiguous_raw:
            continue
        term_id = str(item.get("term_id", ""))
        matched = next((c for c in ambiguous_raw[mention] if c.term_id == term_id), None)
        llm_confirmed.append(
            {
                "mention": mention,
                "term_id": term_id,
                "term_name": str(item.get("term_name", "")),
                "term_type_code": matched.term_type_code if matched else "",
                "confidence": float(matched.confidence) if matched else 0.0,
                "name_id": _name_id_from_candidates(
                    candidates_map, mention=mention, term_id=term_id
                ),
            }
        )

    still_ambiguous_words = {str(v) for v in parsed.get("ambiguous", [])}
    confirmed_mentions = {item["mention"] for item in llm_confirmed}
    still_ambiguous: dict[str, tuple[Any, ...]] = {}
    for mention, candidates in ambiguous_raw.items():
        if mention in confirmed_mentions:
            continue
        still_ambiguous[mention] = candidates

    return llm_confirmed, still_ambiguous


async def save_clarification_results(
    clarification_results: dict[str, Any],
    user_id: str,
) -> list[str]:
    """持久化澄清结果，返回创建的 name_id 列表。"""
    from datacloud_knowledge.intent import store_clarification_results

    return await asyncio.to_thread(store_clarification_results, clarification_results, user_id)


async def update_term_scores(
    score_records: list[dict[str, Any]],
    *,
    gateway_context: Any | None = None,
) -> None:
    """异步更新术语名称评分（fire-and-forget）。"""
    if not score_records:
        return

    normalized = [
        {"name_id": str(r.get("name_id", "")).strip(), "success": bool(r.get("success"))}
        for r in score_records
        if str(r.get("name_id", "")).strip()
    ]
    if not normalized:
        return

    if gateway_context is not None:
        target_agent_type = os.getenv("DATACLOUD_GATEWAY_WORKER_ID", "datacloud")
        try:
            await gateway_context.call_agent(
                target_agent_type=target_agent_type,
                content="update term-name scores",
                payload={
                    "ext_params": {
                        "command": "updateTermsName",
                        "score_records": normalized,
                        "silent": True,
                    }
                },
                wait_for_reply=False,
                metadata={"event": "term_score_update"},
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "update_term_scores: async call_agent failed, fallback to local update: %s", exc
            )

    from datacloud_knowledge.intent import ScoreUpdateRecord, batch_update_scores_with_session

    records = tuple(
        ScoreUpdateRecord(name_id=item["name_id"], success=item["success"]) for item in normalized
    )
    await asyncio.to_thread(batch_update_scores_with_session, records)
