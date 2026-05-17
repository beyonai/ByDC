"""Recall orchestration — unified and vector-only recall for clarification.

Moved from intent/clarification/_recall.py to retrieval/ as part of recall consolidation.
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_knowledge.adapters.opengauss.vector_validation import is_vector_recall_available
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
)
from datacloud_knowledge.retrieval.recall._paths import _batch_vector
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
    field_layers: list[ScopeRecallLayer] | None = None,
    value_layers: list[ScopeRecallLayer] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """对所有术语执行统一召回。

    将 ExtractedTerm 转为 TypedKeywordState 协议对象，
    调用 typed_multi_recall_with_session 执行召回。
    vector_only 术语（英文标识符如 stat_date）只走向量召回路径。

    When ``field_layers`` / ``value_layers`` are provided, whereValue terms use
    ``value_layers`` (for cross-ontology dimension values via joinkeys), while
    all other terms use ``field_layers`` (base ontology + confirmed_object only).
    ``scope_layers`` is a legacy synonym for when the caller doesn't split by type.

    Returns:
        dict["ktype:raw_text", list[CandidateDict]]。
    """
    # 去重：相同 ktype + raw_text 只召回一次
    seen: set[str] = set()
    normal_items: list[_RecallItem] = []
    value_items: list[_RecallItem] = []
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
        elif term.ktype == "whereValue":
            value_items.append(item)
        else:
            normal_items.append(item)

    result: dict[str, list[dict[str, Any]]] = {}

    # 字段类术语（select/whereKey/groupBy/orderBy）
    if normal_items:
        layers = field_layers if field_layers is not None else scope_layers
        result.update(
            typed_multi_recall_with_session(
                normal_items,
                top_k=top_k,
                scope_code=scope_code,
                scope_layers=layers,
            )
        )

    # whereValue 术语（维度值）— 独立 scope，可跨本体
    if value_items:
        layers = value_layers if value_layers is not None else scope_layers
        result.update(
            typed_multi_recall_with_session(
                value_items,
                top_k=top_k,
                scope_code=scope_code,
                scope_layers=layers,
            )
        )

    # 英文标识符：只走向量召回（BM25/子串匹配对英文→中文无意义）
    if vector_only_items:
        enable_vector = is_vector_recall_available()
        result.update(
            _vector_only_recall(
                vector_only_items, top_k=top_k, scope_code=scope_code, enable_vector=enable_vector
            )
        )

    return result


def build_scope_recall_layers(
    ontology_code: str,
    pre: PreResolveResult,
    cc_pre: PreResolveResult,
) -> tuple[list[ScopeRecallLayer], list[ScopeRecallLayer]]:
    """Build per-type scope stacks for recall validation.

    Returns ``(field_layers, value_layers)``:
    - **field_layers**: base ontology only. Field names (select/whereKey/groupBy/orderBy)
      are inherently scoped — they must belong to the current ontology.
    - **value_layers**: base ontology + included objects (if view) + joinkey_object
      (joinkeys.sourceField match).  whereValue dimension values may live in
      cross-referenced ontologies (e.g., ``handler_user_id`` values in ``po_users``).

    When ``ontology_code`` is a **view**, the empty-scope fallback sub-query in
    ``_build_effective_scope_clause`` needs ``HAS_FIELD`` relations from the root
    term to its props.  A view may lack the specific prop whose children contain
    the searched value terms (e.g. ``sales_person`` under ``by_customer``).  We
    resolve the objects that the view "包含" (HAS_OBJECT/MANY_TO_ONE relations to objects) and
    add them to ``value_layers``, so value terms from included objects can be
    found through their scopes.
    """
    field_codes = _collect_confirmed_field_codes(pre, cc_pre)
    base = [ScopeRecallLayer(scope_code=ontology_code, weight=1.0, label="ontology")]
    if not ontology_code or not field_codes:
        return base, base

    # ── field layers: base ontology only ──
    field_layers: list[ScopeRecallLayer] = list(base)

    # ── value layers: base + included_objects (if view) + joinkey_object ──
    value_layers: list[ScopeRecallLayer] = list(base)
    seen_scopes: set[str] = {ontology_code}

    # ── When ontology_code is a view, include HAS_OBJECT/MANY_TO_ONE-related objects
    #     (e.g. "研发管理视图_包含_用户信息表" → po_users).  These objects
    #     may have the HAS_FIELD → prop → child chain for value terms. ──
    included_codes: list[str] = _collect_view_included_objects(ontology_code)
    for code in included_codes:
        if code not in seen_scopes:
            value_layers.append(
                ScopeRecallLayer(scope_code=code, weight=0.8, label="included_object")
            )
            seen_scopes.add(code)

    related_codes: list[str] = _collect_joinkey_related_objects(ontology_code, field_codes)
    for code in related_codes:
        if code not in seen_scopes:
            value_layers.append(
                ScopeRecallLayer(scope_code=code, weight=0.7, label="joinkey_object")
            )
            seen_scopes.add(code)

    return field_layers, value_layers


def _collect_view_included_objects(ontology_code: str) -> list[str]:
    """Return object codes that a view "包含" (includes) via HAS_OBJECT/MANY_TO_ONE relations.

    Views define their data sources through HAS_OBJECT/MANY_TO_ONE relations to object-type
    terms (e.g., ``"研发管理视图_包含_用户信息表" → po_users``).  Unlike
    ``_collect_joinkey_related_objects``, this does NOT require joinkey
    matching — all included objects are relevant for whereValue recall.
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
                    " AND rel.relation_category IN ('HAS_OBJECT', 'MANY_TO_ONE') "
                    "JOIN term AS target "
                    "  ON target.term_id = rel.target_term_id "
                    " AND target.term_type_code = 'object' "
                    "WHERE source.term_code = :ontology_code "
                    "  AND source.term_type_code = 'view'"
                ),
                {"ontology_code": ontology_code},
            ).fetchall()
    except Exception:
        logger.warning(
            "[clarification] collect view included objects failed: ontology=%s",
            ontology_code,
            exc_info=True,
        )
        return []

    return [str(r[0]) for r in rows]


def _collect_joinkey_related_objects(
    ontology_code: str,
    field_codes: list[str],
) -> list[str]:
    """Extract target object codes where joinkeys.sourceField matches a confirmed field.

    Cross-object HAS_OBJECT/MANY_TO_ONE relations carry joinkeys (e.g.,
    ``handler_user_id → user_id``) stored in ``term_relation.ext_attrs``.
    This function only adds a target object to the scope when a confirmed
    field code is listed as a ``sourceField`` in at least one joinkey —
    avoiding the noise of adding ALL related objects.
    """
    if not field_codes:
        return []
    try:
        from sqlalchemy import text

        from datacloud_knowledge.adapters.opengauss._db.connection import get_session

        with get_session() as session:
            rows = session.execute(
                text(
                    "SELECT DISTINCT target.term_code, rel.ext_attrs "
                    "FROM term AS source "
                    "JOIN term_relation AS rel "
                    "  ON rel.source_term_id = source.term_id "
                    " AND rel.relation_category IN ('HAS_OBJECT', 'MANY_TO_ONE') "
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
            "[clarification] collect joinkey related objects failed for ontology=%s",
            ontology_code,
            exc_info=True,
        )
        return []

    result: list[str] = []
    field_set = frozenset(field_codes)
    for obj_code, ext_attrs in rows:
        if not isinstance(ext_attrs, dict):
            continue
        for jk in ext_attrs.get("joinkeys") or []:
            if isinstance(jk, dict) and jk.get("sourceField") in field_set:
                result.append(str(obj_code))
                break  # one match per object is enough
    return result


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
    enable_vector: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """对英文标识符术语只执行向量召回。

    英文编码（如 stat_date）无法通过 BM25/子串匹配命中中文术语名，
    但向量语义检索可以将 "stat_date" 匹配到 "统计日期"。

    当 enable_vector=False（向量服务不可用时），直接返回空结果，
    让上层走降级/澄清路径。
    """
    if not enable_vector:
        return {}

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
                category_cache[cat_key] = _load_type_codes_by_category(allowed_categories)
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
