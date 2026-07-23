"""知识服务 Provider — 对外公开 API。

本模块提供六类核心能力的函数式接口：
1. resolve_field_aliases         字段别名解析
2. search_terms_by_type          术语检索
3. get_object_props_by_code      按对象 code 查询属性列表
4. get_prop_enum_values          按属性 code 查询可选枚举值
5. prepare_query_clarification   查询澄清分析
6. finalize_query_clarification  澄清回填

所有函数通过 PostgresTermReader 封装数据库会话，消费者无需管理 db_session。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from datacloud_knowledge.adapters import create_reader, create_writer
from datacloud_knowledge.contracts.term_provider_types import (
    ImportResult,
    LabelCondition,
    LabelFilter,
    QueryResult,
    QueryType,
    TermCreate,
    TermDetail,
    TermUpdate,
)
from datacloud_knowledge.contracts.types import (
    ClarificationMode as _ClarificationMode,
)
from datacloud_knowledge.contracts.types import (
    FieldResolutionResult,
    OpaquePayload,
    PropItem,
    SearchTermsResult,
    TagFilter,
)
from datacloud_knowledge.intent.clarification.api import (
    analyze_query_clarification as _analyze_query_clarification,
)
from datacloud_knowledge.intent.clarification.api import (
    format_clarification_compute as _format_clarification_compute,
)
from datacloud_knowledge.intent.clarification.api import (
    format_clarification_query as _format_clarification_query,
)
from datacloud_knowledge.intent.clarification.postprocess import (
    normalize_clarification_params as _normalize_clarification_params,
)
from datacloud_knowledge.intent.clarification.postprocess import (
    persist_confirmed_synonyms as _persist_confirmed_synonyms,
)
from datacloud_knowledge.retrieval.orchestration import search_terms_with_fallback

logger = logging.getLogger(__name__)

# ── 公共类型 ───────────────────────────────────────────────────────

ClarificationMode = _ClarificationMode


@dataclass(frozen=True, slots=True)
class PersistedSynonyms:
    """澄清确认过程中持久化的同义词汇总。"""

    created_ids: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FinalizedClarification:
    """澄清回填结果。"""

    structured_input: dict[str, Any]
    changed_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    persisted_synonyms: PersistedSynonyms | None = None


@dataclass(frozen=True, slots=True)
class ClarificationAnalysis:
    """澄清分析结果。"""

    needs_clarification: bool
    form: OpaquePayload | None = None
    metadata: OpaquePayload | None = None

    @property
    def knowledge(self) -> OpaquePayload | None:
        """向后兼容别名，等同 metadata。"""
        return self.metadata


# ── 公开 API ───────────────────────────────────────────────────────


def resolve_field_aliases(
    *,
    terms: Sequence[str],
    scope_code: str,
    library_id: str | None = None,
    user_id: str | None = None,
    resolve_values: bool = False,
    value_terms: Sequence[str] | None = None,
    language: str = "zh_CN",
) -> FieldResolutionResult:
    """字段别名消歧。

    .. deprecated::
        此函数绑定对象/字段领域概念（scope_code），违反通用设计。
        请使用 ``query_terms`` 按 term_type_code + parent_term_code 过滤
        并结合 ``list_term_names`` 自行编排别名匹配逻辑。

    Args:
        terms: 待解析的字段别名列表。
        scope_code: 视图或对象编码。
        library_id: 术语库 ID（可选）。
        user_id: 用户 ID（可选，用于用户级别名匹配）。
        resolve_values: 是否连带解析值别名。
        value_terms: 待值消歧的过滤值列表。
        language: 语言标识（"zh_CN" 或 "en_US"），预留参数，当前仅影响日志。

    Returns:
        FieldResolutionResult，含 resolved/ambiguous/unresolved 三类结果。
    """
    reader = create_reader()
    return reader.resolve_field_aliases(
        terms=list(terms),
        scope_code=scope_code,
        library_id=library_id,
        resolve_values=resolve_values,
        value_terms=list(value_terms) if value_terms is not None else None,
    )


def search_terms_by_type(
    *,
    term_type_code: str,
    term_codes: Sequence[str] | None = None,
    keyword: str | None = None,
    tags: Sequence[TagFilter] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "relevance",
) -> SearchTermsResult:
    """按术语类型检索术语列表。

    优先精确匹配 term_name/term_code，无结果时自动降级到 BM25 全文检索。

    Args:
        term_type_code: 术语类型编码。
        term_codes: 可选，限定术语编码列表（当前未使用，预留）。
        keyword: 可选，关键词搜索。
        tags: 可选，标签过滤条件。
        limit: 返回条数（1..200）。
        offset: 分页偏移。
        order_by: 排序方式（relevance/updated_time/created_time/term_name）。

    Returns:
        分页搜索结果。
    """
    del term_codes  # 预留参数，当前编排层未暴露 term_codes 过滤
    reader = create_reader()
    return search_terms_with_fallback(
        term_type_code=term_type_code,
        keyword=keyword,
        tags=list(tags) if tags is not None else None,
        limit=limit,
        offset=offset,
        order_by=order_by,
        reader=reader,
    )


def prepare_query_clarification(
    *,
    query: str,
    ontology_code: str,
    structured_input: Mapping[str, Any],
    mode: ClarificationMode,
    language: str = "zh_CN",
) -> ClarificationAnalysis:
    """分析查询是否需要澄清。

    返回澄清分析结果，包含是否需要澄清、澄清表单和元数据。

    Args:
        query: 用户原始查询文本。
        ontology_code: 本体编码。
        structured_input: 结构化查询输入。
        mode: 澄清模式（"query" 或 "compute"）。
        language: 语言标识，控制 LLM 提示词的语种。

    Returns:
        ClarificationAnalysis 对象。
    """
    _validate_mode(mode)
    analysis = _analyze_query_clarification(
        query=query,
        ontology_code=ontology_code,
        structured_input=dict(structured_input),
        mode=mode,
        language=language,
    )
    return ClarificationAnalysis(
        needs_clarification=analysis.needs_clarification,
        form=analysis.form or None,
        metadata=analysis.knowledge or None,
    )


def finalize_query_clarification(
    *,
    query: str,
    ontology_code: str,
    structured_input: Mapping[str, Any],
    mode: ClarificationMode,
    needs_clarification: bool,
    form: OpaquePayload | None = None,
    metadata: OpaquePayload | None = None,
    user_id: str | None = None,
    persist_confirmed_synonyms: bool = True,
    idempotency_key: str | None = None,
    language: str = "zh_CN",
) -> FinalizedClarification:
    """将澄清结果回填到结构化输入。

    应用用户确认的术语映射，持久化确认过的同义词。

    Args:
        query: 用户原始查询文本。
        ontology_code: 本体编码。
        structured_input: 原始结构化查询输入。
        mode: 澄清模式。
        needs_clarification: 是否需要澄清。
        form: 澄清表单（用户填写后的结果）。
        metadata: 澄清元数据。
        user_id: 用户 ID（持久化同义词时需要）。
        persist_confirmed_synonyms: 是否持久化本次确认的同义词。
        idempotency_key: 幂等键（当前未使用，预留）。
        language: 语言标识（当前仅传递给下游澄清流程）。

    Returns:
        FinalizedClarification，含回填后的结构化输入和变更路径。
    """
    del idempotency_key

    _validate_mode(mode)

    original_input = dict(structured_input)
    warnings: list[str] = []
    persisted_synonyms: PersistedSynonyms | None = None

    if form is None or metadata is None:
        raise ValueError("form and metadata are required")
    form_text = _serialize_payload(form)
    metadata_text = _serialize_payload(metadata)
    formatter = _format_clarification_query if mode == "query" else _format_clarification_compute
    # 回填表单（必须）
    formatted = formatter(query, original_input, form_text, metadata_text)
    # 标准化（必须）
    normalized = _normalize_clarification_params(
        formatted,
        ontology_code=ontology_code,
        user_id=user_id,
    )

    if persist_confirmed_synonyms and user_id and needs_clarification:
        try:
            created_ids = _persist_confirmed_synonyms(
                paradigm_list=_extract_paradigm_list(form),
                ontology_code=ontology_code,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("[provider] 持久化确认同义词失败: %s", exc)
            warnings.append(f"persist_confirmed_synonyms failed: {exc}")
            created_ids = []
        persisted_synonyms = PersistedSynonyms(created_ids=created_ids)

    changed_paths = _collect_changed_paths(original_input, normalized)
    return FinalizedClarification(
        structured_input=normalized,
        changed_paths=changed_paths,
        warnings=warnings,
        persisted_synonyms=persisted_synonyms,
    )


def get_object_props_by_code(
    *,
    scope_code: str,
) -> list[PropItem]:
    """根据对象/视图编码查询其下所有属性。

    .. deprecated::
        此函数绑定对象/属性领域概念，违反通用设计。
        请使用 ``query_terms(term_type_code="prop", parent_term_code=scope_code)`` 替代。

    Args:
        scope_code: 对象/视图编码。

    Returns:
        PropItem 列表（term_code=属性编码, term_name=属性名称），按编码排序。
    """
    reader = create_reader()
    return reader.get_object_props_by_code(scope_code=scope_code)


def get_prop_enum_values(
    *,
    scope_code: str,
    field_codes: Sequence[str],
) -> dict[str, list[str]]:
    """查询指定属性的可选枚举值。

    .. deprecated::
        此函数绑定属性/对象领域概念，违反通用设计。
        请使用 ``query_terms(parent_term_code=field_code)`` 替代。

    Args:
        scope_code: 对象/视图编码。
        field_codes: 属性编码列表。

    Returns:
        {field_code → [可选值列表]}，去重保序。
    """
    reader = create_reader()
    return reader.get_prop_enum_values(scope_code=scope_code, field_codes=list(field_codes))


# ── TermProvider 新增公开 API ─────────────────────────────────────────


def query_terms(
    *,
    dataset_ids: list[str] | None = None,
    keyword: str | None = None,
    term_name: str | None = None,
    term_type: str | None = None,
    query_type: QueryType = "fulltext",
    parent_term_code: str | None = None,
    label_filters: list[LabelFilter] | None = None,
    label_condition: LabelCondition = "and",
    term_ids: list[str] | None = None,
    ext_attrs: dict[str, Any] | None = None,
    query_vector: list[float] | None = None,
    top_k: int = 20,
    offset: int = 0,
) -> QueryResult:
    """检索术语。

    支持按关键词、术语名称、类型、标签等多维度检索，返回分页结果。
    典型用途：术语搜索、候选列表加载。

    Args:
        dataset_ids:      术语库 ID 列表。None/空 = 不限制。
        keyword:          检索关键词（模糊匹配 term_name/term_code）。
        term_name:        术语名称精确匹配。与 keyword 互斥。
        term_type:        术语类型编码。None = 不限制类型。
        query_type:       检索策略（fulltext/exact/embedding/mixed）。
        parent_term_code: 父术语编码过滤。None = 不限制。
        label_filters:    标签过滤条件列表。
        label_condition:  多标签组合方式（and/or）。
        term_ids:         按 ID 列表精确查询。传入时忽略 keyword/query_type。
        ext_attrs:        扩展属性键值过滤。None = 不限制。
        query_vector:     查询向量（仅 embedding/mixed 需要）。None = 不启用向量检索。
        top_k:            返回条数（1..200）。
        offset:           分页偏移（>=0）。

    Returns:
        QueryResult，包含 total 和 items（TermItem 列表）。
    """
    reader = create_reader()
    return reader.query_terms(
        dataset_ids=dataset_ids,
        keyword=keyword,
        term_name=term_name,
        term_type=term_type,
        query_type=query_type,
        parent_term_code=parent_term_code,
        label_filters=label_filters,
        label_condition=label_condition,
        term_ids=term_ids,
        ext_attrs=ext_attrs,
        query_vector=query_vector,
        top_k=top_k,
        offset=offset,
    )


def query_terms_batch(
    *,
    keywords: list[str],
    dataset_ids: list[str] | None = None,
    term_type_codes: list[str] | None = None,
    query_type: QueryType = "fulltext",
    parent_term_code: str | None = None,
    label_filters: list[LabelFilter] | None = None,
    label_condition: LabelCondition = "and",
    ext_attrs: dict[str, Any] | None = None,
    query_vectors: list[list[float]] | None = None,
    top_k: int = 20,
    offset: int = 0,
) -> list[QueryResult]:
    """批量检索术语 — 每个 keyword 返回独立的 QueryResult。

    内部为每个 keyword 执行独立的检索 + 元数据过滤。
    不支持 term_ids/term_name（精确匹配走 query_terms 单次调用）。

    Args:
        keywords:         搜索关键词列表。
        dataset_ids:      术语库 ID 列表。None/空 = 不限制。
        term_type_codes:  术语类型编码列表。None = 不限制类型，空列表 = 返回空。
        query_type:       检索策略（fulltext/exact/embedding/mixed）。
        parent_term_code: 父术语编码过滤。None = 不限制。
        label_filters:    标签过滤条件列表。
        label_condition:  多标签组合方式（and/or）。
        ext_attrs:        扩展属性键值过滤。None = 不限制。
        query_vectors:    查询向量列表（仅 embedding/mixed 需要，长度与 keywords 一致）。
        top_k:            返回条数（1..200）。
        offset:           分页偏移（>=0）。

    Returns:
        list[QueryResult]，与 keywords 一一对应。
    """
    reader = create_reader()
    return reader.query_terms_batch(
        keywords=keywords,
        dataset_ids=dataset_ids,
        term_type_codes=term_type_codes,
        query_type=query_type,
        parent_term_code=parent_term_code,
        label_filters=label_filters,
        label_condition=label_condition,
        ext_attrs=ext_attrs,
        query_vectors=query_vectors,
        top_k=top_k,
        offset=offset,
    )


def get_term_detail(
    *,
    dataset_id: str = "",
    library_id: str = "",
    term_id: str,
) -> TermDetail | None:
    """查询单条术语完整详情。

    返回术语的所有字段（含标签翻译、同义词列表、父术语名称）。
    典型用途：术语详情页、编辑前回显。

    Args:
        dataset_id: 术语库 ID（**已弃用**，请使用 ``library_id``）。
        library_id: 术语库 ID（新名称，ADR-002）。
        term_id:    术语 ID。

    Returns:
        TermDetail，不存在返回 None。
    """
    effective_library_id = library_id or dataset_id
    reader = create_reader()
    return reader.get_term_detail(library_id=effective_library_id, term_id=term_id)


def list_terms(
    *,
    dataset_id: str = "",
    library_id: str = "",
    domain_code: str | None = None,
    keyword: str | None = None,
    term_type: str | None = None,
    term_type_no_eq: str | None = None,
    page_index: int = 1,
    page_size: int = 50,
) -> QueryResult:
    """分页列出术语（每条含完整详情）。

    一次请求返回 TermDetail 列表（含 parent_term_name/synonym_list/label_info），
    替代 N 次并发 get_term_detail。典型用途：加载某类型全量术语、构建 name index。

    Args:
        dataset_id:      术语库 ID（**已弃用**，请使用 ``library_id``）。
        library_id:      术语库 ID（新名称，ADR-002）。
        domain_code:     领域编码过滤（可选）。
        keyword:          关键词搜索（可选）。
        term_type:       术语类型编码。None = 不限。
        term_type_no_eq: 排除的术语类型编码。传 "-1" 表示排除术语类型本身。
        page_index:      页码（从 1 开始）。
        page_size:       每页条数。

    Returns:
        QueryResult，其中 items 为 TermDetail 列表。
    """
    effective_library_id = library_id or dataset_id
    reader = create_reader()
    return reader.list_terms(
        library_id=effective_library_id,
        term_type=term_type,
        term_type_no_eq=term_type_no_eq,
        domain_code=domain_code,
        keyword=keyword,
        page_index=page_index,
        page_size=page_size,
    )


def import_terms(
    *,
    dataset_id: str = "",
    library_id: str = "",
    terms: list[TermCreate],
    backfill: bool = False,
) -> ImportResult:
    """批量新增术语（含同义词、标签、扩展属性）。

    典型用途：批量导入术语数据、知识包导入。

    Args:
        dataset_id: 目标术语库 ID（**已弃用**，请使用 ``library_id``）。
        library_id: 目标术语库 ID（新名称，ADR-002）。
        terms:      待新增术语列表。
        backfill:   导入后是否回填 tsvector 和 embedding 向量。默认 False。

    Returns:
        ImportResult，含创建数、更新数、跳过数、term_id 列表和错误信息。
    """
    effective_library_id = library_id or dataset_id
    with create_writer() as writer:
        result = writer.import_terms(library_id=effective_library_id, terms=terms)

    if backfill and result.term_ids:
        from datacloud_knowledge.adapters.opengauss._writers._term import (
            run_import_backfill,
        )

        run_import_backfill(result.term_ids)

    return result


def update_term(
    *,
    dataset_id: str,
    term_id: str,
    updates: TermUpdate,
) -> None:
    """更新术语。仅更新非 None 字段。

    典型用途：术语编辑保存、字段级部分更新。

    Args:
        dataset_id: 术语库 ID。
        term_id:    术语 ID。
        updates:    更新字段（None = 不修改）。

    Raises:
        ValueError: 术语不存在。
    """
    with create_writer() as writer:
        writer.update_term(dataset_id=dataset_id, term_id=term_id, updates=updates)


# ── 内部辅助函数 ───────────────────────────────────────────────────


def _validate_mode(mode: ClarificationMode) -> None:
    """校验澄清模式是否合法。"""
    if mode not in ("query", "compute"):
        raise ValueError(f"不支持的澄清模式: {mode!r}")


def _serialize_payload(payload: OpaquePayload) -> str:
    """将不透明载荷序列化为 JSON 字符串。"""
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False)


def _extract_paradigm_list(form: OpaquePayload | None) -> list[dict[str, Any]]:
    """从澄清表单中提取范式列表。"""
    if form is None:
        return []

    data: Any = form
    if isinstance(form, str):
        try:
            data = json.loads(form) if form else {}
        except (json.JSONDecodeError, ValueError):
            logger.warning("[provider] 解析表单载荷失败")
            return []

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        paradigm_list = data.get("paradigmList")
        if isinstance(paradigm_list, list):
            return [item for item in paradigm_list if isinstance(item, dict)]
    return []


def _collect_changed_paths(before: Any, after: Any, prefix: str = "") -> list[str]:
    """递归收集 JSON 结构中变更的路径。"""
    if before == after:
        return []

    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: list[str] = []
        keys = sorted(set(before.keys()) | set(after.keys()), key=str)
        for key in keys:
            key_path = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_collect_changed_paths(before.get(key), after.get(key), key_path))
        return paths or ([prefix] if prefix else [])

    if isinstance(before, list) and isinstance(after, list):
        child_paths: list[str] = []
        max_len = max(len(before), len(after))
        for idx in range(max_len):
            item_path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            before_item = before[idx] if idx < len(before) else None
            after_item = after[idx] if idx < len(after) else None
            child_paths.extend(_collect_changed_paths(before_item, after_item, item_path))
        return child_paths or ([prefix] if prefix else [])

    return [prefix or "$"]


# ── 公共导出 ───────────────────────────────────────────────────────

__all__ = [
    "ClarificationAnalysis",
    "ClarificationMode",
    "FinalizedClarification",
    "ImportResult",
    "PersistedSynonyms",
    "QueryResult",
    "QueryType",
    "TermCreate",
    "TermDetail",
    "TermUpdate",
    "finalize_query_clarification",
    "get_object_props_by_code",
    "get_prop_enum_values",
    "get_term_detail",
    "import_terms",
    "list_terms",
    "prepare_query_clarification",
    "query_terms",
    "query_terms_batch",
    "resolve_field_aliases",
    "search_terms_by_type",
    "update_term",
]
