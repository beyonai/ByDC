"""术语匹配召回 — 算法 B。

支持多种模糊匹配模式：
- rapidfuzz: 字符串相似度匹配（默认）
- bm25: PostgreSQL 全文搜索
- vector: 向量语义相似度搜索
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from rapidfuzz import fuzz, process

from .types import MatchCandidate, MatchResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from datacloud_knowledge.embedding import EmbeddingService

    from .cache import UserNameCache
    from .types import Mention

log = logging.getLogger(__name__)

# 模糊匹配默认配置
DEFAULT_FUZZY_SCORE_CUTOFF = 50.0  # 相似度阈值 (0-100)
DEFAULT_FUZZY_MAX_CANDIDATES = 5  # 最大返回候选数

# 搜索模式类型
SearchMode = Literal["strict", "rapidfuzz", "bm25", "vector"]


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
            user_name_index = user_cache.load(user_id)
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
            for term_id, term_type_code, _source_match_type, score in postings:
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
        # 未精确匹配，尝试模糊匹配
        elif enable_fuzzy and global_name_index:
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


def match_mentions_with_search(
    mentions: tuple[Mention, ...],
    session: Session,
    user_id: str | None = None,
    global_name_index: dict[str, list[tuple[str, str, str]]] | None = None,
    user_cache: UserNameCache | None = None,
    # 搜索模式参数
    search_mode: SearchMode = "strict",
    embedding_service: EmbeddingService | None = None,
    # 通用参数
    top_k: int = 5,
    min_score: float = 0.01,
    # rapidfuzz 特有参数
    fuzzy_score_cutoff: float = DEFAULT_FUZZY_SCORE_CUTOFF,
) -> dict[str, tuple[MatchCandidate, ...]]:
    """Match mentions with multiple search modes.

    支持三种模糊匹配模式：
    - rapidfuzz: 字符串相似度匹配
    - bm25: PostgreSQL 全文搜索（基于单字分词）
    - vector: 向量语义相似度搜索

    Args:
        mentions: 术语提及列表
        session: SQLAlchemy Session
        user_id: 用户 ID
        global_name_index: 全局名称索引
        user_cache: 用户缓存
        search_mode: 匹配模式 ("strict" | "rapidfuzz" | "bm25" | "vector")
        embedding_service: Embedding 服务（vector 模式必需）
        top_k: 返回候选数量
        min_score: 最小分数阈值
        fuzzy_score_cutoff: rapidfuzz 相似度阈值

    Returns:
        Result 包含精确匹配和模糊匹配结果
    """

    result: dict[str, tuple[MatchCandidate, ...]] = {}

    for mention in mentions:
        if search_mode == "strict":
            user_name_index: dict[str, list[tuple[str, str, str, float]]] | None = None
            if user_id is not None and user_cache is not None:
                user_name_index = user_cache.get(user_id)
                if user_name_index is None:
                    user_name_index = user_cache.load(user_id)
                log.debug("Loaded user name index for user_id=%s", user_id)
            merged_name_index = _merge_name_indexes(global_name_index, user_name_index)
            postings = merged_name_index.get(mention.text)
            if postings:
                # 精确匹配
                exact_candidates: list[MatchCandidate] = []
                for term_id, term_type_code, _source_match_type, score in postings:
                    exact_candidates.append(
                        MatchCandidate(
                            term_id=term_id,
                            term_name=mention.text,
                            term_type_code=term_type_code,
                            match_type="exact",
                            confidence=1.0,
                            score=score,
                        )
                    )
                result[mention.text] = tuple(exact_candidates)

        elif search_mode == "rapidfuzz" and global_name_index:
            fuzzy_candidates = _fuzzy_match(
                query=mention.text,
                name_index=global_name_index,
                score_cutoff=fuzzy_score_cutoff,
                max_candidates=top_k,
            )
            result[mention.text] = tuple(fuzzy_candidates)

        elif search_mode == "bm25":
            fuzzy_candidates = _bm25_match(
                session=session,
                query=mention.text,
                top_k=top_k,
                min_score=min_score,
            )
            result[mention.text] = tuple(fuzzy_candidates)

        elif search_mode == "vector":
            if embedding_service is None:
                log.warning("Vector mode requires embedding_service, skipping")
                result[mention.text] = ()
            else:
                fuzzy_candidates = _vector_match(
                    session=session,
                    query=mention.text,
                    embedding_service=embedding_service,
                    top_k=top_k,
                    min_similarity=min_score,
                )
                result[mention.text] = tuple(fuzzy_candidates)
        else:
            result[mention.text] = ()

    return result


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
        for term_id, term_type_code, _match_type in postings:
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


def _bm25_match(
    session: Session,
    query: str,
    top_k: int = 5,
    min_score: float = 0.01,
) -> list[MatchCandidate]:
    """使用 BM25 全文搜索进行匹配。"""
    from datacloud_knowledge.retrieval import bm25_search

    if not query or not query.strip():
        return []

    try:
        results = bm25_search(session, query, top_k=top_k, min_score=min_score)
        return [
            MatchCandidate(
                term_id=r.term_id,
                term_name=r.term_name,
                term_type_code=r.term_type_code,
                match_type="bm25",
                confidence=min(r.score, 1.0),
                score=0.0,
            )
            for r in results
        ]
    except Exception as e:
        log.error("BM25 match failed: %s", e)
        return []


def _vector_match(
    session: Session,
    query: str,
    embedding_service: EmbeddingService,
    top_k: int = 5,
    min_similarity: float = 0.5,
) -> list[MatchCandidate]:
    """使用向量语义搜索进行匹配。"""
    from datacloud_knowledge.retrieval import vector_search

    if not query or not query.strip():
        return []

    try:
        results = vector_search(
            session, query, embedding_service, top_k=top_k, min_similarity=min_similarity
        )
        return [
            MatchCandidate(
                term_id=r.term_id,
                term_name=r.term_name,
                term_type_code=r.term_type_code,
                match_type="vector",
                confidence=r.similarity,
                score=0.0,
            )
            for r in results
        ]
    except Exception as e:
        log.error("Vector match failed: %s", e)
        return []


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
