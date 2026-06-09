"""术语搜索与别名消歧 — TermStore 模式层。

所有公开函数注入 TermStore 实例，不直接操作 adapters/。
orchestration.py 的 search_terms_with_fallback 已合并至此。
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_knowledge.capabilities.protocol import TermStore
from datacloud_knowledge.capabilities.types import LabelFilter, QueryResult
from datacloud_knowledge.contracts.types import (
    NameItem,
    PropItem,
    SearchTermsResult,
    TagFilter,
    ValueResolutionResult,
    ValueWithAliases,
)

log = logging.getLogger(__name__)

__all__ = [
    "get_object_props",
    "get_object_props_by_code",
    "get_prop_values_with_aliases",
    "get_term_ids",
    "get_term_names",
    "resolve_value_aliases",
    "search_terms_by_type",
    "search_terms_with_fallback",
]


# ═══════════════════════════════════════════════════════════════════════════════
# 搜索
# ═══════════════════════════════════════════════════════════════════════════════


def _tags_to_label_filters(tags: list[TagFilter] | None) -> list[LabelFilter] | None:
    """将 contracts TagFilter 列表转换为 capabilities LabelFilter 列表。"""
    if not tags:
        return None
    result: list[LabelFilter] = []
    for t in tags:
        fv = t.value
        if isinstance(fv, list):
            fv = ",".join(fv)
        result.append(LabelFilter(field_code=t.key, filter_value=fv))
    return result


def search_terms_by_type(
    store: TermStore,
    *,
    term_type_code: str,
    term_codes: list[str] | None = None,
    keyword: str | None = None,
    tags: list[TagFilter] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "relevance",
) -> SearchTermsResult:
    """按术语类型检索术语列表。

    通过 TermStore.query_terms() 执行检索，支持全文、精确匹配和语义搜索。

    Args:
        store:          TermStore 实例。
        term_type_code: 术语类型编码（如 ``"view"``、``"prop"``）。
        term_codes:     可选，限定术语编码列表（预留）。
        keyword:        可选关键词搜索（匹配 term_name/term_code）。
        tags:           可选标签过滤条件列表。
        limit:          返回条数（1..200）。
        offset:         分页偏移（>=0）。
        order_by:       排序方式（relevance/updated_time/created_time/term_name，当前未使用）。

    Returns:
        分页搜索结果（contracts.SearchTermsResult）。
    """
    _ = term_codes  # 预留
    _ = order_by  # TermStore 当前不支持服务端排序

    result: QueryResult = store.query_terms(
        term_type=term_type_code,
        keyword=keyword,
        label_filters=_tags_to_label_filters(tags),
        top_k=limit,
        offset=offset,
    )

    return _build_search_result(result)


def search_terms_with_fallback(
    store: TermStore | None = None,
    *,
    term_type_code: str,
    keyword: str | None = None,
    tags: list[TagFilter] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "relevance",
    reader: Any = None,  # 向后兼容：provider.py 传入 TermReader（忽略）
) -> SearchTermsResult:
    """精确匹配优先，无结果降级到全文搜索。

    编排逻辑：先使用 query_type="exact" 精确匹配 term_name/term_code，
    零结果时自动降级到 query_type="fulltext"（BM25 兜底）。

    原 orchestration.py 的 search_terms_with_fallback。

    Args:
        store:          TermStore 实例。
        term_type_code: 术语类型编码。
        keyword:        可选关键词。
        tags:           可选标签过滤条件列表。
        limit:          返回条数。
        offset:         分页偏移。
        order_by:       排序方式。

    Returns:
        分页搜索结果。
    """
    _ = order_by
    _ = reader  # 向后兼容：忽略 TermReader 参数

    if store is None:
        log.warning("search_terms_with_fallback called without store — returning empty result")
        return SearchTermsResult(total=0, items=[])

    label_filters = _tags_to_label_filters(tags)

    # Step 1: 精确匹配
    result = store.query_terms(
        term_type=term_type_code,
        keyword=keyword,
        query_type="exact",
        label_filters=label_filters,
        top_k=limit,
        offset=offset,
    )
    if result.total > 0 or not keyword:
        return _build_search_result(result)

    # Step 2: BM25 兜底
    log.info("精确匹配无结果，降级 fulltext: type=%s keyword=%s", term_type_code, keyword)
    result = store.query_terms(
        term_type=term_type_code,
        keyword=keyword,
        query_type="fulltext",
        label_filters=label_filters,
        top_k=limit,
        offset=offset,
    )
    return _build_search_result(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 批量查询
# ═══════════════════════════════════════════════════════════════════════════════


def get_term_ids(
    store: TermStore,
    *,
    keys: list[tuple[str, str, str]],
) -> dict[tuple[str, str, str], str]:
    """批量根据 (library_id, term_type_code, term_code) 三元组查询 term_id。

    Args:
        store: TermStore 实例。
        keys:  (library_id, term_type_code, term_code) 三元组列表。

    Returns:
        {(library_id, term_type_code, term_code) → term_id} 映射。
    """
    result: dict[tuple[str, str, str], str] = {}
    for lib_id, tt_code, t_code in keys:
        qr = store.query_terms(
            term_type=tt_code,
            keyword=t_code,
            query_type="exact",
            top_k=1,
        )
        if qr.items:
            result[(lib_id, tt_code, t_code)] = qr.items[0].term_id
    return result


def get_term_names(
    store: TermStore,
    *,
    term_ids: list[str],
    scope_filter: dict[str, object] | None = None,
) -> dict[str, list[NameItem]]:
    """批量查询术语的所有名称（标准名 + 别名）。

    Args:
        store:        TermStore 实例。
        term_ids:     术语 ID 列表。
        scope_filter: 可选的作用域过滤条件。

    Returns:
        {term_id → [NameItem]} 映射。
    """
    _ = scope_filter  # TermStore 当前不支持 scope_filter
    name_map: dict[str, list[NameItem]] = {}
    for tid in term_ids:
        detail = store.get_term_detail(dataset_id="", term_id=tid)
        if detail is None:
            name_map[tid] = []
            continue
        names: list[NameItem] = [NameItem(name_text=detail.term_name, is_primary=True)]
        for syn in detail.synonym_list:
            if syn:
                names.append(NameItem(name_text=syn, is_primary=False))
        name_map[tid] = names
    return name_map


# ═══════════════════════════════════════════════════════════════════════════════
# 对象属性查询
# ═══════════════════════════════════════════════════════════════════════════════


def get_object_props(
    store: TermStore,
    *,
    source_term_ids: list[str],
) -> dict[str, list[PropItem]]:
    """批量查询对象/视图下的属性。

    通过 TermStore.get_term_detail 获取 term_code，
    再用 query_terms(parent_term_code=...) 查找子属性。

    Args:
        store:           TermStore 实例。
        source_term_ids: 源术语 ID 列表（view/object 的 term_id）。

    Returns:
        {source_term_id → [PropItem]} 映射。
    """
    result: dict[str, list[PropItem]] = {}
    for tid in source_term_ids:
        detail = store.get_term_detail(dataset_id="", term_id=tid)
        if detail is None:
            result[tid] = []
            continue
        qr = store.query_terms(
            parent_term_code=detail.term_code,
            label_filters=[LabelFilter(field_code="termDataType", filter_value="prop")],
            top_k=500,
        )
        props: list[PropItem] = []
        for item in qr.items:
            props.append(
                PropItem(
                    term_id=item.term_id,
                    term_code=item.term_code,
                    term_name=item.term_name,
                )
            )
        result[tid] = props
    return result


def get_object_props_by_code(
    store: TermStore,
    *,
    scope_code: str,
) -> list[PropItem]:
    """根据对象 code 查询其所有属性。

    通过 query_terms(term_type=[scope_code], label_filters=[termDataType=prop])。

    Args:
        store:      TermStore 实例。
        scope_code: 对象/视图编码（如 ``"sales_crm"``）。

    Returns:
        PropItem 列表。
    """
    qr = store.query_terms(
        term_type=[scope_code] if scope_code else None,
        label_filters=[LabelFilter(field_code="termDataType", filter_value="prop")],
        top_k=500,
    )
    return [
        PropItem(
            term_id=item.term_id,
            term_code=item.term_code,
            term_name=item.term_name,
        )
        for item in qr.items
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 值消歧
# ═══════════════════════════════════════════════════════════════════════════════


def get_prop_values_with_aliases(
    store: TermStore,
    *,
    source_term_ids: list[str],
) -> dict[str, list[ValueWithAliases]]:
    """批量查询对象下属性的值术语及其别名。

    路径: source → (HAS_FIELD) → prop → (parent_term_id) → child term。

    Args:
        store:           TermStore 实例。
        source_term_ids: 源术语 ID 列表。

    Returns:
        {source_term_id → [ValueWithAliases]} 映射。
    """
    result: dict[str, list[ValueWithAliases]] = {}
    for tid in source_term_ids:
        detail = store.get_term_detail(dataset_id="", term_id=tid)
        if detail is None:
            result[tid] = []
            continue
        props_qr = store.query_terms(
            parent_term_code=detail.term_code,
            label_filters=[LabelFilter(field_code="termDataType", filter_value="prop")],
            top_k=500,
        )
        values: list[ValueWithAliases] = []
        for prop_item in props_qr.items:
            child_qr = store.query_terms(
                parent_term_code=prop_item.term_code,
                top_k=500,
            )
            for child in child_qr.items:
                aliases = (
                    [a.strip() for a in child.synonyms.split("|") if a.strip()]
                    if child.synonyms
                    else []
                )
                values.append(
                    ValueWithAliases(
                        parent_term_id=prop_item.term_id,
                        term_id=child.term_id,
                        term_code=child.term_code,
                        term_name=child.term_name,
                        aliases=aliases,
                    )
                )
        result[tid] = values
    return result


def resolve_value_aliases(
    store: TermStore,
    *,
    terms: list[str],
    scope_code: str,
    user_id: str | None = None,
) -> ValueResolutionResult:
    """轻量级属性值精确消歧。

    在 scope_code 对应的 view/object 下，查找值术语的 term_name 和别名是否匹配。

    Args:
        store:      TermStore 实例。
        terms:      待匹配的值列表（如企业名、地区名）。
        scope_code: 视图或对象 code。
        user_id:    预留参数。

    Returns:
        ValueResolutionResult。
    """
    _ = user_id

    props_qr = store.query_terms(
        term_type=[scope_code] if scope_code else None,
        label_filters=[LabelFilter(field_code="termDataType", filter_value="prop")],
        top_k=500,
    )

    matched: set[str] = set()
    all_value_names: set[str] = set()

    for prop_item in props_qr.items:
        child_qr = store.query_terms(
            parent_term_code=prop_item.term_code,
            top_k=500,
        )
        for child in child_qr.items:
            all_value_names.add(child.term_name)
            if child.synonyms:
                for raw_alias in child.synonyms.split("|"):
                    a = raw_alias.strip()
                    if a:
                        all_value_names.add(a)

    unmatched: list[str] = []
    for term in terms:
        if term in all_value_names:
            matched.add(term)
        else:
            unmatched.append(term)

    return ValueResolutionResult(matched=matched, unmatched=unmatched)


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════════


def _build_search_result(qr: QueryResult) -> SearchTermsResult:
    """将 capabilities QueryResult 转换为 contracts SearchTermsResult。

    capabilities.TermItem 和 contracts.TermItem 字段不同，需手动映射。
    """
    from datacloud_knowledge.contracts.types import TermItem as CTermItem

    items: list[CTermItem] = []
    for item in qr.items:
        items.append(
            CTermItem(
                term_id=item.term_id,
                term_code=item.term_code,
                term_name=item.term_name,
                term_type_code=item.term_type,
                desc_summary=item.desc,
                score=item.score,
            )
        )
    return SearchTermsResult(total=qr.total, items=items)
