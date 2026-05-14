"""Recall orchestration — unified and vector-only recall for clarification.

Moved from intent/clarification/_recall.py to retrieval/ as part of recall consolidation.
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.contracts.intent_types import ExtractedTerm, PreResolveResult
from datacloud_knowledge.contracts.rrf import rrf_fuse
from datacloud_knowledge.retrieval._recall_common import (
    KTYPE_CATEGORY_MAP,
    _load_type_codes_by_category,
    _shape_candidates,
)
from datacloud_knowledge.retrieval.recall import (
    PreparedBatch,
    RecallRequest,
    ScopeRecallLayer,
    _batch_vector,
)
from datacloud_knowledge.retrieval.typed_recall import typed_multi_recall_with_session

logger = logging.getLogger(__name__)


class _RecallItem:
    """轻量 TypedKeywordState 协议实现，用于传入 typed_multi_recall_with_session。"""

    __slots__ = ("keyword", "ktype", "search_enabled")

    def __init__(self, keyword: str, ktype: str, search_enabled: bool) -> None:
        self.keyword = keyword
        self.ktype = ktype
        self.search_enabled = search_enabled


def unified_recall(
    terms: list[ExtractedTerm],
    *,
    top_k: int = 10,
    scope_code: str | None = None,
    scope_layers: list[ScopeRecallLayer] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """对所有术语执行统一召回。

    将 ExtractedTerm 转为 TypedKeywordState 协议对象，
    调用 typed_multi_recall_with_session 执行召回。
    vector_only 术语（英文标识符如 stat_date）只走向量召回路径。

    Returns:
        dict["ktype:raw_text", list[CandidateDict]]。
    """
    # 去重：相同 ktype + raw_text 只召回一次
    seen: set[str] = set()
    normal_items: list[_RecallItem] = []
    vector_only_items: list[_RecallItem] = []
    for term in terms:
        if not term.search_enabled:
            continue
        key = f"{term.ktype}:{term.raw_text}"
        if key in seen:
            continue
        seen.add(key)
        item = _RecallItem(
            keyword=term.raw_text,
            ktype=term.ktype,
            search_enabled=True,
        )
        if term.vector_only:
            vector_only_items.append(item)
        else:
            normal_items.append(item)

    result: dict[str, list[dict[str, Any]]] = {}

    # 常规术语：走全部 4 路召回（BM25 + Jieba + Substring + Vector）
    if normal_items:
        result.update(
            typed_multi_recall_with_session(
                normal_items,
                top_k=top_k,
                scope_code=scope_code,
                scope_layers=scope_layers,
            )
        )

    # 英文标识符：只走向量召回（BM25/子串匹配对英文→中文无意义）
    if vector_only_items:
        result.update(_vector_only_recall(vector_only_items, top_k=top_k, scope_code=scope_code))

    return result


def build_scope_recall_layers(
    ontology_code: str,
    pre: PreResolveResult,
    cc_pre: PreResolveResult,
) -> list[ScopeRecallLayer]:
    """基于已确认字段构建加权 scope 栈，用于召回范围校验。

    两种 scope 扩展来源：
    1. ``get_matching_objects`` — 共享同名已确认字段的其他 object。
    2. 跨对象 BUSINESS 关系 — 当某个已确认字段的值存储在另一个 ontology 对象中
       （如 ``handler_user_id`` → ``po_users``），将目标对象作为额外 scope layer
       加入，使 whereValue 召回能搜到当前 ontology scope 之外的维度值。
    """
    layers: list[ScopeRecallLayer] = []
    field_codes = _collect_confirmed_field_codes(pre, cc_pre)
    if ontology_code:
        layers.append(ScopeRecallLayer(scope_code=ontology_code, weight=1.0, label="ontology"))
    if not ontology_code or not field_codes:
        return layers

    try:
        reader = create_reader()
        rows = reader.get_matching_objects(
            ontology_code=ontology_code,
            field_codes=field_codes,
        )
    except Exception:
        logger.warning("[clarification] build scope recall layers failed", exc_info=True)
        return layers

    for object_code, matched_count in rows:
        code = str(object_code)
        if code == ontology_code:
            continue
        weight = 1.5 + min(float(matched_count), 3.0) * 0.25
        layers.append(ScopeRecallLayer(scope_code=code, weight=weight, label="confirmed_object"))

    # ── 通过跨对象 BUSINESS 关系扩展 scope ──
    # 当某个字段的值存储在另一个对象中（如 handler_user_id → po_users），
    # whereValue 召回必须搜目标对象的 scope 才能找到维度值。
    seen_scopes: set[str] = {layer.scope_code for layer in layers if layer.scope_code}
    related_codes: list[str] = _collect_related_object_codes(ontology_code, field_codes)
    for code in related_codes:
        if code not in seen_scopes:
            layers.append(ScopeRecallLayer(scope_code=code, weight=0.7, label="related_object"))
            seen_scopes.add(code)
    return layers


def _collect_related_object_codes(
    ontology_code: str,
    field_codes: list[str],
) -> list[str]:
    """查找与当前 ontology 存在 BUSINESS 关系的对象。

    跨对象关系（如 by_rd_task → po_users，joinkeys: handler_user_id↔user_id）
    表明已确认字段的维度值存储在目标对象的 scope 中。此函数提取这些目标对象的
    term_code，供 scope recall layer 使用。
    """
    try:
        from sqlalchemy import text

        from datacloud_knowledge.adapters.opengauss._db.connection import get_session

        with get_session() as session:
            rows = session.execute(
                text(
                    "SELECT DISTINCT target.term_code "
                    "FROM term AS source "
                    "JOIN term_relation AS rel "
                    "  ON rel.source_term_id = source.term_id "
                    " AND rel.relation_category = 'BUSINESS' "
                    "JOIN term AS target "
                    "  ON target.term_id = rel.target_term_id "
                    " AND target.term_type_code = 'object' "
                    "WHERE source.term_code = :ontology_code "
                    "  AND source.term_type_code IN ('view', 'object')"
                ),
                {"ontology_code": ontology_code},
            ).fetchall()
    except Exception:
        logger.warning(
            "[clarification] collect related object codes failed for ontology=%s",
            ontology_code,
            exc_info=True,
        )
        return []
    return [str(r.term_code) for r in rows]


def _collect_confirmed_field_codes(pre: PreResolveResult, cc_pre: PreResolveResult) -> list[str]:
    """Collect confirmed ontology field codes while preserving first-seen order."""
    field_codes: list[str] = []
    for result in (pre, cc_pre):
        for resolved in result.confirmed.values():
            term_code = str(getattr(resolved, "term_code", ""))
            if term_code and term_code not in field_codes:
                field_codes.append(term_code)
    return field_codes


def _vector_only_recall(
    items: list[_RecallItem],
    *,
    top_k: int,
    scope_code: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """对英文标识符术语只执行向量召回。

    英文编码（如 stat_date）无法通过 BM25/子串匹配命中中文术语名，
    但向量语义检索可以将 "stat_date" 匹配到 "统计日期"。
    """
    # 构建 RecallRequest（需要 type_filter）
    category_cache: dict[frozenset[int], set[str]] = {}
    requests: list[RecallRequest] = []
    for item in items:
        allowed_categories = KTYPE_CATEGORY_MAP.get(item.ktype)
        if allowed_categories is None:
            type_filter: set[str] | None = None
        else:
            cat_key = frozenset(allowed_categories)
            if cat_key not in category_cache:
                category_cache[cat_key] = _load_type_codes_by_category(
                    allowed_categories  # type: ignore[arg-type]
                )
            type_filter = category_cache[cat_key]
            if not type_filter:
                continue

        frozen_filter = frozenset(type_filter) if type_filter is not None else None
        requests.append(
            RecallRequest(
                map_key=f"{item.ktype}:{item.keyword}",
                keyword=item.keyword,
                ktype=item.ktype,
                type_filter=frozen_filter,
                is_per_type=False,
                per_type_limit=0,
                scope_code=scope_code,
            )
        )

    if not requests:
        return {}

    batch = PreparedBatch(
        requests=tuple(requests),
        normal_requests=tuple(requests),
        per_type_requests=(),
    )

    # 只走向量路径
    vector_hits = _batch_vector(batch, top_k=top_k)

    # 整形为 CandidateDict
    result: dict[str, list[dict[str, Any]]] = {}
    for req in requests:
        hits = vector_hits.get(req.map_key, [])
        if hits:
            fused = rrf_fuse([hits], k=60, top_n=top_k * 3)
            candidates = _shape_candidates(fused, req.type_filter, top_k=top_k)
        else:
            candidates = []
        result[req.map_key] = candidates
        if candidates:
            logger.info(
                "[clarification] vector_only recall %s -> %d 候选, top=%s",
                req.map_key,
                len(candidates),
                candidates[0]["term_name"] if candidates else "",
            )

    return result
