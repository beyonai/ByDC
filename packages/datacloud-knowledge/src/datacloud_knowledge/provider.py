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

from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
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

    在指定作用域下，将用户输入的业务别名（如"销售额"）精确匹配到系统字段编码（如 "sales_amount"）。

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
    reader = PostgresTermReader()
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
        term_codes: 可选，限定术语编码列表。
        keyword: 可选，关键词搜索。
        tags: 可选，标签过滤条件。
        limit: 返回条数（1..200）。
        offset: 分页偏移。
        order_by: 排序方式（relevance/updated_time/created_time/term_name）。

    Returns:
        分页搜索结果。
    """
    reader = PostgresTermReader()
    return reader.search_terms(
        term_type_code=term_type_code,
        keyword=keyword,
        tags=list(tags) if tags is not None else None,
        limit=limit,
        offset=offset,
        order_by=order_by,
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

    if needs_clarification:
        # 类型收窄：my py 需要显式检查才能推断非 None
        if form is None or metadata is None:
            raise ValueError("form and metadata are required when needs_clarification is True")
        form_text = _serialize_payload(form)
        metadata_text = _serialize_payload(metadata)
        formatter = (
            _format_clarification_query if mode == "query" else _format_clarification_compute
        )
        formatted = formatter(query, original_input, form_text, metadata_text)
    else:
        formatted = original_input

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

    接收业务编码（如 ``"sales_crm"``），通过知识图谱 HAS_FIELD 关系返回该对象下的
    所有属性术语。典型用途：前端选择数据对象后，动态展示可查询的字段列表。

    Args:
        scope_code: 对象/视图编码。

    Returns:
        PropItem 列表（term_code=属性编码, term_name=属性名称），按编码排序。

    Example:
        >>> props = get_object_props_by_code(scope_code="sales_crm")
        >>> for p in props:
        ...     print(f"{p.term_code}: {p.term_name}")
    """
    reader = PostgresTermReader()
    return reader.get_object_props_by_code(scope_code=scope_code)


def get_prop_enum_values(
    *,
    scope_code: str,
    field_codes: Sequence[str],
) -> dict[str, list[str]]:
    """查询指定属性的可选枚举值。

    接收对象编码和属性编码列表，返回每个属性的可选值（含别名去重）。
    典型用途：前端下拉框展示字段的过滤候选项。

    Args:
        scope_code: 对象/视图编码。
        field_codes: 属性编码列表。

    Returns:
        {field_code → [可选值列表]}，去重保序。

    Example:
        >>> values = get_prop_enum_values(
        ...     scope_code="sales_crm",
        ...     field_codes=["region", "level"],
        ... )
        >>> values["region"]   # → ["华东", "华南", "华北", ...]
        >>> values["level"]    # → ["高", "中", "低"]
    """
    reader = PostgresTermReader()
    return reader.get_prop_enum_values(
        scope_code=scope_code, field_codes=list(field_codes)
    )


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
    "PersistedSynonyms",
    "finalize_query_clarification",
    "get_object_props_by_code",
    "get_prop_enum_values",
    "prepare_query_clarification",
    "resolve_field_aliases",
    "search_terms_by_type",
]
