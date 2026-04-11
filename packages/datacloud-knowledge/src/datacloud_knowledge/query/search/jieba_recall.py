"""结巴分词召回 — 将查询文本用 jieba 分词后，对每个 token 分别 BM25 召回再 RRF 内融合。

流程：
1. jieba.lcut(query_text) → tokens
2. 对每个 token 执行 bm25_search_with_or
3. 将每个 token 的结果列表作为一路，用 RRF 内融合
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from datacloud_knowledge.query.search.bm25 import BM25Result, bm25_search_with_or
from datacloud_knowledge.query.search.rrf import rrf_fuse

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

_jieba_module: Any | None = None
_jieba_module: Any | None = None


def _get_jieba() -> Any:
    """延迟导入 jieba 以避免启动时间开销。"""
    global _jieba_module  # noqa: PLW0603
    if _jieba_module is None:
        import jieba  # type: ignore[import-untyped]

        _jieba_module = jieba
    return _jieba_module


def _bm25_results_to_ranked_list(
    results: list[BM25Result],
) -> list[tuple[str, str, str, str]]:
    """将 BM25Result 列表转为 RRF 所需的 ranked tuple 列表。"""
    return [(r.term_id, r.term_name, r.name_id, r.term_type_code) for r in results]


def jieba_recall(
    session: Session,
    query_text: str,
    *,
    top_k: int = 10,
    min_bm25_score: float = 0.001,
    rrf_k: int = 60,
    term_type_codes: set[str] | None = None,
) -> list[tuple[str, str, str, str]]:
    """对查询文本进行 jieba 分词 + 逐 token BM25 召回 + RRF 内融合。

    Args:
        session: SQLAlchemy Session。
        query_text: 查询文本。
        top_k: 最终返回的结果数量。
        min_bm25_score: 每个 token 的 BM25 最低分阈值。
        rrf_k: RRF 平滑常数。

    Returns:
        ``(term_id, term_name, name_id, term_type_code)`` 列表，按 RRF 分数降序。
    """
    query_text = query_text.strip()
    if not query_text:
        return []

    jieba = _get_jieba()
    tokens: list[str] = [t for t in jieba.lcut(query_text) if len(t.strip()) > 0]

    if not tokens:
        return []

    log.debug("jieba_recall: '%s' → tokens=%s", query_text, tokens)

    # 对每个 token 执行 BM25 OR 搜索
    ranked_lists: list[list[tuple[str, str, str, str]]] = []
    for token in tokens:
        bm25_results = bm25_search_with_or(
            session,
            token,
            top_k=top_k * 2,  # 多召回一些供 RRF 融合
            min_score=min_bm25_score,
            term_type_codes=term_type_codes,
        )
        if bm25_results:
            ranked_lists.append(_bm25_results_to_ranked_list(bm25_results))

    if not ranked_lists:
        return []

    # RRF 内融合
    fused = rrf_fuse(ranked_lists, k=rrf_k, top_n=top_k)
    return [(c.term_id, c.term_name, c.name_id, c.term_type_code) for c in fused]
