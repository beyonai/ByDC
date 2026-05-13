"""术语搜索与别名消歧 — 委托层。

所有公开函数已迁移到 TermReader / TermSearchEngine 协议，
通过 ``create_reader()`` 工厂获取后端实例，不直接操作 SQLAlchemy。

协议方法映射：
- search_terms_by_type         → reader.search_terms()
- get_term_ids                 → reader.get_term_by_ids()
- get_object_props             → reader.get_object_props()
- get_object_props_by_code     → reader.get_object_props_by_code()
- get_term_names               → reader.get_term_names()
- get_prop_values_with_aliases → reader.get_prop_values_with_aliases()
- resolve_field_aliases        → reader.resolve_field_aliases()
- resolve_value_aliases        → reader.resolve_value_aliases()
- resolve_field_aliases_with_names → reader.resolve_field_aliases_with_names()
- get_prop_enum_values         → reader.get_prop_enum_values()
"""

from __future__ import annotations

from typing import cast

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.contracts.types import (
    FieldResolutionResult,
    FieldResolutionResultWithNames,
    NameItem,
    PropItem,
    SearchTermsResult,
    TagFilter,
    ValueResolutionResult,
    ValueWithAliases,
)


def search_terms_by_type(
    *,
    term_type_code: str,
    term_codes: list[str] | None = None,
    keyword: str | None = None,
    tags: list[TagFilter] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "relevance",
) -> SearchTermsResult:
    """按术语类型检索术语列表（精确匹配 + BM25 兜底）。

    Args:
        term_type_code: 术语类型编码（支持驼峰简写映射，如 ONTOLOGY_VIEW→view）。
        term_codes: 可选，限定术语编码列表（当前未使用，预留）。
        keyword: 可选关键词搜索（精确匹配 term_name/term_code，BM25 兜底）。
        tags: 可选标签过滤条件列表。
        limit: 返回条数（1..200）。
        offset: 分页偏移（>=0）。
        order_by: 排序方式（relevance/updated_time/created_time/term_name）。

    Returns:
        分页搜索结果，包含 total 和 items。
    """
    _ = term_codes  # 协议暂不支持 term_codes 过滤
    reader = create_reader()
    return reader.search_terms(
        term_type_code=term_type_code,
        keyword=keyword,
        tags=tags,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )


def get_term_ids(
    *,
    keys: list[tuple[str, str, str]],
) -> dict[tuple[str, str, str], str]:
    """批量根据 (library_id, term_type_code, term_code) 三元组查询 term_id。

    Args:
        keys: (library_id, term_type_code, term_code) 三元组列表。

    Returns:
        {(library_id, term_type_code, term_code) → term_id} 映射。
    """
    reader = create_reader()
    return reader.get_term_by_ids(keys=keys)


def get_object_props(
    *,
    source_term_ids: list[str],
) -> dict[str, list[PropItem]]:
    """批量查询对象/视图下的属性（通过 term_relation HAS_FIELD）。

    Args:
        source_term_ids: 源术语 ID 列表（view/object 的 term_id）。

    Returns:
        {source_term_id → [PropItem]} 映射。
    """
    reader = create_reader()
    return reader.get_object_props(source_term_ids=source_term_ids)


def get_object_props_by_code(
    *,
    scope_code: str,
) -> list[PropItem]:
    """根据对象 code 查询其所有属性。

    通过知识图谱中的 HAS_FIELD 关系，接收对象编码（而非内部 term_id），
    返回该对象下的所有属性术语。相较于 ``get_object_props``（需要 term_id），
    本函数面向外部消费者，入参为业务编码。

    Args:
        scope_code: 对象/视图编码（如 ``"sales_crm"``）。

    Returns:
        PropItem 列表，按属性编码排序。

    Example:
        >>> props = get_object_props_by_code(scope_code="sales_crm")
        >>> for p in props:
        ...     print(p.term_code, p.term_name)
    """
    reader = create_reader()
    return reader.get_object_props_by_code(scope_code=scope_code)


def get_term_names(
    *,
    term_ids: list[str],
    scope_filter: dict[str, object] | None = None,
) -> dict[str, list[NameItem]]:
    """批量查询术语的所有名称（标准名 + 别名），通用函数。

    Args:
        term_ids: 术语 ID 列表。
        scope_filter: 可选的作用域过滤条件（如 {"scope": "view", "code": "xxx"}）。

    Returns:
        {term_id → [NameItem]} 映射。
    """
    reader = create_reader()
    return reader.get_term_names(term_ids=term_ids, scope_filter=scope_filter)


def get_prop_values_with_aliases(
    *,
    source_term_ids: list[str],
) -> dict[str, list[ValueWithAliases]]:
    """批量查询对象下属性的值术语及其别名。

    路径: source → (HAS_FIELD) → prop → (parent_term_id) → child term

    Args:
        source_term_ids: 源术语 ID 列表。

    Returns:
        {source_term_id → [ValueWithAliases]} 映射。
    """
    reader = create_reader()
    return reader.get_prop_values_with_aliases(source_term_ids=source_term_ids)


def resolve_field_aliases(
    *,
    terms: list[str],
    scope_code: str,
    library_id: str | None = None,
    user_id: str | None = None,
    resolve_values: bool = False,
    value_terms: list[str] | None = None,
) -> FieldResolutionResult:
    """轻量级字段 + 值别名精确消歧。

    在 scope_code 对应的视图/对象下查找字段别名（TermName.name_text → prop term_code）
    和可选值别名（child term 的 term_name/TermName 别名）。

    Args:
        terms: 待解析的字段中文名/别名列表。
        scope_code: 视图或对象 code（如 ``"scene_enterprise_analysis"``）。
        library_id: 预留参数，v1 不使用。
        user_id: 预留参数，当前协议未使用。
        resolve_values: 是否对 value_terms 追加值级别消歧。
        value_terms: 待值消歧的过滤值列表（如企业名、地区名等）。

    Returns:
        FieldResolutionResult，包含 resolved / ambiguous / unresolved 三类结果。
    """
    _ = library_id  # reserved for future use
    _ = user_id  # 协议当前不支持 user_id 过滤
    reader = create_reader()
    return reader.resolve_field_aliases(
        terms=terms,
        scope_code=scope_code,
        library_id=library_id,
        resolve_values=resolve_values,
        value_terms=value_terms,
    )


def resolve_value_aliases(
    *,
    terms: list[str],
    scope_code: str,
    user_id: str | None = None,
) -> ValueResolutionResult:
    """轻量级属性值精确消歧。

    在 scope_code 对应的 view/object 下，通过关系链路
    ``view/object → HAS_FIELD → prop → (parent_term_id) → child term``
    查找值术语，并在 child term 的 ``term_name`` 和 ``TermName.name_text``（别名）
    中精确匹配输入 terms。

    用于 filter value 级别的消歧：当用户查询包含企业名、地区名等枚举值时，
    判断该值是否为已知的合法属性值，避免不必要的澄清中断。

    Args:
        terms: 待匹配的值列表（如企业名、地区名等）。
        scope_code: 视图或对象 code（如 ``"scene_enterprise_analysis"``）。
        user_id: 预留参数，当前协议未使用。

    Returns:
        ValueResolutionResult，包含 matched（已知值）和 unmatched（未知值）。
    """
    _ = user_id  # 协议当前不支持 user_id 过滤
    reader = create_reader()
    return reader.resolve_value_aliases(terms=terms, scope_code=scope_code)


def resolve_field_aliases_with_names(
    *,
    terms: list[str],
    scope_code: str,
    library_id: str | None = None,
    user_id: str | None = None,
    resolve_values: bool = False,
    value_terms: list[str] | None = None,
) -> FieldResolutionResultWithNames:
    """扩展版字段别名消歧：resolved 同时返回 term_name。

    与 ``resolve_field_aliases`` 共享逻辑，区别仅在于
    resolved 字典的 value 类型为 ``ResolvedField(term_code, term_name)``
    而非纯 ``str``。

    .. note::
        当前后端实现仅支持字段级别的精确消歧（通过别名和 term_code 两种匹配）。
        ``library_id``、``user_id``、``resolve_values``、``value_terms`` 参数
        保留用于未来扩展，暂不传递给后端。

    Args:
        terms: 待解析的字段中文名/别名列表。
        scope_code: 视图或对象 code。
        library_id: 预留参数，v1 不使用。
        user_id: 预留参数，当前协议未使用。
        resolve_values: 预留参数，当前后端未实现值消歧。
        value_terms: 预留参数，当前后端未实现值消歧。

    Returns:
        FieldResolutionResultWithNames。
    """
    _ = library_id
    _ = user_id
    _ = resolve_values
    _ = value_terms
    reader = create_reader()
    # resolve_field_aliases_with_names 是 PostgresTermReader 的扩展方法，
    # 不在 TermReader 协议中。
    return cast(
        FieldResolutionResultWithNames,
        reader.resolve_field_aliases_with_names(  # type: ignore[attr-defined]
            terms=terms,
            scope_code=scope_code,
        ),
    )


def get_prop_enum_values(
    *,
    scope_code: str,
    field_codes: list[str],
) -> dict[str, list[str]]:
    """查询指定 prop 的枚举值（child term_name + 别名）。

    路径: view/object(scope_code) → HAS_FIELD → prop(field_code) → child terms。
    child term 的 term_name 和 TermName 别名均作为枚举值返回。

    Args:
        scope_code: 视图或对象 code。
        field_codes: 待查询的 prop term_code 列表。

    Returns:
        {field_code → [枚举值列表]}，去重保序。
    """
    reader = create_reader()
    return reader.get_prop_enum_values(scope_code=scope_code, field_codes=field_codes)


__all__ = [
    "get_object_props",
    "get_object_props_by_code",
    "get_prop_enum_values",
    "get_prop_values_with_aliases",
    "get_term_ids",
    "get_term_names",
    "resolve_field_aliases",
    "resolve_field_aliases_with_names",
    "resolve_value_aliases",
    "search_terms_by_type",
]
