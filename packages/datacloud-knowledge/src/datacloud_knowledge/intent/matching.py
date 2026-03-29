"""术语匹配召回 — 算法 B。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from rapidfuzz import fuzz, process

from .types import MatchCandidate, MatchResult

if TYPE_CHECKING:
    from .cache import UserNameCache
    from .types import Mention

log = logging.getLogger(__name__)

# 模糊匹配默认配置
DEFAULT_FUZZY_SCORE_CUTOFF = 50.0  # 相似度阈值 (0-100)
DEFAULT_FUZZY_MAX_CANDIDATES = 5   # 最大返回候选数


def match_mentions(
    mentions: tuple[Mention, ...],
    session: Any,
    user_id: str | None = None,
    global_name_index: dict[str, list[tuple[str, str, str]]] | None = None,
    user_cache: UserNameCache | None = None,
    # 新增参数
    enable_fuzzy: bool = True,
    fuzzy_score_cutoff: float = DEFAULT_FUZZY_SCORE_CUTOFF,
    fuzzy_max_candidates: int = DEFAULT_FUZZY_MAX_CANDIDATES,
) -> MatchResult:
    """Match mentions against merged global/user name indexes.
    Algorithm B (matching recall) behavior:
    - Exact match from merged name index.
    - Confidence is based on original name type:
      - standard_name -> 1.0
      - alias -> 0.9
    - Fuzzy matching for unmatched mentions using rapidfuzz.
    """
    user_name_index: dict[str, list[tuple[str, str, str, float]]] | None = None
    if user_id is not None and user_cache is not None:
        user_name_index = user_cache.get(user_id)
        if user_name_index is None:
            user_name_index = user_cache.load(user_id, session)
        log.debug("Loaded user name index for user_id=%s", user_id)
    merged_name_index = _merge_name_indexes(global_name_index, user_name_index)
    log.debug(
        "Matching %d mentions with merged index size=%d",
        len(mentions),
        len(merged_name_index),
    )
    exact: dict[str, tuple[MatchCandidate, ...]] = {}
    fuzzy: dict[str, tuple[MatchCandidate, ...]] = {}
    for mention in mentions:
        postings = merged_name_index.get(mention.text)
        if postings:
            # 精确匹配
            exact_candidates: list[MatchCandidate] = []
            for term_id, term_type_code, source_match_type, score in postings:
                confidence = 1.0
                exact_candidates.append(
                    MatchCandidate(
                        term_id=term_id,
                        term_name=mention.text,
                        term_type_code=term_type_code,
                        match_type="exact",
                        confidence=confidence,
                        score=score,
                    )
                )
            exact[mention.text] = tuple(exact_candidates)
        else:
            # 未精确匹配，尝试模糊匹配
            if enable_fuzzy and global_name_index:
                fuzzy_candidates = _fuzzy_match(
                    query=mention.text,
                    name_index=global_name_index,
                    score_cutoff=fuzzy_score_cutoff,
                    max_candidates=fuzzy_max_candidates,
                )
                fuzzy[mention.text] = tuple(fuzzy_candidates)
            else:
                fuzzy[mention.text] = ()
    return MatchResult(exact=exact, fuzzy=fuzzy)

def _fuzzy_match(
    query: str,
    name_index: dict[str, list[tuple[str, str, str]]],
    score_cutoff: float = DEFAULT_FUZZY_SCORE_CUTOFF,
    max_candidates: int = DEFAULT_FUZZY_MAX_CANDIDATES,
) -> list[MatchCandidate]:
    """使用 rapidfuzz 进行模糊匹配。"""
    if not query or not name_index:
        return []
    candidates = list(name_index.keys())
    if not candidates:
        return []
    # rapidfuzz 模糊匹配
    results_raw = process.extract(
        query,
        candidates,
        scorer=fuzz.WRatio,
        limit=max_candidates,
        score_cutoff=score_cutoff,
    )
    # 转换结果为 MatchCandidate
    fuzzy_candidates: list[MatchCandidate] = []
    for matched_name, score, _ in results_raw:
        similarity = score / 100.0  # 转换为 0.0-1.0
        
        # 获取该匹配术语的所有候选项
        postings = name_index.get(matched_name, [])
        for term_id, term_type_code, match_type in postings:
            fuzzy_candidates.append(
                MatchCandidate(
                    term_id=term_id,
                    term_name=matched_name,
                    term_type_code=term_type_code,
                    match_type="fuzzy",
                    confidence=similarity,
                    score=0.0,  # 模糊匹配没有个人 score
                )
            )
    return fuzzy_candidates

def _merge_name_indexes(
    global_index: dict[str, list[tuple[str, str, str]]] | None,
    user_index: dict[str, list[tuple[str, str, str, float]]] | None,
) -> dict[str, list[tuple[str, str, str, float]]]:
    """Merge global and user name indexes.

    Rules:
    - Global entries are expanded from 3-tuple to 4-tuple with score=0.0.
    - For the same (name_text, term_id), user entry overrides global entry.
    """
    merged_by_name: dict[str, dict[str, tuple[str, str, str, float]]] = {}

    if global_index is not None:
        for name_text, global_entries in global_index.items():
            term_map = merged_by_name.setdefault(name_text, {})
            for term_id, term_type_code, match_type in global_entries:
                term_map.setdefault(term_id, (term_id, term_type_code, match_type, 0.0))

    if user_index is not None:
        for name_text, user_entries in user_index.items():
            term_map = merged_by_name.setdefault(name_text, {})
            for term_id, term_type_code, match_type, score in user_entries:
                term_map[term_id] = (term_id, term_type_code, match_type, score)

    merged: dict[str, list[tuple[str, str, str, float]]] = {}
    for name_text, term_map in merged_by_name.items():
        merged[name_text] = list(term_map.values())

    return merged
