"""Intent service facade with managed DB/session boundaries."""

from __future__ import annotations

import logging
import os
from importlib import import_module
from typing import TYPE_CHECKING, Any

from sqlalchemy import bindparam, text

from datacloud_knowledge.adapters import create_writer
from datacloud_knowledge.adapters.opengauss._db.connection import get_session
from datacloud_knowledge.adapters.opengauss.vector_validation import (
    TermVectorValidationError,
    validate_term_vector_readiness,
)

from .cache import UserNameCache
from .disambiguation import build_shortest_path_tree, disambiguate
from .matching import match_mentions_with_search
from .score_update import batch_update_scores
from .types import (
    DisambiguationResult,
    MatchResult,
    Mention,
    ScoreUpdateRecord,
    ShortestPathTreeResult,
)

logger = logging.getLogger(__name__)

CandidateDict = dict[str, Any]
if TYPE_CHECKING:
    from .batch_recall import ScopeRecallLayer

_VECTOR_ENABLE_ENV = "DATACLOUD_INTENT_ENABLE_VECTOR"
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _vector_search_enabled() -> bool:
    """Return whether intent vector recall is enabled; defaults to enabled."""
    raw = os.getenv(_VECTOR_ENABLE_ENV, "1").strip().lower()
    return raw not in _FALSE_VALUES


def _build_global_name_index() -> dict[str, list[tuple[str, str, str]]]:
    """Build global name index from public term_name rows."""
    sql = text(
        """
        SELECT
            t.term_id,
            t.term_type_code,
            tn.name_text,
            CASE WHEN tn.name_text = t.term_name THEN 'standard_name' ELSE 'alias' END AS match_type
        FROM term_name tn
        JOIN term t ON tn.term_id = t.term_id
        WHERE tn.search_scope = '{}'::jsonb
           OR COALESCE((tn.search_scope->>'scope_user_id'), '') = ''
        """
    )
    with get_session() as session:
        rows = session.execute(sql).fetchall()
    index: dict[str, list[tuple[str, str, str]]] = {}
    for term_id, term_type_code, name_text, match_type in rows:
        index.setdefault(str(name_text), []).append(
            (str(term_id), str(term_type_code), str(match_type))
        )
    return index


def _query_name_ids_by_word(
    *,
    word: str,
    term_ids: list[str],
    user_id: str | None,
) -> dict[str, str]:
    """Resolve term_id -> name_id for a mention word."""
    if not term_ids:
        return {}

    if user_id:
        sql = text(
            """
            SELECT
                tn.term_id,
                tn.name_id
            FROM term_name tn
            WHERE tn.name_text = :name_text
              AND tn.term_id IN :term_ids
              AND (
                    tn.search_scope = '{}'::jsonb
                 OR COALESCE((tn.search_scope->>'scope_user_id'), '') = ''
                 OR COALESCE((tn.search_scope->>'scope_user_id'), '') = :user_id
              )
            ORDER BY
              CASE WHEN COALESCE((tn.search_scope->>'scope_user_id'), '') = :user_id
                   THEN 0 ELSE 1 END,
              tn.updated_time DESC
            """
        ).bindparams(bindparam("term_ids", expanding=True))
        params = {"name_text": word, "term_ids": term_ids, "user_id": user_id}
    else:
        sql = text(
            """
            SELECT
                tn.term_id,
                tn.name_id
            FROM term_name tn
            WHERE tn.name_text = :name_text
              AND tn.term_id IN :term_ids
              AND (
                    tn.search_scope = '{}'::jsonb
                 OR COALESCE((tn.search_scope->>'scope_user_id'), '') = ''
              )
            ORDER BY tn.updated_time DESC
            """
        ).bindparams(bindparam("term_ids", expanding=True))
        params = {"name_text": word, "term_ids": term_ids}

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()

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
    *,
    word: str,
    hits: tuple[Any, ...],
    user_id: str | None,
) -> list[CandidateDict]:
    term_ids = [str(c.term_id) for c in hits]
    name_id_map = _query_name_ids_by_word(word=word, term_ids=term_ids, user_id=user_id)
    return [_candidate_to_dict(c, name_id=name_id_map.get(str(c.term_id))) for c in hits]


def _get_validated_embedding_service(session: Any) -> Any:
    if not _vector_search_enabled():
        logger.error("知识库向量召回被环境变量 %s 关闭，服务将降级运行", _VECTOR_ENABLE_ENV)
        return None

    try:
        embedding_module = import_module("datacloud_knowledge.embedding")
        embedding_svc = embedding_module.get_embedding_service()
        validate_term_vector_readiness(session, embedding_svc)
    except TermVectorValidationError as exc:
        logger.error("知识库向量校验失败，向量召回将跳过: %s", exc)
        return None
    except Exception as exc:
        logger.error("知识库向量服务初始化失败，向量召回将跳过: %s", exc)
        return None
    return embedding_svc


def search_all_candidates_with_name_id(
    concept_terms: list[str],
    *,
    user_id: str | None = None,
    top_k: int = 5,
) -> dict[str, list[CandidateDict]]:
    """Run strict -> bm25 -> vector and return name_id-enriched candidates."""
    if not concept_terms:
        return {}

    user_cache = UserNameCache()
    global_name_index = _build_global_name_index()
    result: dict[str, list[CandidateDict]] = {}

    with get_session() as session:
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
                result[word] = _convert_hits(word=word, hits=hits, user_id=user_id)
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
                result[word] = _convert_hits(word=word, hits=hits, user_id=user_id)
            else:
                still_remaining.append(word)

        if not still_remaining:
            return result

        embedding_svc = _get_validated_embedding_service(session)
        if embedding_svc is None:
            for word in still_remaining:
                result[word] = []
            return result

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
            result[word] = _convert_hits(word=word, hits=hits, user_id=user_id) if hits else []

    return result


def disambiguate_with_session(match_result: MatchResult) -> DisambiguationResult:
    """Execute disambiguation with a managed DB session."""
    with get_session() as session:
        return disambiguate(match_result, session)


def build_shortest_path_tree_with_session(
    *,
    target_term_id: str,
    source_term_type_codes: list[str] | tuple[str, ...],
    max_depth: int = 6,
) -> ShortestPathTreeResult:
    """Build shortest-path tree with a managed DB session."""
    with get_session() as session:
        return build_shortest_path_tree(
            target_term_id=target_term_id,
            source_term_type_codes=source_term_type_codes,
            session=session,
            max_depth=max_depth,
        )


def store_clarification_results(
    clarification_results: dict[str, Any],
    user_id: str,
) -> list[str]:
    """Persist clarification results and return created name_id list."""
    created_ids: list[str] = []
    with get_session() as session:
        writer = create_writer(session=session)
        for mention_text, result in clarification_results.items():
            if isinstance(result, dict) and "term_id" in result:
                name_id = writer.create_term_name(
                    term_id=str(result["term_id"]),
                    name_text=mention_text,
                    user_id=user_id,
                    search_scope={},
                )
                created_ids.append(name_id)
            elif isinstance(result, str) and result.strip():
                # 通过 create_term_with_knowledge 创建术语及其关联知识和别名，
                # 再单独获取 name_id
                _term_id = writer.create_term_with_knowledge(
                    term_name=mention_text,
                    term_type_code="USER_DEFINED",
                    domain_id="DOMAIN_002",
                    knowledge_desc=result,
                    user_id=user_id,
                )
                # 用户别名已在 create_term_with_knowledge 内部创建，
                # 这里通过 create_term_name 的幂等语义获取已有的 name_id
                name_id = writer.create_term_name(
                    term_id=_term_id,
                    name_text=mention_text,
                    user_id=user_id,
                    search_scope={},
                )
                created_ids.append(name_id)
    return created_ids


def batch_update_scores_with_session(records: tuple[ScoreUpdateRecord, ...]) -> None:
    """Update term-name score tags under a managed DB session."""
    if not records:
        return
    with get_session() as session:
        batch_update_scores(records, session)


def typed_multi_recall_with_session(
    items: list[Any],
    *,
    user_id: str | None = None,
    top_k: int = 5,
    scope_code: str | None = None,
    scope_layers: list[ScopeRecallLayer] | None = None,
) -> dict[str, list[CandidateDict]]:
    """Run typed multi-path recall with a managed DB session.

    Accepts TypedKeywordState items from paradigm_builder and returns
    dict[keyword, list[CandidateDict]] compatible with the existing
    paradigm resolution interface.
    """
    from .recall import typed_multi_recall_batch as _typed_multi_recall_batch

    with get_session() as session:
        embedding_svc = _get_validated_embedding_service(session)
        if embedding_svc is None:
            return _typed_multi_recall_batch(
                items,
                session=session,
                top_k=top_k,
                rrf_k=60,
                enable_vector=False,
                wv_per_type=top_k,
                scope_code=scope_code,
                scope_layers=scope_layers,
            )

        return _typed_multi_recall_batch(
            items,
            session=session,
            top_k=top_k,
            rrf_k=60,
            enable_vector=True,
            wv_per_type=top_k,
            scope_code=scope_code,
            scope_layers=scope_layers,
        )
