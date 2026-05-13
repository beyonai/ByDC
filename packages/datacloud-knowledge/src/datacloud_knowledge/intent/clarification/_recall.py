"""Recall orchestration — unified and vector-only recall for clarification.

Moved from api.py to eliminate local imports and enable independent testing.
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_knowledge.adapters.opengauss._db.connection import get_session
from datacloud_knowledge.adapters.opengauss._db.models import Term, TermRelation
from datacloud_knowledge.contracts.rrf import rrf_fuse
from datacloud_knowledge.intent._recall_common import (
    KTYPE_CATEGORY_MAP,
    _load_type_codes_by_category,
    _shape_candidates,
)
from datacloud_knowledge.intent.recall import (
    PreparedBatch,
    RecallRequest,
    ScopeRecallLayer,
    _batch_vector,
)
from datacloud_knowledge.intent.service import typed_multi_recall_with_session

from .models import ExtractedTerm, PreResolveResult

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
    """Build a small weighted scope stack from confirmed fields for recall validation."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import aliased

    layers: list[ScopeRecallLayer] = []
    field_codes = _collect_confirmed_field_codes(pre, cc_pre)
    if ontology_code:
        layers.append(ScopeRecallLayer(scope_code=ontology_code, weight=1.0, label="ontology"))
    if not ontology_code or not field_codes:
        return layers

    try:
        view_term = aliased(Term, name="view_term")
        object_term = aliased(Term, name="object_term")
        prop_term = aliased(Term, name="prop_term")
        view_object_rel = aliased(TermRelation, name="view_object_rel")
        object_prop_rel = aliased(TermRelation, name="object_prop_rel")
        with get_session() as session:
            rows = session.execute(
                select(object_term.term_code, func.count(prop_term.term_id).label("matched_count"))
                .select_from(view_term)
                .join(view_object_rel, view_object_rel.source_term_id == view_term.term_id)
                .join(object_term, object_term.term_id == view_object_rel.target_term_id)
                .join(object_prop_rel, object_prop_rel.source_term_id == object_term.term_id)
                .join(prop_term, prop_term.term_id == object_prop_rel.target_term_id)
                .where(
                    view_term.term_code == ontology_code,
                    view_term.term_type_code.in_(["view", "object"]),
                    object_term.term_type_code == "object",
                    prop_term.term_type_code == "prop",
                    prop_term.term_code.in_(field_codes),
                )
                .group_by(object_term.term_code)
                .order_by(func.count(prop_term.term_id).desc())
                .limit(2)
            ).all()
    except Exception:
        logger.warning("[clarification] build scope recall layers failed", exc_info=True)
        return layers

    for object_code, matched_count in rows:
        code = str(object_code)
        if code == ontology_code:
            continue
        weight = 1.5 + min(float(matched_count), 3.0) * 0.25
        layers.append(ScopeRecallLayer(scope_code=code, weight=weight, label="confirmed_object"))
    return layers


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
    with get_session() as session:
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
                        session, allowed_categories
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
