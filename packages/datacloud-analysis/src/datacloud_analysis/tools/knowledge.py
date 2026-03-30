"""T_KNOW_SEARCH — enterprise knowledge & terminology search (design §3.1).

Calls the ``datacloud-knowledge-service`` to retrieve relevant domain
knowledge (ontology, term definitions, business rules) before the Agent
starts planning.

Also provides composite term-retrieval and disambiguation helpers used by
intent_node and clarification_node (design §4.1.3 / §4.1.4).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from sqlalchemy import bindparam, text

logger = logging.getLogger(__name__)

CandidateDict = dict[str, Any]


@tool
async def search_knowledge(query: str, n_hops: int = 4) -> str:
    """Search the enterprise knowledge graph and return semantic tree text."""
    try:
        from datacloud_knowledge import nl_to_semantic_tree

        result = await asyncio.to_thread(nl_to_semantic_tree, query, n_hops=n_hops)
    except Exception as e:
        logger.error("nl_to_semantic_tree failed: %s", e)
        return f"(查询失败: {e})"
    return str(result)


def _build_global_name_index(session: Any) -> dict[str, list[tuple[str, str, str]]]:
    """Build global name index from public ``term_name`` rows.

    The shape matches ``match_mentions_with_search`` expectation:
    ``{name_text: [(term_id, term_type_code, match_type), ...]}``.
    """
    sql = text(
        """
        SELECT
            t.term_id,
            t.term_type_code,
            tn.name_text,
            CASE WHEN tn.name_text = t.term_name THEN 'standard_name' ELSE 'alias' END AS match_type
        FROM whale_datacloud.term_name tn
        JOIN whale_datacloud.term t ON tn.term_id = t.term_id
        WHERE tn.search_scope = '{}'::jsonb
           OR tn.search_scope->>'scope_user_id' IS NULL
        """
    )
    rows = session.execute(sql).fetchall()
    index: dict[str, list[tuple[str, str, str]]] = {}
    for term_id, term_type_code, name_text, match_type in rows:
        index.setdefault(str(name_text), []).append(
            (str(term_id), str(term_type_code), str(match_type))
        )
    return index


def _query_name_ids_by_word(
    session: Any,
    *,
    word: str,
    term_ids: list[str],
    user_id: str | None,
) -> dict[str, str]:
    """Resolve ``term_id -> name_id`` for a mention word.

    Preference:
    1) user-scoped alias (scope_user_id=user_id)
    2) global alias/standard name
    """
    if not term_ids:
        return {}

    if user_id:
        sql = text(
            """
            SELECT
                tn.term_id,
                tn.name_id
            FROM whale_datacloud.term_name tn
            WHERE tn.name_text = :name_text
              AND tn.term_id IN :term_ids
              AND (
                    tn.search_scope = '{}'::jsonb
                 OR tn.search_scope->>'scope_user_id' IS NULL
                 OR tn.search_scope->>'scope_user_id' = :user_id
              )
            ORDER BY
              CASE WHEN tn.search_scope->>'scope_user_id' = :user_id THEN 0 ELSE 1 END,
              tn.updated_time DESC
            """
        ).bindparams(bindparam("term_ids", expanding=True))
        rows = session.execute(
            sql, {"name_text": word, "term_ids": term_ids, "user_id": user_id}
        ).fetchall()
    else:
        sql = text(
            """
            SELECT
                tn.term_id,
                tn.name_id
            FROM whale_datacloud.term_name tn
            WHERE tn.name_text = :name_text
              AND tn.term_id IN :term_ids
              AND (
                    tn.search_scope = '{}'::jsonb
                 OR tn.search_scope->>'scope_user_id' IS NULL
              )
            ORDER BY tn.updated_time DESC
            """
        ).bindparams(bindparam("term_ids", expanding=True))
        rows = session.execute(sql, {"name_text": word, "term_ids": term_ids}).fetchall()

    mapping: dict[str, str] = {}
    for term_id, name_id in rows:
        term_id_text = str(term_id)
        if term_id_text not in mapping:
            mapping[term_id_text] = str(name_id)
    return mapping


def _candidate_to_dict(candidate: Any, *, name_id: str | None) -> CandidateDict:
    return {
        "term_id": candidate.term_id,
        "term_name": candidate.term_name,
        "term_type_code": candidate.term_type_code,
        "match_type": candidate.match_type,
        "confidence": candidate.confidence,
        "score": candidate.score,
        "name_id": name_id,
    }


def _convert_hits(
    session: Any,
    *,
    word: str,
    hits: tuple[Any, ...],
    user_id: str | None,
) -> list[CandidateDict]:
    term_ids = [str(c.term_id) for c in hits]
    name_id_map = _query_name_ids_by_word(session, word=word, term_ids=term_ids, user_id=user_id)
    return [_candidate_to_dict(c, name_id=name_id_map.get(str(c.term_id))) for c in hits]


async def search_all_candidates(
    concept_terms: list[str],
    *,
    user_id: str | None = None,
    top_k: int = 5,
) -> dict[str, list[CandidateDict]]:
    """四步漏斗检索所有 concept_terms，返回 {word: [candidate_dict, ...]}。"""
    from datacloud_knowledge.intent import UserNameCache, match_mentions_with_search
    from datacloud_knowledge.intent.types import Mention
    from datacloud_knowledge.knowledge_search.db.connection import get_session
    from datacloud_knowledge.query.embedding import get_embedding_service

    if not concept_terms:
        return {}

    def _run_search() -> dict[str, list[CandidateDict]]:
        user_cache = UserNameCache()
        result: dict[str, list[CandidateDict]] = {}
        with get_session() as session:
            global_name_index = _build_global_name_index(session)
            mentions = tuple(Mention(text=w) for w in concept_terms)

            strict_hits = match_mentions_with_search(
                mentions,
                session,
                user_id=user_id,
                global_name_index=global_name_index,
                user_cache=user_cache,
                search_mode="strict",
                top_k=top_k,
            )

            remaining: list[str] = []
            for word in concept_terms:
                hits = strict_hits.get(word)
                if hits:
                    result[word] = _convert_hits(session, word=word, hits=hits, user_id=user_id)
                else:
                    remaining.append(word)

            if not remaining:
                return result

            bm25_mentions = tuple(Mention(text=w) for w in remaining)
            bm25_hits = match_mentions_with_search(
                bm25_mentions,
                session,
                search_mode="bm25",
                top_k=top_k,
            )

            still_remaining: list[str] = []
            for word in remaining:
                hits = bm25_hits.get(word)
                if hits:
                    result[word] = _convert_hits(session, word=word, hits=hits, user_id=user_id)
                else:
                    still_remaining.append(word)

            if not still_remaining:
                return result

            try:
                embedding_svc = get_embedding_service()
                vector_mentions = tuple(Mention(text=w) for w in still_remaining)
                vector_hits = match_mentions_with_search(
                    vector_mentions,
                    session,
                    search_mode="vector",
                    embedding_service=embedding_svc,
                    top_k=top_k,
                )
                for word in still_remaining:
                    hits = vector_hits.get(word)
                    result[word] = (
                        _convert_hits(session, word=word, hits=hits, user_id=user_id)
                        if hits
                        else []
                    )
            except Exception as exc:
                logger.warning("search_all_candidates: vector step failed: %s", exc)
                for word in still_remaining:
                    result[word] = []

        return result

    return await asyncio.to_thread(_run_search)


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
    from datacloud_knowledge.intent import MatchCandidate, MatchResult, disambiguate
    from datacloud_knowledge.knowledge_search.db.connection import get_session

    if not candidates_map:
        return [], []

    def _build_match_result() -> MatchResult:
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
        return MatchResult(exact=exact, fuzzy=fuzzy)

    def _run_disambiguate() -> tuple[
        dict[str, Any],
        dict[str, tuple[Any, ...]],
    ]:
        match_result = _build_match_result()
        with get_session() as session:
            dis_result = disambiguate(match_result, session)
            return dis_result.confirmed, dis_result.ambiguous

    confirmed_raw, ambiguous_raw = await asyncio.to_thread(_run_disambiguate)

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
    """层3：LLM 语境推理消歧，返回 (llm_confirmed, still_ambiguous)。"""
    candidates_text = ""
    for mention, candidates in ambiguous_raw.items():
        if not candidates:
            continue
        options = "\n".join(
            f"  {i + 1}. term_id={c.term_id} term_name={c.term_name} "
            f"type={c.term_type_code} confidence={c.confidence:.2f}"
            for i, c in enumerate(candidates[:3])
        )
        candidates_text += f"\n词：「{mention}」\n候选：\n{options}\n"

    if not candidates_text:
        return [], dict(ambiguous_raw)

    prompt = f"""你是术语消歧专家。根据用户问题的语境，从候选术语中选出最合适的一个。

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
    except Exception as exc:
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
        if mention in still_ambiguous_words:
            still_ambiguous[mention] = candidates
        else:
            # 未被 LLM 明确处理的词也保留为歧义。
            still_ambiguous[mention] = candidates

    return llm_confirmed, still_ambiguous


async def save_clarification_results(
    clarification_results: dict[str, Any],
    user_id: str,
) -> list[str]:
    """写入澄清结果，返回 name_id 列表。"""
    from datacloud_knowledge.intent.storage import (
        create_term_with_knowledge,
        create_user_term_name,
    )
    from datacloud_knowledge.knowledge_search.db.connection import get_session

    def _run_store() -> list[str]:
        created_ids: list[str] = []
        with get_session() as session:
            for mention_text, result in clarification_results.items():
                if isinstance(result, dict) and "term_id" in result:
                    name_id = create_user_term_name(
                        name_text=mention_text,
                        term_id=str(result["term_id"]),
                        user_id=user_id,
                        session=session,
                    )
                    created_ids.append(name_id)
                    logger.info(
                        "save_clarification_results: alias '%s' → %s",
                        mention_text,
                        result["term_id"],
                    )
                elif isinstance(result, str) and result.strip():
                    term_id, _, name_id = create_term_with_knowledge(
                        term_code=f"user_defined_{mention_text}",
                        term_name=mention_text,
                        term_type_code="USER_DEFINED",
                        domain_id="DOMAIN_002",
                        knowledge_text=result,
                        user_id=user_id,
                        session=session,
                    )
                    created_ids.append(name_id)
                    logger.info(
                        "save_clarification_results: new term '%s' term_id=%s",
                        mention_text,
                        term_id,
                    )
        return created_ids

    return await asyncio.to_thread(_run_store)


async def update_term_scores(
    score_records: list[dict[str, Any]],
) -> None:
    """异步 fire-and-forget 更新别名 score。"""
    from datacloud_knowledge.intent import ScoreUpdateRecord, batch_update_scores
    from datacloud_knowledge.knowledge_search.db.connection import get_session

    if not score_records:
        return

    records = tuple(
        ScoreUpdateRecord(name_id=str(r["name_id"]), success=bool(r["success"]))
        for r in score_records
        if r.get("name_id")
    )
    if not records:
        return

    def _run_update() -> None:
        with get_session() as session:
            batch_update_scores(records, session)

    asyncio.create_task(asyncio.to_thread(_run_update))
