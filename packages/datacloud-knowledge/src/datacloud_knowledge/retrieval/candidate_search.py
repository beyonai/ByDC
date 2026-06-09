"""Candidate search — multi-strategy recall pipeline (strict → bm25 → vector)."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.contracts.types import Mention
from datacloud_knowledge.retrieval.mention_matching import match_mentions_with_search
from datacloud_knowledge.retrieval.name_cache import UserNameCache

logger = logging.getLogger(__name__)

CandidateDict = dict[str, Any]


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


def search_all_candidates_with_name_id(
    concept_terms: list[str],
    *,
    user_id: str | None = None,
    top_k: int = 5,
    embedding_service: Any | None = None,
) -> dict[str, list[CandidateDict]]:
    """Run strict -> bm25 -> vector and return name_id-enriched candidates.

    Callers that wish to use vector recall must pass a pre-validated
    ``embedding_service`` (obtained via
    ``adapters.opengauss.vector_validation.get_validated_embedding_service``).
    When ``embedding_service`` is *None* (the default), vector recall is
    silently skipped and unmatched terms receive empty candidate lists.
    """
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

    # Vector recall: caller must supply a validated embedding service.
    if embedding_service is None:
        for word in still_remaining:
            result[word] = []
        return result

    vector_mentions = tuple(Mention(text=w) for w in still_remaining)
    vector_hits = match_mentions_with_search(
        vector_mentions,
        None,
        search_mode="vector",
        embedding_service=embedding_service,
        top_k=top_k,
    )
    for word in still_remaining:
        hits = vector_hits.get(word)
        result[word] = _convert_hits(word=word, hits=hits, user_id=user_id) if hits else []

    return result
