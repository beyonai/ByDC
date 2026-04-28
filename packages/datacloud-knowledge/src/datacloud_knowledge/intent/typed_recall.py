"""分类型多路召回 — 基于五段式 ktype 的 typed multi-path recall + RRF 融合。

流程:
1. 按 ktype 确定允许的 type_category 集合
2. 从 term_type 表动态加载对应的 term_type_code 白名单
3. 对每个 keyword 并行执行 4 路召回（BM25-AND、BM25-OR via jieba、substring、vector）
4. 各路结果用外层 RRF 融合
5. 按 term_type_code 白名单过滤
6. 返回 dict[keyword, list[CandidateDict]]
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final, Protocol

from datacloud_knowledge.query.search.bm25 import (
    bm25_search,
    bm25_search_jieba,
    bm25_search_jieba_partitioned,
    bm25_search_partitioned,
)
from datacloud_knowledge.query.search.jieba_recall import jieba_recall
from datacloud_knowledge.query.search.rrf import rrf_fuse
from datacloud_knowledge.query.search.substring_recall import (
    substring_recall,
    substring_recall_partitioned,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from .batch_recall import ScopeRecallLayer


class TypedKeywordState(Protocol):
    keyword: str
    ktype: str
    search_enabled: bool


log = logging.getLogger(__name__)

CandidateDict = dict[str, Any]

# ── ktype → 允许的 type_category 集合 ──────────────────────────
# type_category 定义（term_type 表）:
#   1 = 列表术语 (LIST_TERM)    — 企业名、地址、网格名等维度值
#   2 = 字典术语 (DICT_TERM)    — 行业、状态、等级等枚举值
#   3 = 本体术语 (ONTOLOGY_TERM) — object/view/action/prop 等结构定义
#
# whereValue 需要匹配具体的值（列表/字典术语）
# select/groupBy/whereKey/orderBy 需要匹配字段/对象（本体术语）
# aggregation 不走知识召回

KTYPE_CATEGORY_MAP: Final[dict[str, set[int] | None]] = {
    "select": {3},
    "groupBy": {3},
    "whereKey": {3},
    "whereValue": {1, 2},
    "orderBy": {3},
    "aggregation": None,
}

# whereValue 单路多样性：每个 term_type_code 最多保留几条
_WHERE_VALUE_PER_TYPE: Final[int] = 3


def _diversify_by_type(
    ranked: list[tuple[str, str, str, str, str]],
    per_type: int = _WHERE_VALUE_PER_TYPE,
) -> list[tuple[str, str, str, str, str]]:
    """按 term_type_code 分组截断，保证类型多样性。

    输入 tuple: (term_id, term_name, name_id, term_type_code, term_code)。
    保持原始排序，每个 type 最多保留 per_type 条。
    """
    type_counts: dict[str, int] = defaultdict(int)
    result: list[tuple[str, str, str, str, str]] = []
    for item in ranked:
        ttc = item[3]  # term_type_code
        if type_counts[ttc] < per_type:
            result.append(item)
            type_counts[ttc] += 1
    return result


def _topn_per_type(
    results: list[tuple[str, str, str, str, str]],
    per_type: int,
) -> list[tuple[str, str, str, str, str]]:
    """对已有结果按 term_type_code 分桶取 top per_type（用于不支持 SQL 分区的路径）。"""
    buckets: dict[str, int] = defaultdict(int)
    merged: list[tuple[str, str, str, str, str]] = []
    for r in results:
        ttc = r[3] if len(r) > 3 else ""
        if buckets[ttc] < per_type:
            merged.append(r)
            buckets[ttc] += 1
    return merged


def _load_type_codes_by_category(
    session: Session,
    categories: set[int],
) -> set[str]:
    """从 term_type 表按 type_category 加载 type_code 集合。"""
    from datacloud_knowledge.knowledge_search.db.models import TermType

    rows = (
        session.query(TermType.type_code)
        .filter(TermType.type_category.in_(sorted(categories)))
        .all()
    )
    return {row.type_code for row in rows}


def typed_multi_recall(
    items: Sequence[TypedKeywordState],
    *,
    session: Session,
    top_k: int = 5,
    rrf_k: int = 60,
    enable_vector: bool = False,
    wv_per_type: int = _WHERE_VALUE_PER_TYPE,
    scope_code: str | None = None,
    scope_layers: Sequence[ScopeRecallLayer] | None = None,
) -> dict[str, list[CandidateDict]]:
    """对 TypedKeywordState 列表执行分类型多路召回。

    Args:
        items: 从 paradigm_builder._build_typed_items() 生成的类型化关键词列表。
        session: SQLAlchemy 数据库会话。
        top_k: 每个 keyword 最终返回的候选数量。
        rrf_k: RRF 平滑常数。
        enable_vector: 是否启用向量召回（需要 embedding 列非空）。
        wv_per_type: whereValue 每个 term_type_code 独立搜索的 top N。
    Returns:
        dict["ktype:keyword", list[CandidateDict]]。
        key 格式为 ``f"{item.ktype}:{item.keyword}"``，避免同名 keyword 在不同
        ktype 下冲突。CandidateDict 包含 term_id, term_name, term_type_code,
        match_type, confidence, score, name_id。
    """
    from .batch_recall import typed_multi_recall_batch

    return typed_multi_recall_batch(
        items,
        session=session,
        top_k=top_k,
        rrf_k=rrf_k,
        enable_vector=enable_vector,
        wv_per_type=wv_per_type,
        scope_code=scope_code,
        scope_layers=scope_layers,
    )


def _recall_single_keyword(
    *,
    session: Session,
    keyword: str,
    type_filter: set[str] | None,
    top_k: int,
    rrf_k: int,
    enable_vector: bool,
    ktype: str = "",
    wv_per_type: int = _WHERE_VALUE_PER_TYPE,
) -> list[CandidateDict]:
    """对单个 keyword 执行多路召回 + RRF 外融合。

    当 ``ktype == "whereValue"`` 时，每一路召回按 ``term_type_code`` 分组搜索，
    每个 type 独立搜 top N，保证类型多样性。
    """
    ranked_lists: list[list[tuple[str, str, str, str, str]]] = []
    path_names: list[str] = []  # 用于日志
    _per_type = ktype == "whereValue" and type_filter is not None and len(type_filter) > 1
    # ── 路径 1: BM25 AND（精确字符匹配）──
    try:
        if _per_type:
            bm25_and_results = bm25_search_partitioned(
                session,
                keyword,
                per_type_limit=wv_per_type,
                min_score=0.001,
                term_type_codes=type_filter,
            )
            raw = [
                (r.term_id, r.term_name, r.name_id, r.term_type_code, r.term_code)
                for r in bm25_and_results
            ]
        else:
            bm25_and_results = bm25_search(
                session,
                keyword,
                top_k=top_k * 3,
                min_score=0.001,
                term_type_codes=type_filter,
            )
            raw = [
                (r.term_id, r.term_name, r.name_id, r.term_type_code, r.term_code)
                for r in bm25_and_results
            ]
        if raw:
            ranked_lists.append(raw)
            path_names.append("bm25_and")
    except Exception:
        log.warning("BM25-AND recall failed for '%s'", keyword, exc_info=True)

    # ── 路径 3: jieba 词级 BM25（查询 name_keywords_jieba 列）──
    # 单次 SQL 完成词级匹配 + ts_rank_cd 排序，替代原来的 N 次 DB 查询 + RRF。
    # 若 name_keywords_jieba 列不存在，回退为旧的 jieba_recall。
    try:
        _t0 = time.monotonic()
        if _per_type:
            jieba_bm25_results = bm25_search_jieba_partitioned(
                session,
                keyword,
                per_type_limit=wv_per_type,
                min_score=0.001,
                term_type_codes=type_filter,
            )
            jieba_results = [
                (r.term_id, r.term_name, r.name_id, r.term_type_code, r.term_code)
                for r in jieba_bm25_results
            ]
        else:
            jieba_bm25_results = bm25_search_jieba(
                session,
                keyword,
                top_k=top_k * 3,
                min_score=0.001,
                term_type_codes=type_filter,
            )
            jieba_results = [
                (r.term_id, r.term_name, r.name_id, r.term_type_code, r.term_code)
                for r in jieba_bm25_results
            ]
        if not jieba_results:
            # jieba 列不存在或无结果，回退为旧的应用层 jieba 分词 + RRF
            if _per_type:
                jieba_results = jieba_recall(
                    session,
                    keyword,
                    top_k=wv_per_type * len(type_filter or ()) * 3,
                    rrf_k=rrf_k,
                    term_type_codes=type_filter,
                )
                jieba_results = _topn_per_type(jieba_results, wv_per_type)
            else:
                jieba_results = jieba_recall(
                    session,
                    keyword,
                    top_k=top_k * 3,
                    rrf_k=rrf_k,
                    term_type_codes=type_filter,
                )
        log.info(
            "[recall_perf] jieba    '%s': %.3fs hits=%d",
            keyword,
            time.monotonic() - _t0,
            len(jieba_results) if jieba_results else 0,
        )
        if jieba_results:
            ranked_lists.append(jieba_results)
            path_names.append("jieba")
    except Exception:
        log.warning("Jieba recall failed for '%s'", keyword, exc_info=True)

    # ── 路径 4: 子串匹配 ──
    try:
        _t0 = time.monotonic()
        if _per_type:
            substr_results = substring_recall_partitioned(
                session,
                keyword,
                per_type_limit=wv_per_type,
                term_type_codes=type_filter,
            )
        else:
            substr_results = substring_recall(
                session,
                keyword,
                top_k=top_k * 3,
                term_type_codes=type_filter,
            )
        log.info(
            "[recall_perf] substr   '%s': %.3fs hits=%d",
            keyword,
            time.monotonic() - _t0,
            len(substr_results) if substr_results else 0,
        )
        if substr_results:
            ranked_lists.append(substr_results)
            path_names.append("substring")
    except Exception:
        log.warning("Substring recall failed for '%s'", keyword, exc_info=True)

    # ── 路径 5: 向量召回（可选）──
    if enable_vector:
        try:
            _t0 = time.monotonic()
            from datacloud_knowledge.query.embedding import get_embedding_service
            from datacloud_knowledge.query.search.vector import vector_search

            embedding_svc = get_embedding_service()
            vector_results = vector_search(
                session, keyword, embedding_svc, top_k=top_k * 3, min_similarity=0.3
            )
            log.info(
                "[recall_perf] vector   '%s': %.3fs hits=%d",
                keyword,
                time.monotonic() - _t0,
                len(vector_results) if vector_results else 0,
            )
            if vector_results:
                raw = [
                    (r.term_id, r.term_name, r.name_id, r.term_type_code, r.term_code)
                    for r in vector_results
                ]
                ranked_lists.append(raw)
                path_names.append("vector")
        except Exception:
            log.warning("Vector recall failed for '%s'", keyword, exc_info=True)

    if not ranked_lists:
        log.debug("No recall results for '%s'", keyword)
        return []

    # ── 外层 RRF 融合 ──
    fused = rrf_fuse(ranked_lists, k=rrf_k, top_n=top_k * 3)

    log.debug(
        "Recall '%s' via [%s]: %d candidates before filter, %d after RRF",
        keyword,
        ", ".join(path_names),
        sum(len(rl) for rl in ranked_lists),
        len(fused),
    )

    # ── 按 ktype 的 term_type_code 白名单过滤 ──
    candidates = _shape_candidates(fused, type_filter, top_k=top_k)
    if _per_type:
        diversified = _diversify_by_type(
            [
                (
                    str(candidate["term_id"]),
                    str(candidate["term_name"]),
                    str(candidate["name_id"]),
                    str(candidate["term_type_code"]),
                    str(candidate.get("term_code") or ""),
                )
                for candidate in candidates
            ],
            per_type=wv_per_type,
        )
        refused = rrf_fuse([diversified], k=rrf_k, top_n=top_k) if diversified else []
        return _shape_candidates(refused, type_filter, top_k=top_k)

    return candidates


def _shape_candidates(
    fused: list[Any],
    type_filter: set[str] | frozenset[str] | None,
    *,
    top_k: int,
) -> list[CandidateDict]:
    candidates: list[CandidateDict] = []
    for c in fused:
        if type_filter is not None and c.term_type_code not in type_filter:
            continue
        candidates.append(
            {
                "term_id": c.term_id,
                "term_name": c.term_name,
                "term_type_code": c.term_type_code,
                "match_type": "multi_recall",
                "confidence": min(c.rrf_score * 10, 1.0),
                "score": c.rrf_score,
                "name_id": c.name_id,
                "term_code": getattr(c, "term_code", ""),
            }
        )
        if len(candidates) >= top_k:
            break
    return candidates
