"""Candidate search — multi-strategy recall pipeline (strict → bm25 → vector)."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.adapters.opengauss.vector_validation import (
    TermVectorValidationError,
    validate_term_vector_readiness,
)
from datacloud_knowledge.contracts.types import Mention
from datacloud_knowledge.retrieval.embedding import get_embedding_service
from datacloud_knowledge.retrieval.mention_matching import match_mentions_with_search
from datacloud_knowledge.retrieval.name_cache import UserNameCache

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

CandidateDict = dict[str, Any]

_VECTOR_ENABLE_ENV = "DATACLOUD_INTENT_ENABLE_VECTOR"
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _vector_search_enabled() -> bool:
    """Return whether intent vector recall is enabled; defaults to enabled."""
    raw = os.getenv(_VECTOR_ENABLE_ENV, "1").strip().lower()
    return raw not in _FALSE_VALUES


def _build_global_name_index() -> dict[str, list[tuple[str, str, str]]]:
    """Build global name index from public term_name rows, via reader adapter."""
    return create_reader().get_global_name_index()


def _query_name_ids_by_word(
    *,
    word: str,
    term_ids: list[str],
    user_id: str | None,
) -> dict[str, str]:
    """Resolve term_id -> name_id for a mention word, via reader adapter."""
    return create_reader().get_name_ids_by_word(word=word, term_ids=term_ids, user_id=user_id)


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
        embedding_svc = get_embedding_service()
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

    mentions = tuple(Mention(text=w) for w in concept_terms)
    strict_hits = match_mentions_with_search(
        mentions,
        None,
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
        None,
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

    embedding_svc = _get_validated_embedding_service(None)
    if embedding_svc is None:
        for word in still_remaining:
            result[word] = []
        return result

    vector_mentions = tuple(Mention(text=w) for w in still_remaining)
    vector_hits = match_mentions_with_search(
        vector_mentions,
        None,
        search_mode="vector",
        embedding_service=embedding_svc,
        top_k=top_k,
    )
    for word in still_remaining:
        hits = vector_hits.get(word)
        result[word] = _convert_hits(word=word, hits=hits, user_id=user_id) if hits else []

    return result
