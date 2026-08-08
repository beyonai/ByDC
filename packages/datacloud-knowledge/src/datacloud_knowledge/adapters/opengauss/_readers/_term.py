"""_TermReader Mixin — per-entity read operations for the OpenGauss adapter.

Extracted from ``reader.py`` PostgresTermReader.
All methods use ``self._get_session()`` from ``_ReaderBase`` instead of
``self._session_factory()``. No ``__init__`` (provided by ``_ReaderBase``).
"""

from __future__ import annotations

import json
import logging
import re
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import and_, bindparam, cast, func, literal, or_, select, text
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC, TIMESTAMP
from sqlalchemy.orm import aliased

from datacloud_knowledge.adapters.opengauss._db.models import (
    Term,
    TermDomain,
    TermKnowledge,
    TermName,
    TermRelation,
)
from datacloud_knowledge.adapters.opengauss.bm25 import bm25_search_with_or
from datacloud_knowledge.adapters.opengauss.jieba_recall import jieba_recall
from datacloud_knowledge.contracts.rrf import rrf_fuse
from datacloud_knowledge.contracts.term_provider_types import (
    EnumeratedObjectInstances,
    LabelCondition,
    LabelFilter,
    ObjectInstanceItem,
    QueryResult,
    QueryType,
    TermDetail,
)
from datacloud_knowledge.contracts.term_provider_types import (
    FilterSpec as TermFilterSpec,  # query_terms_by_labels filters 通道元素（区别于本模块 enumerate 的 FilterSpec 注册表条目）
)
from datacloud_knowledge.contracts.term_provider_types import (
    TermItem as ProviderTermItem,
)
from datacloud_knowledge.contracts.types import (
    AmbiguousCandidate,
    DimensionValueItem,
    FieldResolutionResult,
    FieldResolutionResultWithNames,
    NameItem,
    PropItem,
    ResolvedField,
    SearchTermsResult,
    ShortestPathNode,
    TagFilter,
    TermItem,
    UserScopedNameItem,
    ValueResolutionResult,
    ValueWithAliases,
)

from ._base import _ReaderBase

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _TermSearchRow:
    """搜索中间行结构，用于 ORM 查出的原始行的统一转换。"""

    term_id: str
    term_code: str
    term_name: str
    term_type_code: str
    desc_summary: str | None
    term_tags: dict[str, Any]
    created_time: Any | None
    updated_time: Any | None
    score: float | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# FilterSpec 注册表 — enumerate_object_instances 条件框架
#
# filters 数组 = [{"type": <注册表 key>, "params": <类型专属参数字典>}, ...]
# 新条件类型 = 注册表 +1 条（validate + build）+ 测试，RPC/handler/接口形状零改动。
# 静态 dict，非插件系统/DSL（防过度工程）。
#
# degree filter 请求形状:
#   {"type": "degree", "params": {"metric": "out_minus_in"|"out_ratio_in"|"out"|"in",
#                                 "op": "gt"|"gte"|"lt"|"lte"|"eq", "value": <数字>}}
# ═══════════════════════════════════════════════════════════════════════════════

_DEGREE_METRICS = ("out", "in", "out_minus_in", "out_ratio_in")
_DEGREE_OPS: dict[str, str] = {
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "eq": "=",
}


def _degree_metric_expr(metric: str) -> str:
    """degree metric 白名单 → SQL 度量表达式（防注入：白名单映射，绝不拼接输入）。

    度数语义（钉死）：只统计实例级边（两端 id 均非空）+ BUSINESS 类别；
    自环（source=target）进出各计一次；**范围统计**（T-65）：对端 term 必须
    落在 object_codes ∪ kb_resource_ids 并集内（EXISTS 截断邻域，见
    _degree_opposite_range）。
    双 JOIN 计数用 COUNT(DISTINCT relation_id) 防止 out/in 交叉膨胀。
    """
    out_expr = "COUNT(DISTINCT out_rel.relation_id)"
    in_expr = "COUNT(DISTINCT in_rel.relation_id)"
    if metric == "out":
        return out_expr
    if metric == "in":
        return in_expr
    if metric == "out_minus_in":
        return f"({out_expr} - {in_expr})"
    # out_ratio_in — 除零语义：in=0 且 out>0 → +∞（1e999，gt/gte 恒通过 lt/lte 恒不通过）；
    # in=0 且 out=0 → NULL 不参与
    return (
        f"CASE WHEN {out_expr} = 0 AND {in_expr} = 0 THEN NULL "
        f"WHEN {in_expr} = 0 THEN 1e999 "
        f"ELSE {out_expr} * 1.0 / {in_expr} END"
    )


def _degree_opposite_range(
    rel_alias: str,
    opposite_col: str,
    *,
    object_codes: list[str],
    kb_resource_ids: list[str],
) -> str:
    """对端范围判定 EXISTS 子查询 — 度数范围统计（T-65）并集语义。

    对端 term（out → ``target_term_id`` / in → ``source_term_id``）满足
    object_codes 或 kb_resource_ids **任一**维度（OR）即视为在范围内；某维
    为空时只生成该维条件。两维均空不会到达此路径（enumerate_object_instances
    范围全空提前返回空结果）。

    返回形如::

        EXISTS (
                    SELECT 1 FROM term ot
                     WHERE ot.term_id = out_rel.target_term_id
                       AND (ot.term_type_code IN :degree_object_codes
                         OR ot.ext_attrs->>'kb_resource_id' IN :degree_kb_resource_ids)
                  )

    对端条件使用**独立参数名**（degree_object_codes / degree_kb_resource_ids），
    与主查询 WHERE 的 :object_codes/:kb_resource_ids 分开绑定（同一值两份参数），
    防两处 IN 列表被同名参数串绑。
    """
    dims: list[str] = []
    if object_codes:
        dims.append("ot.term_type_code IN :degree_object_codes")
    if kb_resource_ids:
        dims.append("ot.ext_attrs->>'kb_resource_id' IN :degree_kb_resource_ids")
    return (
        "EXISTS (\n"
        "            SELECT 1 FROM term ot\n"
        f"             WHERE ot.term_id = {rel_alias}.{opposite_col}\n"
        f"               AND ({' OR '.join(dims)})\n"
        "          )"
    )


def _validate_degree_filter(params: dict[str, Any]) -> None:
    """degree filter 参数校验 — 非法抛 ValueError。"""
    metric = params.get("metric")
    if metric not in _DEGREE_METRICS:
        raise ValueError(f"非法 degree metric: {metric!r}，允许: {sorted(_DEGREE_METRICS)}")
    op = params.get("op")
    if op not in _DEGREE_OPS:
        raise ValueError(f"非法 degree op: {op!r}，允许: {sorted(_DEGREE_OPS)}")
    value = params.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        # 验收钉死 ValueError（_EXCEPTION_MAP: ValueError → 400 invalid_params）
        raise ValueError(f"degree value 必须是数字，收到: {value!r}")  # noqa: TRY004


def _build_degree_condition(alias: str, params: dict[str, Any]) -> tuple[str, dict[str, object]]:
    """degree filter → (条件片段, 绑定参数)。

    返回片段形如 ``<metric_expr> <op> :value``，绑定参数 key 固定为 ``value``，
    由调用侧做参数名唯一化（支持多个 filter AND 组合）。
    """
    _ = alias  # 保留 FilterSpec.build 的 (alias, params) 签名（票面钉死）
    metric = params["metric"]
    op = params["op"]
    value = params["value"]
    expr = _degree_metric_expr(metric)
    return f"{expr} {_DEGREE_OPS[op]} :value", {"value": value}


def _degree_sort_expr(params: dict[str, Any]) -> str:
    """degree 排序度量表达式（metric 值降序，HAVING/ORDER BY 复用同一表达式）。"""
    return _degree_metric_expr(params["metric"])


@dataclass(frozen=True, slots=True)
class FilterSpec:
    """枚举查询条件规格 — 注册表条目。

    Attributes:
        stage: 条件所在 SQL 阶段（"where" | "having"）。
        required_joins: 需要生成的 LEFT JOIN（"out"/"in"，空 = 无 JOIN）。
        validate: 参数校验，非法抛 ValueError。
        build: (alias, params) -> (SQL 片段, 绑定参数 dict)。
        sort_expr: 可选排序度量表达式构造器；含排序语义的 filter 提供，
                   无则查询按 term_id ASC（新 filter 类型无需改本方法）。
    """

    stage: Literal["where", "having"]
    required_joins: frozenset[str]
    validate: Callable[[dict[str, Any]], None]
    build: Callable[[str, dict[str, Any]], tuple[str, dict[str, object]]]
    sort_expr: Callable[[dict[str, Any]], str] | None = None


_FILTER_REGISTRY: dict[str, FilterSpec] = {
    "degree": FilterSpec(
        stage="having",
        required_joins=frozenset({"out", "in"}),
        validate=_validate_degree_filter,
        build=_build_degree_condition,
        sort_expr=_degree_sort_expr,
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# SortSpec 注册表 — enumerate_object_instances 排序框架（与 _FILTER_REGISTRY 同构）
#
# sort 请求形状（term_provider_types.SortSpec）:
#   {"by": "similarity", "params": {"query": <语义查询串>}}
# 新排序依据 = 注册表 +1 条（validate + build）+ 测试，RPC/handler 接口形状零改动。
#
# similarity 排序语义（钉死）:
#   - 候选集（object_codes/kb_resource_ids/filters 过滤后）内重排，不截断候选集
#     （仅分页 LIMIT/OFFSET，排序本身无 LIMIT）；
#   - 排序键 = term 下全部 name 的最佳相似度 MAX(1-(name_embedding <=> :vector))，
#     余弦公式与 _build_vector_sql 同形；name_embedding IS NULL → 排尾部（NULLS LAST）；
#   - 双键 = 分数 DESC, term_id ASC（稳定 tie-break，调用方统一拼接）；
#   - query 向量由 EmbeddingService 生成 1 次；Embedding 配置缺失/失败 → 静默降级
#     BM25 单字（ts_rank_cd(name_keywords)，name_keywords 97.3% 可用），不 500；
#   - query 空串 → 退化 term_id ASC（无排序）。
# ═══════════════════════════════════════════════════════════════════════════════


def _validate_similarity_sort(params: dict[str, Any]) -> None:
    """similarity 参数校验 — query 必须是 str（空串允许，退化 term_id ASC）。"""
    query = params.get("query")
    if query is not None and not isinstance(query, str):
        # 验收钉死 ValueError（_EXCEPTION_MAP: ValueError → 400 invalid_params）
        raise ValueError(f"similarity 排序的 query 必须是字符串，收到: {query!r}")


def _similarity_score_expr(alias: str = "tn") -> str:
    """相似度分数表达式 — 参照 _build_vector_sql 的余弦公式（1 - 余弦距离）。"""
    return f"1 - ({alias}.name_embedding <=> CAST(:vector AS vector))"


def _embed_query_vector(query: str) -> list[float] | None:
    """生成 query 向量；Embedding 配置缺失/调用失败 → None（静默降级 BM25，不 500）。

    EmbeddingService 来自 retrieval/embedding/service.py（OpenAI 兼容，
    DATACLOUD_EMBEDDING_API_BASE/KEY/MODEL 已配置；缺配置时 _init_model 抛
    RuntimeError），非 reader 方法。跨 Mixin 标注：本函数是 reader 模块对
    retrieval 层的单向调用，不产生循环依赖。
    """
    try:
        from datacloud_knowledge.retrieval.embedding.service import (
            get_embedding_service,
        )

        return get_embedding_service().get_text_embedding(query)
    except Exception:
        logger.warning(
            "similarity sort embedding 生成失败，静默降级 BM25: query=%r", query, exc_info=True
        )
        return None


def _build_similarity_sort(params: dict[str, Any]) -> tuple[str, dict[str, object]]:
    """similarity 排序 → (分数排序片段, 绑定参数)。

    片段 = 分数表达式 + DESC NULLS LAST（不含 term_id tie-break，调用方统一拼接）；
    空片段 = 退化（调用方回退 term_id ASC）。
    优先级：query 向量 → 降级 BM25 单字 → 空 query 退化。
    """
    raw_query = params.get("query")
    query = raw_query.strip() if isinstance(raw_query, str) else ""
    if not query:
        return "", {}
    query_vector = _embed_query_vector(query)
    if query_vector is not None:
        vector_str = "[" + ",".join(map(str, query_vector)) + "]"
        return f"MAX({_similarity_score_expr('tn')}) DESC NULLS LAST", {"vector": vector_str}
    # Embedding 不可用 → 静默降级 BM25 单字（ts_rank_cd(name_keywords)，与
    # bm25.py bm25_search_with_or 同款单字 OR tsquery 构建）
    from datacloud_knowledge.adapters.opengauss.bm25 import _build_char_tsquery

    tsquery = _build_char_tsquery(query, ts_operator="|")
    if not tsquery:
        return "", {}
    return (
        "MAX(ts_rank_cd(tn.name_keywords, q, 32)) DESC NULLS LAST",
        {"tsquery": tsquery},
    )


@dataclass(frozen=True, slots=True)
class SortSpecEntry:
    """枚举查询排序规格 — 注册表条目（与 FilterSpec 同构）。

    Attributes:
        validate: 参数校验，非法抛 ValueError。
        build: (params) -> (分数排序片段, 绑定参数 dict)；空片段 = 无排序
               （调用方回退 term_id ASC）。
        requires_name_join: 排序依赖 term_name 表（name 级特征）时 True。
    """

    validate: Callable[[dict[str, Any]], None]
    build: Callable[[dict[str, Any]], tuple[str, dict[str, object]]]
    requires_name_join: bool = False


_SORT_REGISTRY: dict[str, SortSpecEntry] = {
    "similarity": SortSpecEntry(
        validate=_validate_similarity_sort,
        build=_build_similarity_sort,
        requires_name_join=True,
    ),
}


class _TermReader(_ReaderBase):
    """Mixin providing all term-read operations.

    Inherits session factory and lazy schema check from ``_ReaderBase``.
    All query methods use ``self._get_session()``.
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # 公开方法 — 协议方法
    # ═══════════════════════════════════════════════════════════════════════════

    def search_terms_exact(
        self,
        *,
        term_type_code: str,
        keyword: str | None = None,
        tags: Sequence[TagFilter] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "relevance",
    ) -> SearchTermsResult:
        """按术语类型精确检索术语列表（原子查询，无 BM25 兜底）。

        仅执行精确匹配（term_name == keyword 或 term_code == keyword）。
        无匹配时返回空结果，由调用方决定是否降级到 BM25。

        Args:
            term_type_code: 术语类型编码（支持驼峰简写映射）。
            keyword: 可选关键词（精确匹配 term_name/term_code）。
            tags: 可选标签过滤条件列表。
            limit: 返回条数（1..200）。
            offset: 分页偏移（>=0）。
            order_by: 排序方式（relevance/updated_time/created_time/term_name）。

        Returns:
            SearchTermsResult，无精确匹配时 total=0。
        """
        if not (1 <= limit <= 200):
            raise ValueError("limit 必须在 1..200")
        if offset < 0:
            raise ValueError("offset 必须 >= 0")

        canonical_type = self._normalize_type_code(term_type_code)
        tags_list = list(tags) if tags is not None else None

        try:
            with self._get_session() as session:
                filters = self._build_filters(
                    canonical_type=canonical_type,
                    keyword=keyword,
                    tags=tags_list,
                )

                total = int(
                    session.execute(
                        select(func.count()).select_from(Term).where(*filters)
                    ).scalar_one()
                )

                if total == 0:
                    return SearchTermsResult(total=0, items=[])

                stmt = (
                    select(
                        Term.term_id,
                        Term.term_code,
                        Term.term_name,
                        Term.term_type_code,
                        Term.desc_summary,
                        Term.term_tags,
                        Term.created_time,
                        Term.updated_time,
                    )
                    .where(*filters)
                    .limit(limit)
                    .offset(offset)
                )
                stmt = self._apply_order_by(stmt, order_by=order_by)
                rows = [
                    self._convert_db_row_to_term_row(row) for row in session.execute(stmt).all()
                ]
        except Exception:
            logger.exception(
                "search_terms_exact failed: type=%s keyword=%s tags=%s",
                term_type_code,
                keyword,
                tags,
            )
            raise

        items: list[TermItem] = []
        for row in rows:
            items.append(
                TermItem(
                    term_id=row.term_id,
                    term_code=row.term_code,
                    term_name=row.term_name,
                    term_type_code=row.term_type_code,
                    desc_summary=row.desc_summary,
                    term_tags=row.term_tags,
                    created_time=row.created_time,
                    updated_time=row.updated_time,
                    score=row.score,
                )
            )

        return SearchTermsResult(total=total, items=items)

    def search_terms(
        self,
        *,
        term_type_code: str,
        keyword: str | None = None,
        tags: Sequence[TagFilter] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "relevance",
    ) -> SearchTermsResult:
        """按术语类型检索术语列表。

        优先通过精确匹配（term_name / term_code）查询，
        无精确命中时通过 BM25 全文搜索兜底。

        Args:
            term_type_code: 术语类型编码（支持驼峰简写映射，如 ONTOLOGY_VIEW→view）。
            keyword: 可选关键词（先精确匹配，无结果时走 BM25）。
            tags: 可选标签过滤条件列表。
            limit: 返回条数（1..200）。
            offset: 分页偏移（>=0）。
            order_by: 排序方式（relevance/updated_time/created_time/term_name）。

        Returns:
            分页搜索结果，包含 total 和 items。

        Raises:
            ValueError: 参数校验失败时抛出。
        """
        if not (1 <= limit <= 200):
            raise ValueError("limit 必须在 1..200")
        if offset < 0:
            raise ValueError("offset 必须 >= 0")

        canonical_type = self._normalize_type_code(term_type_code)
        normalized_keyword = (keyword or "").strip()
        tags_list = list(tags) if tags is not None else None

        try:
            with self._get_session() as session:
                base_filters = self._build_filters(
                    canonical_type=canonical_type,
                    keyword=keyword,
                    tags=tags_list,
                )
                bm25_filters = self._build_filters(
                    canonical_type=canonical_type,
                    keyword=None,
                    tags=tags_list,
                )

                total = int(
                    session.execute(
                        select(func.count()).select_from(Term).where(*base_filters)
                    ).scalar_one()
                )
                if total > 0:
                    stmt = (
                        select(
                            Term.term_id,
                            Term.term_code,
                            Term.term_name,
                            Term.term_type_code,
                            Term.desc_summary,
                            Term.term_tags,
                            Term.created_time,
                            Term.updated_time,
                        )
                        .where(*base_filters)
                        .limit(limit)
                        .offset(offset)
                    )
                    stmt = self._apply_order_by(stmt, order_by=order_by)
                    rows = [
                        self._convert_db_row_to_term_row(row) for row in session.execute(stmt).all()
                    ]
                elif normalized_keyword:
                    bm25_rows = bm25_search_with_or(
                        session,
                        normalized_keyword,
                        top_k=limit + offset,
                        min_score=0.001,
                        term_type_codes={canonical_type},
                    )
                    rows = self._convert_bm25_rows_to_term_rows(
                        session=session,
                        bm25_rows=bm25_rows,
                        filters=bm25_filters,
                    )
                    total = len(rows)
                    rows = rows[offset : offset + limit]
                else:
                    rows = []
        except Exception:
            logger.exception(
                "search_terms failed: term_type_code=%s, keyword=%s, tags=%s, limit=%s, offset=%s",
                term_type_code,
                keyword,
                tags,
                limit,
                offset,
            )
            raise

        items: list[TermItem] = []
        for row in rows:
            items.append(
                TermItem(
                    term_id=row.term_id,
                    term_code=row.term_code,
                    term_name=row.term_name,
                    term_type_code=row.term_type_code,
                    desc_summary=row.desc_summary,
                    term_tags=row.term_tags,
                    created_time=row.created_time,
                    updated_time=row.updated_time,
                    score=row.score,
                )
            )

        return SearchTermsResult(total=total, items=items)

    def get_term_by_ids(
        self, *, keys: Sequence[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """批量根据 (library_id, term_type_code, term_code) 三元组查询 term_id。

        Args:
            keys: (library_id, term_type_code, term_code) 三元组列表。

        Returns:
            {(library_id, term_type_code, term_code) → term_id} 映射。无结果的 key 不出现在字典中。
        """
        keys_list = list(keys)
        if not keys_list:
            return {}

        try:
            with self._get_session() as session:
                conditions = [
                    and_(
                        Term.library_id == library_id,
                        Term.term_type_code == term_type_code,
                        Term.term_code == term_code,
                    )
                    for library_id, term_type_code, term_code in keys_list
                ]
                rows = session.execute(
                    select(
                        Term.library_id, Term.term_type_code, Term.term_code, Term.term_id
                    ).where(or_(*conditions))
                ).all()
        except Exception:
            logger.exception("get_term_by_ids failed: keys=%s", keys_list)
            raise

        return {(str(row[0]), str(row[1]), str(row[2])): str(row[3]) for row in rows}

    def get_term_names(
        self,
        *,
        term_ids: Sequence[str],
        scope_filter: dict[str, object] | None = None,
    ) -> dict[str, list[NameItem]]:
        """批量查询术语的所有名称（标准名 + 别名）。

        通过 scope_filter 过滤 search_scope（JSONB），
        同时总是包含 global 作用域的名称。

        Args:
            term_ids: 术语 ID 列表。
            scope_filter: 可选的作用域过滤条件（如 {"scope": "view", "code": "xxx"}）。

        Returns:
            {term_id → [NameItem]} 映射。每个 term_id 至少包含一个空列表。
        """
        term_ids_list = list(term_ids)
        if not term_ids_list:
            return {}

        try:
            with self._get_session() as session:
                filters: list[Any] = [TermName.term_id.in_(term_ids_list)]
                if scope_filter is not None:
                    filters.append(
                        or_(
                            TermName.search_scope.contains(scope_filter),
                            TermName.search_scope.contains({"scope": "global"}),
                        )
                    )

                rows = session.execute(
                    select(
                        TermName.term_id,
                        TermName.name_text,
                        (TermName.name_text == Term.term_name).label("is_primary"),
                    )
                    .join(Term, Term.term_id == TermName.term_id)
                    .where(*filters)
                ).all()
        except Exception:
            logger.exception(
                "get_term_names failed: term_ids=%s, scope_filter=%s",
                term_ids_list,
                scope_filter,
            )
            raise

        result: dict[str, list[NameItem]] = {term_id: [] for term_id in term_ids_list}
        for term_id, name_text, is_primary in rows:
            result.setdefault(str(term_id), []).append(
                NameItem(name_text=str(name_text), is_primary=bool(is_primary))
            )
        return result

    def resolve_field_aliases(
        self,
        *,
        terms: Sequence[str],
        scope_code: str,
        library_id: str | None = None,
        resolve_values: bool = False,
        value_terms: Sequence[str] | None = None,
    ) -> FieldResolutionResult:
        """轻量级字段 + 值别名精确消歧。

        在 scope_code 对应的视图/对象下查找字段别名（TermName.name_text → prop term_code）
        和可选值别名（child term 的 term_name/TermName 别名，通过 HAS_TERM 链路）。

        Args:
            terms: 待解析的字段中文名/别名列表。
            scope_code: 视图或对象 code（如 "scene_enterprise_analysis"）。
            library_id: 预留参数，v1 不使用。
            resolve_values: 是否对 value_terms 追加值级别消歧。
            value_terms: 待值消歧的过滤值列表（如企业名、地区名等）。

        Returns:
            FieldResolutionResult，包含 resolved/ambiguous/unresolved 三类结果。
        """
        _ = library_id  # reserved for future use
        warnings.warn(
            "resolve_field_aliases() is deprecated: binds object/field domain "
            "concepts in the term protocol. Use query_terms + list_term_names instead.",
            FutureWarning,
            stacklevel=2,
        )

        effective_values = list(value_terms) if value_terms is not None else []
        if not scope_code or (not terms and not effective_values):
            all_unresolved = list(terms or []) + effective_values
            return FieldResolutionResult(unresolved=all_unresolved)

        unique_field_terms = list(dict.fromkeys(terms)) if terms else []
        unique_value_terms = list(dict.fromkeys(effective_values)) if effective_values else []

        view_scope: dict[str, str] = {"scope": "view", "code": scope_code}
        obj_scope: dict[str, str] = {"scope": "object", "code": scope_code}
        global_scope: dict[str, str] = {"scope": "global"}

        try:
            with self._get_session() as session:
                queries: list[Any] = []

                # 子查询 1：字段别名（TermName → prop，按 search_scope 过滤）
                if unique_field_terms:
                    field_q = (
                        select(
                            literal("field").label("match_type"),
                            TermName.name_text.label("matched_text"),
                            Term.term_code,
                            Term.term_name,
                            TermName.search_scope,
                        )
                        .join(Term, Term.term_id == TermName.term_id)
                        .where(
                            TermName.name_text.in_(unique_field_terms),
                            Term.term_type_code == "prop",
                            or_(
                                TermName.search_scope.contains(view_scope),
                                TermName.search_scope.contains(obj_scope),
                                TermName.search_scope.contains(global_scope),
                            ),
                        )
                    )
                    queries.append(field_q)

                # 子查询 2+3：值消歧（child term_name + TermName 别名）
                if resolve_values and unique_value_terms:
                    view_obj = aliased(Term, name="view_obj")
                    prop = aliased(Term, name="prop")
                    child = aliased(Term, name="child")
                    type_term = aliased(Term, name="type_term")
                    has_term_rel = aliased(TermRelation, name="has_term_rel")

                    _null_scope = cast(literal(None), JSONB)

                    # child.term_name 直接匹配
                    val_direct_q = (
                        select(
                            literal("value").label("match_type"),
                            child.term_name.label("matched_text"),
                            literal("").label("term_code"),
                            literal("").label("term_name"),
                            _null_scope.label("search_scope"),
                        )
                        .select_from(view_obj)
                        .join(TermRelation, TermRelation.source_term_id == view_obj.term_id)
                        .join(prop, prop.term_id == TermRelation.target_term_id)
                        .join(
                            has_term_rel,
                            (has_term_rel.source_term_id == prop.term_id)
                            & (has_term_rel.relation_category == "HAS_TERM"),
                        )
                        .join(type_term, type_term.term_id == has_term_rel.target_term_id)
                        .join(child, child.term_type_code == type_term.term_code)
                        .where(
                            view_obj.term_code == scope_code,
                            view_obj.term_type_code.in_(["view", "object"]),
                            prop.term_type_code == "prop",
                            child.term_name.in_(unique_value_terms),
                        )
                    )
                    queries.append(val_direct_q)

                    # TermName 别名匹配
                    view_obj2 = aliased(Term, name="view_obj2")
                    prop2 = aliased(Term, name="prop2")
                    child2 = aliased(Term, name="child2")
                    type_term2 = aliased(Term, name="type_term2")
                    has_term_rel2 = aliased(TermRelation, name="has_term2")
                    val_alias_q = (
                        select(
                            literal("value").label("match_type"),
                            TermName.name_text.label("matched_text"),
                            literal("").label("term_code"),
                            literal("").label("term_name"),
                            _null_scope.label("search_scope"),
                        )
                        .select_from(view_obj2)
                        .join(TermRelation, TermRelation.source_term_id == view_obj2.term_id)
                        .join(prop2, prop2.term_id == TermRelation.target_term_id)
                        .join(
                            has_term_rel2,
                            (has_term_rel2.source_term_id == prop2.term_id)
                            & (has_term_rel2.relation_category == "HAS_TERM"),
                        )
                        .join(type_term2, type_term2.term_id == has_term_rel2.target_term_id)
                        .join(child2, child2.term_type_code == type_term2.term_code)
                        .join(TermName, TermName.term_id == child2.term_id)
                        .where(
                            view_obj2.term_code == scope_code,
                            view_obj2.term_type_code.in_(["view", "object"]),
                            prop2.term_type_code == "prop",
                            TermName.name_text.in_(unique_value_terms),
                            or_(
                                TermName.search_scope.contains(global_scope),
                            ),
                        )
                    )
                    queries.append(val_alias_q)

                    # 子查询 4+5：View → included_object 值消歧
                    view_obj3 = aliased(Term, name="view_obj3")
                    included_obj = aliased(Term, name="included_obj")
                    include_rel = aliased(TermRelation, name="include_rel")
                    prop3 = aliased(Term, name="prop3")
                    child3 = aliased(Term, name="child3")
                    type_term3 = aliased(Term, name="type_term3")
                    has_term_rel3 = aliased(TermRelation, name="has_term3")

                    # included_object → child.term_name 直接匹配
                    val_included_direct_q = (
                        select(
                            literal("value").label("match_type"),
                            child3.term_name.label("matched_text"),
                            literal("").label("term_code"),
                            literal("").label("term_name"),
                            _null_scope.label("search_scope"),
                        )
                        .select_from(view_obj3)
                        .join(
                            include_rel,
                            (include_rel.source_term_id == view_obj3.term_id)
                            & (include_rel.relation_category == "HAS_OBJECT"),
                        )
                        .join(
                            included_obj,
                            (included_obj.term_id == include_rel.target_term_id)
                            & (included_obj.term_type_code == "object"),
                        )
                        .join(TermRelation, TermRelation.source_term_id == included_obj.term_id)
                        .join(prop3, prop3.term_id == TermRelation.target_term_id)
                        .join(
                            has_term_rel3,
                            (has_term_rel3.source_term_id == prop3.term_id)
                            & (has_term_rel3.relation_category == "HAS_TERM"),
                        )
                        .join(type_term3, type_term3.term_id == has_term_rel3.target_term_id)
                        .join(child3, child3.term_type_code == type_term3.term_code)
                        .where(
                            view_obj3.term_code == scope_code,
                            view_obj3.term_type_code.in_(["view", "object"]),
                            prop3.term_type_code == "prop",
                            child3.term_name.in_(unique_value_terms),
                        )
                    )
                    queries.append(val_included_direct_q)

                    # included_object → TermName 别名匹配
                    view_obj4 = aliased(Term, name="view_obj4")
                    included_obj2 = aliased(Term, name="included_obj2")
                    include_rel2 = aliased(TermRelation, name="include_rel2")
                    prop4 = aliased(Term, name="prop4")
                    child4 = aliased(Term, name="child4")
                    type_term4 = aliased(Term, name="type_term4")
                    has_term_rel4 = aliased(TermRelation, name="has_term4")

                    val_included_alias_q = (
                        select(
                            literal("value").label("match_type"),
                            TermName.name_text.label("matched_text"),
                            literal("").label("term_code"),
                            literal("").label("term_name"),
                            _null_scope.label("search_scope"),
                        )
                        .select_from(view_obj4)
                        .join(
                            include_rel2,
                            (include_rel2.source_term_id == view_obj4.term_id)
                            & (include_rel2.relation_category == "HAS_OBJECT"),
                        )
                        .join(
                            included_obj2,
                            (included_obj2.term_id == include_rel2.target_term_id)
                            & (included_obj2.term_type_code == "object"),
                        )
                        .join(TermRelation, TermRelation.source_term_id == included_obj2.term_id)
                        .join(prop4, prop4.term_id == TermRelation.target_term_id)
                        .join(
                            has_term_rel4,
                            (has_term_rel4.source_term_id == prop4.term_id)
                            & (has_term_rel4.relation_category == "HAS_TERM"),
                        )
                        .join(type_term4, type_term4.term_id == has_term_rel4.target_term_id)
                        .join(child4, child4.term_type_code == type_term4.term_code)
                        .join(TermName, TermName.term_id == child4.term_id)
                        .where(
                            view_obj4.term_code == scope_code,
                            view_obj4.term_type_code.in_(["view", "object"]),
                            prop4.term_type_code == "prop",
                            TermName.name_text.in_(unique_value_terms),
                            or_(
                                TermName.search_scope.contains(global_scope),
                            ),
                        )
                    )
                    queries.append(val_included_alias_q)

                if not queries:
                    all_unresolved = unique_field_terms + unique_value_terms
                    return FieldResolutionResult(unresolved=all_unresolved)

                # 执行 UNION ALL
                stmt = queries[0].union_all(*queries[1:]) if len(queries) > 1 else queries[0]
                rows = session.execute(stmt).all()

        except Exception:
            logger.exception(
                "resolve_field_aliases failed: terms=%s, scope_code=%s",
                unique_field_terms,
                scope_code,
            )
            raise

        # 分拣结果
        field_hits: dict[str, dict[str, tuple[str, dict[str, str]]]] = {}
        value_matched: set[str] = set()

        for match_type, matched_text, term_code, term_name, search_scope in rows:
            if str(match_type) == "field":
                alias = str(matched_text)
                code = str(term_code)
                if alias not in field_hits:
                    field_hits[alias] = {}
                if code not in field_hits[alias]:
                    raw_scope: dict[str, str] = (
                        {str(k): str(v) for k, v in search_scope.items()}
                        if isinstance(search_scope, dict)
                        else {}
                    )
                    field_hits[alias][code] = (str(term_name), raw_scope)
            else:
                value_matched.add(str(matched_text))

        resolved: dict[str, str] = {}
        ambiguous: dict[str, list[AmbiguousCandidate]] = {}
        unresolved: list[str] = []

        for term in unique_field_terms:
            candidates = field_hits.get(term)
            if candidates is None:
                unresolved.append(term)
            elif len(candidates) == 1:
                resolved[term] = next(iter(candidates))
            else:
                ambiguous[term] = [
                    AmbiguousCandidate(
                        term_code=code,
                        term_name=name,
                        matched_alias=term,
                        scope=scope,
                    )
                    for code, (name, scope) in candidates.items()
                ]

        # 值未命中的归入 unresolved
        if resolve_values and unique_value_terms:
            if value_matched:
                logger.info(
                    "[resolve_field_aliases] value_aliases: matched=%d unmatched=%d",
                    len(value_matched),
                    len(unique_value_terms) - len(value_matched),
                )
            unresolved.extend(t for t in unique_value_terms if t not in value_matched)
        elif unique_value_terms:
            unresolved.extend(unique_value_terms)

        logger.info(
            "[resolve_field_aliases] scope=%s resolved=%d ambiguous=%d unresolved=%d",
            scope_code,
            len(resolved),
            len(ambiguous),
            len(unresolved),
        )
        return FieldResolutionResult(
            resolved=resolved,
            ambiguous=ambiguous,
            unresolved=unresolved,
        )

    def resolve_value_aliases(
        self, *, terms: Sequence[str], scope_code: str
    ) -> ValueResolutionResult:
        """轻量级属性值精确消歧。

        在 scope_code 对应的 view/object 下，通过关系链路
        ``view/object → HAS_FIELD → prop → HAS_TERM → type_term → child(term_type_code)``
        查找值术语，并在 child term 的 ``term_name`` 和 ``TermName.name_text``（别名）
        中精确匹配输入 terms。

        Args:
            terms: 待匹配的值列表（如企业名、地区名等）。
            scope_code: 视图或对象 code（如 "scene_enterprise_analysis"）。

        Returns:
            ValueResolutionResult，包含 matched（已知值）和 unmatched（未知值）。
        """
        warnings.warn(
            "resolve_value_aliases() is deprecated: binds object/property domain "
            "concepts in the term protocol. Use query_terms + list_term_names instead.",
            FutureWarning,
            stacklevel=2,
        )
        terms_list = list(terms)
        if not terms_list or not scope_code:
            return ValueResolutionResult(unmatched=terms_list)

        unique_terms = list(dict.fromkeys(terms_list))
        global_scope: dict[str, str] = {"scope": "global"}

        view_obj = aliased(Term, name="view_obj")
        prop = aliased(Term, name="prop")
        type_term = aliased(Term, name="type_term")
        child = aliased(Term, name="child")
        has_field_rel = aliased(TermRelation, name="has_field")
        has_term_rel = aliased(TermRelation, name="has_term")

        try:
            with self._get_session() as session:
                # Step 1: 通过 child.term_name 直接匹配
                direct_rows = session.execute(
                    select(child.term_name)
                    .select_from(view_obj)
                    .join(
                        has_field_rel,
                        has_field_rel.source_term_id == view_obj.term_id,
                    )
                    .join(prop, prop.term_id == has_field_rel.target_term_id)
                    .join(
                        has_term_rel,
                        (has_term_rel.source_term_id == prop.term_id)
                        & (has_term_rel.relation_category == "HAS_TERM"),
                    )
                    .join(type_term, type_term.term_id == has_term_rel.target_term_id)
                    .join(child, child.term_type_code == type_term.term_code)
                    .where(
                        view_obj.term_code == scope_code,
                        view_obj.term_type_code.in_(["view", "object"]),
                        prop.term_type_code == "prop",
                        child.term_name.in_(unique_terms),
                    )
                ).all()
                direct_hits: set[str] = {str(row[0]) for row in direct_rows}

                # Step 2: 通过 TermName 别名匹配（仅对未命中的 terms）
                remaining = [t for t in unique_terms if t not in direct_hits]
                alias_hits: set[str] = set()

                if remaining:
                    alias_rows = session.execute(
                        select(TermName.name_text)
                        .select_from(view_obj)
                        .join(
                            has_field_rel,
                            has_field_rel.source_term_id == view_obj.term_id,
                        )
                        .join(prop, prop.term_id == has_field_rel.target_term_id)
                        .join(
                            has_term_rel,
                            (has_term_rel.source_term_id == prop.term_id)
                            & (has_term_rel.relation_category == "HAS_TERM"),
                        )
                        .join(type_term, type_term.term_id == has_term_rel.target_term_id)
                        .join(child, child.term_type_code == type_term.term_code)
                        .join(TermName, TermName.term_id == child.term_id)
                        .where(
                            view_obj.term_code == scope_code,
                            view_obj.term_type_code.in_(["view", "object"]),
                            prop.term_type_code == "prop",
                            TermName.name_text.in_(remaining),
                            or_(
                                TermName.search_scope.contains(global_scope),
                            ),
                        )
                    ).all()
                    alias_hits = {str(row[0]) for row in alias_rows}

        except Exception:
            logger.exception(
                "resolve_value_aliases failed: terms=%s, scope_code=%s",
                unique_terms,
                scope_code,
            )
            raise

        matched = direct_hits | alias_hits
        unmatched = [t for t in unique_terms if t not in matched]

        logger.info(
            "[resolve_value_aliases] scope=%s matched=%d unmatched=%d",
            scope_code,
            len(matched),
            len(unmatched),
        )
        return ValueResolutionResult(matched=matched, unmatched=unmatched)

    def get_object_props(self, *, source_term_ids: Sequence[str]) -> dict[str, list[PropItem]]:
        """批量查询对象/视图下的属性（通过 term_relation HAS_FIELD）。

        Args:
            source_term_ids: 源术语 ID 列表（view/object 的 term_id）。

        Returns:
            {source_term_id → [PropItem]} 映射。每个 source_term_id 至少包含一个空列表。
        """
        warnings.warn(
            "get_object_props() is deprecated: binds object/property domain concepts. Use query_term_relations instead.",
            FutureWarning,
            stacklevel=2,
        )
        source_term_ids_list = list(source_term_ids)
        if not source_term_ids_list:
            return {}

        try:
            with self._get_session() as session:
                rows = session.execute(
                    select(
                        TermRelation.source_term_id,
                        Term.term_id,
                        Term.term_code,
                        Term.term_name,
                    )
                    .join(Term, Term.term_id == TermRelation.target_term_id)
                    .where(
                        TermRelation.source_term_id.in_(source_term_ids_list),
                        Term.term_type_code == "prop",
                    )
                ).all()
        except Exception:
            logger.exception("get_object_props failed: source_term_ids=%s", source_term_ids_list)
            raise

        result: dict[str, list[PropItem]] = {
            source_term_id: [] for source_term_id in source_term_ids_list
        }
        for source_id, term_id, term_code, term_name in rows:
            result.setdefault(str(source_id), []).append(
                PropItem(term_id=str(term_id), term_code=str(term_code), term_name=str(term_name))
            )
        return result

    def get_object_props_by_code(self, *, scope_code: str) -> list[PropItem]:
        """根据对象 code 查询其所有属性。

        先通过 scope_code 查找 view/object 的 term_id，再查询 HAS_FIELD 关系获取属性列表。
        """
        warnings.warn(
            "get_object_props_by_code() is deprecated: binds object/property domain concepts. Use query_term_relations instead.",
            FutureWarning,
            stacklevel=2,
        )
        if not scope_code:
            return []

        with self._get_session() as session:
            source_row = session.execute(
                select(Term.term_id).where(
                    Term.term_code == scope_code,
                    Term.term_type_code.in_(["view", "object"]),
                )
            ).scalar_one_or_none()

            if source_row is None:
                logger.warning("[get_object_props_by_code] scope_code 未找到: %s", scope_code)
                return []

            source_term_id = str(source_row)

            try:
                rows = session.execute(
                    select(
                        TermRelation.source_term_id,
                        Term.term_id,
                        Term.term_code,
                        Term.term_name,
                    )
                    .join(Term, Term.term_id == TermRelation.target_term_id)
                    .where(
                        TermRelation.source_term_id == source_term_id,
                        Term.term_type_code == "prop",
                    )
                    .order_by(Term.term_code)
                ).all()
            except Exception:
                logger.exception("get_object_props_by_code failed: scope_code=%s", scope_code)
                raise

        return [
            PropItem(
                term_id=str(r.term_id),
                term_code=str(r.term_code),
                term_name=str(r.term_name),
            )
            for r in rows
        ]

    def get_prop_values_with_aliases(
        self, *, source_term_ids: Sequence[str]
    ) -> dict[str, list[ValueWithAliases]]:
        """批量查询对象下属性的值术语及其别名。

        路径: source → (HAS_FIELD) → prop → (HAS_TERM) → type_term → child(term_type_code)。

        Args:
            source_term_ids: 源术语 ID 列表。

        Returns:
            {source_term_id → [ValueWithAliases]} 映射。每个 source_term_id 至少包含一个空列表。
        """
        warnings.warn(
            "get_prop_values_with_aliases() is deprecated: binds property/value domain concepts. Use query_terms instead.",
            FutureWarning,
            stacklevel=2,
        )
        source_term_ids_list = list(source_term_ids)
        if not source_term_ids_list:
            return {}

        prop = aliased(Term, name="prop")
        type_term = aliased(Term, name="type_term")
        child = aliased(Term, name="child")
        has_term_rel = aliased(TermRelation, name="has_term")

        try:
            with self._get_session() as session:
                child_rows = session.execute(
                    select(
                        TermRelation.source_term_id,
                        prop.term_id,
                        child.term_id,
                        child.term_code,
                        child.term_name,
                    )
                    .join(prop, prop.term_id == TermRelation.target_term_id)
                    .join(
                        has_term_rel,
                        (has_term_rel.source_term_id == prop.term_id)
                        & (has_term_rel.relation_category == "HAS_TERM"),
                    )
                    .join(type_term, type_term.term_id == has_term_rel.target_term_id)
                    .join(child, child.term_type_code == type_term.term_code)
                    .where(
                        TermRelation.source_term_id.in_(source_term_ids_list),
                        prop.term_type_code == "prop",
                    )
                    .order_by(TermRelation.source_term_id, child.term_code)
                ).all()

                child_term_ids = list({str(row[2]) for row in child_rows})

                alias_rows: list[Any] = []
                if child_term_ids:
                    alias_rows = list(
                        session.execute(
                            select(TermName.term_id, TermName.name_text).where(
                                TermName.term_id.in_(child_term_ids)
                            )
                        ).all()
                    )
        except Exception:
            logger.exception(
                "get_prop_values_with_aliases failed: source_term_ids=%s", source_term_ids_list
            )
            raise

        alias_map: dict[str, list[str]] = {}
        for term_id, name_text in alias_rows:
            alias_map.setdefault(str(term_id), []).append(str(name_text))

        result: dict[str, list[ValueWithAliases]] = {
            source_term_id: [] for source_term_id in source_term_ids_list
        }
        for source_id, prop_term_id, term_id, term_code, term_name in child_rows:
            result.setdefault(str(source_id), []).append(
                ValueWithAliases(
                    parent_term_id=str(prop_term_id),
                    term_id=str(term_id),
                    term_code=str(term_code),
                    term_name=str(term_name),
                    aliases=alias_map.get(str(term_id), []),
                )
            )
        return result

    def get_prop_type_map(
        self,
        *,
        scope_code: str,
        field_codes: Sequence[str] | None = None,
    ) -> dict[str, str]:
        """查询 ontology 下 prop 的 HAS_TERM 绑定 type_code。

        路径: view/object(scope_code) → HAS_FIELD → prop → HAS_TERM → type_term。

        Args:
            scope_code: 视图或对象 code。
            field_codes: 可选，限定 prop 范围。None 时返回该 ontology 下所有 prop。

        Returns:
            {prop_code: type_code}，仅包含有 HAS_TERM 绑定的 prop。
        """
        warnings.warn(
            "get_prop_type_map() is deprecated: property-type mapping is entity-specific. Use list_term_types instead.",
            FutureWarning,
            stacklevel=2,
        )
        if not scope_code:
            return {}

        field_codes_list = list(field_codes) if field_codes else []
        unique_codes = list(dict.fromkeys(field_codes_list)) if field_codes_list else None

        view_obj = aliased(Term, name="view_obj_ptm")
        prop = aliased(Term, name="prop_ptm")
        type_term = aliased(Term, name="type_term_ptm")
        has_field_rel = aliased(TermRelation, name="has_field_ptm")
        has_term_rel = aliased(TermRelation, name="has_term_ptm")

        try:
            with self._get_session() as session:
                stmt = (
                    select(
                        prop.term_code.label("field_code"),
                        type_term.term_code.label("type_code"),
                    )
                    .select_from(view_obj)
                    .join(
                        has_field_rel,
                        has_field_rel.source_term_id == view_obj.term_id,
                    )
                    .join(prop, prop.term_id == has_field_rel.target_term_id)
                    .join(
                        has_term_rel,
                        (has_term_rel.source_term_id == prop.term_id)
                        & (has_term_rel.relation_category == "HAS_TERM"),
                    )
                    .join(type_term, type_term.term_id == has_term_rel.target_term_id)
                    .where(
                        view_obj.term_code == scope_code,
                        view_obj.term_type_code.in_(["view", "object"]),
                        prop.term_type_code == "prop",
                    )
                )
                if unique_codes:
                    stmt = stmt.where(prop.term_code.in_(unique_codes))

                rows = session.execute(stmt).all()
        except Exception:
            logger.exception(
                "get_prop_type_map failed: scope_code=%s, field_codes=%s",
                scope_code,
                unique_codes,
            )
            raise

        result: dict[str, str] = {}
        for field_code, type_code in rows:
            result[str(field_code)] = str(type_code)
        return result

    def get_prop_enum_values(
        self, *, scope_code: str, field_codes: Sequence[str]
    ) -> dict[str, list[str]]:
        """查询指定 prop 的枚举值（child term_name + 别名）。

        路径: view/object(scope_code) → HAS_FIELD → prop → HAS_TERM → type_term
              → children(term_type_code = type_term.term_code)。

        Args:
            scope_code: 视图或对象 code。
            field_codes: 待查询的 prop term_code 列表。

        Returns:
            {field_code → [枚举值列表]}，去重保序。未命中 field_code 的值为空列表。
        """
        warnings.warn(
            "get_prop_enum_values() is deprecated: binds property/enum domain concepts. Use query_terms(parent_term_code=...) instead.",
            FutureWarning,
            stacklevel=2,
        )
        field_codes_list = list(field_codes)
        if not scope_code or not field_codes_list:
            return {}

        unique_codes = list(dict.fromkeys(field_codes_list))

        child = aliased(Term, name="child")

        try:
            with self._get_session() as session:
                # Step 1: 复用 get_prop_type_map 查 prop → type_code
                prop_type_map = self.get_prop_type_map(
                    scope_code=scope_code,
                    field_codes=unique_codes,
                )
                type_to_fields: dict[str, list[str]] = {}
                for fc, tc in prop_type_map.items():
                    type_to_fields.setdefault(tc, []).append(fc)

                # Step 2: 查找所有属于这些 type_code 的 child value terms
                result_raw: dict[str, list[str]] = {code: [] for code in unique_codes}
                child_to_field: dict[str, str] = {}

                type_codes = list(type_to_fields.keys())
                if type_codes:
                    value_rows = session.execute(
                        select(
                            child.term_type_code.label("type_code"),
                            child.term_name.label("value_name"),
                            child.term_id.label("child_id"),
                        ).where(child.term_type_code.in_(type_codes))
                    ).all()

                    for type_code, value_name, child_id in value_rows:
                        tc = str(type_code)
                        for fc in type_to_fields.get(tc, []):
                            result_raw.setdefault(fc, []).append(str(value_name))
                            child_to_field[str(child_id)] = fc

                # 查询 child 的 TermName 别名
                child_ids = list(child_to_field.keys())
                if child_ids:
                    alias_rows = session.execute(
                        select(TermName.term_id, TermName.name_text).where(
                            TermName.term_id.in_(child_ids)
                        )
                    ).all()
                    for term_id, name_text in alias_rows:
                        fc_alias = child_to_field.get(str(term_id))
                        if fc_alias:
                            result_raw.setdefault(fc_alias, []).append(str(name_text))

        except Exception:
            logger.exception(
                "get_prop_enum_values failed: scope_code=%s, field_codes=%s",
                scope_code,
                unique_codes,
            )
            raise

        # 去重保序
        result: dict[str, list[str]] = {}
        for code in unique_codes:
            seen: set[str] = set()
            deduped: list[str] = []
            for val in result_raw.get(code, []):
                if val and val not in seen:
                    seen.add(val)
                    deduped.append(val)
            result[code] = deduped

        logger.info(
            "[get_prop_enum_values] scope=%s codes=%s counts=%s",
            scope_code,
            unique_codes,
            {c: len(v) for c, v in result.items()},
        )
        return result

    def get_bfs_distance(
        self,
        *,
        source_term_id: str,
        target_term_id: str,
        max_depth: int = 4,
    ) -> int | None:
        """计算两个术语在图谱中的 BFS 最短距离。

        通过 ``term_relation`` 表递归 CTE 搜索，相同节点返回 0。

        Args:
            source_term_id: 源术语 ID。
            target_term_id: 目标术语 ID。
            max_depth: 最大搜索深度。

        Returns:
            最短距离，不可达时返回 None。
        """
        warnings.warn(
            "get_bfs_distance() is deprecated: graph traversal in reader protocol. Use query_term_relations(depth=...) instead.",
            FutureWarning,
            stacklevel=2,
        )
        if source_term_id == target_term_id:
            return 0
        if max_depth <= 0:
            return None

        try:
            with self._get_session() as session:
                row = session.execute(
                    text(
                        """
                        WITH RECURSIVE bfs AS (
                            SELECT
                                CAST(:source_id AS varchar) AS current_id,
                                0 AS depth,
                                ARRAY[CAST(:source_id AS varchar)]::varchar[] AS path
                            UNION ALL
                            SELECT
                                CASE
                                    WHEN tr.source_term_id = b.current_id THEN tr.target_term_id
                                    ELSE tr.source_term_id
                                END,
                                b.depth + 1,
                                b.path || CASE
                                    WHEN tr.source_term_id = b.current_id THEN tr.target_term_id
                                    ELSE tr.source_term_id
                                END
                            FROM bfs b
                            JOIN term_relation tr
                                ON tr.source_term_id = b.current_id
                                OR tr.target_term_id = b.current_id
                            WHERE b.depth < :max_depth
                              AND NOT (
                                    CASE
                                        WHEN tr.source_term_id = b.current_id
                                        THEN tr.target_term_id
                                        ELSE tr.source_term_id
                                    END
                                ) = ANY(b.path)
                        )
                        SELECT depth FROM bfs
                        WHERE current_id = :target_id
                        ORDER BY depth LIMIT 1
                        """
                    ),
                    {
                        "source_id": source_term_id,
                        "target_id": target_term_id,
                        "max_depth": max_depth,
                    },
                ).fetchone()
        except Exception:
            logger.exception(
                "get_bfs_distance failed: source=%s target=%s max_depth=%s",
                source_term_id,
                target_term_id,
                max_depth,
            )
            raise

        return int(row[0]) if row is not None else None

    def get_shortest_path_tree(
        self,
        *,
        target_term_id: str,
        source_term_type_codes: Sequence[str],
        max_depth: int = 6,
    ) -> Sequence[ShortestPathNode]:
        """查询从限定类型根节点到目标术语的最短路径树。

        通过递归 CTE 从 *target_term_id* 向上遍历 ``term_relation`` 表，
        找到 ``term_type_code IN source_term_type_codes`` 中深度最小的
        候选根节点，返回完整路径信息。

        Args:
            target_term_id: 目标术语 ID（消歧候选项）。
            source_term_type_codes: 限定根节点的术语类型编码列表。
            max_depth: 最大搜索深度。

        Returns:
            ShortestPathNode 列表，每个节点代表一条从根到目标的完整路径。
            无满足条件的根节点时返回空列表。
        """
        warnings.warn(
            "get_shortest_path_tree() is deprecated: graph traversal in reader protocol. Use query_term_relations instead.",
            FutureWarning,
            stacklevel=2,
        )
        if not target_term_id.strip():
            raise ValueError("target_term_id must not be blank")
        if not source_term_type_codes:
            raise ValueError("source_term_type_codes must not be empty")
        if max_depth <= 0:
            raise ValueError("max_depth must be positive")

        sql = text(
            """
            WITH RECURSIVE upward AS (
                SELECT
                    t.term_id,
                    t.term_name,
                    t.term_type_code,
                    t.desc_summary AS term_desc_summary,
                    (
                        SELECT COALESCE(NULLIF(k.desc_summary, ''), NULLIF(k."desc", ''))
                        FROM term_knowledge k
                        WHERE k.term_id = t.term_id
                        ORDER BY k.knowledge_id
                        LIMIT 1
                    ) AS description,
                    0 AS depth,
                    ARRAY[t.term_id]::text[] AS path_term_ids,
                    ARRAY[t.term_name]::text[] AS path_term_names,
                    ARRAY[t.term_type_code]::text[] AS path_term_type_codes,
                    ARRAY[COALESCE(t.desc_summary, '')]::text[] AS path_term_desc_summaries,
                    ARRAY[
                        COALESCE(
                            (
                                SELECT COALESCE(NULLIF(k.desc_summary, ''), NULLIF(k."desc", ''))
                                FROM term_knowledge k
                                WHERE k.term_id = t.term_id
                                ORDER BY k.knowledge_id
                                LIMIT 1
                            ),
                            ''
                        )
                    ]::text[] AS path_descriptions,
                    ARRAY[]::text[] AS path_relations,
                    ARRAY[t.term_id]::text[] AS visited_ids
                FROM term t
                WHERE t.term_id = :target_term_id

                UNION ALL

                SELECT
                    parent.term_id,
                    parent.term_name,
                    parent.term_type_code,
                    parent.desc_summary AS term_desc_summary,
                    (
                        SELECT COALESCE(NULLIF(k.desc_summary, ''), NULLIF(k."desc", ''))
                        FROM term_knowledge k
                        WHERE k.term_id = parent.term_id
                        ORDER BY k.knowledge_id
                        LIMIT 1
                    ) AS description,
                    upward.depth + 1 AS depth,
                    ARRAY[parent.term_id]::text[] || upward.path_term_ids,
                    ARRAY[parent.term_name]::text[] || upward.path_term_names,
                    ARRAY[parent.term_type_code]::text[] || upward.path_term_type_codes,
                    ARRAY[COALESCE(parent.desc_summary, '')]::text[] || upward.path_term_desc_summaries,
                    ARRAY[
                        COALESCE(
                            (
                                SELECT COALESCE(NULLIF(k.desc_summary, ''), NULLIF(k."desc", ''))
                                FROM term_knowledge k
                                WHERE k.term_id = parent.term_id
                                ORDER BY k.knowledge_id
                                LIMIT 1
                            ),
                            ''
                        )
                    ]::text[] || upward.path_descriptions,
                    ARRAY[tr.relation_name]::text[] || upward.path_relations,
                    upward.visited_ids || ARRAY[parent.term_id]::text[]
                FROM upward
                JOIN term_relation tr ON tr.target_term_id = upward.term_id
                JOIN term parent ON parent.term_id = tr.source_term_id
                WHERE upward.depth < :max_depth
                  AND NOT parent.term_id = ANY(upward.visited_ids)
            ),
            candidate_roots AS (
                SELECT *
                FROM upward
                WHERE term_type_code IN :source_term_type_codes
            ),
            min_depth AS (
                SELECT MIN(depth) AS depth FROM candidate_roots
            )
            SELECT
                term_id,
                term_name,
                term_type_code,
                description,
                depth,
                path_term_ids,
                path_term_names,
                path_term_type_codes,
                path_term_desc_summaries,
                path_descriptions,
                path_relations
            FROM candidate_roots
            WHERE depth = (SELECT depth FROM min_depth)
            ORDER BY term_name, term_id, path_term_ids
            """
        ).bindparams(bindparam("source_term_type_codes", expanding=True))

        try:
            with self._get_session() as session:
                rows = session.execute(
                    sql,
                    {
                        "target_term_id": target_term_id,
                        "source_term_type_codes": list(source_term_type_codes),
                        "max_depth": max_depth,
                    },
                ).fetchall()
        except Exception:
            logger.exception(
                "get_shortest_path_tree failed: target=%s types=%s max_depth=%s",
                target_term_id,
                source_term_type_codes,
                max_depth,
            )
            raise

        return tuple(
            ShortestPathNode(
                term_id=str(row.term_id),
                term_name=str(row.term_name),
                term_type_code=str(row.term_type_code),
                description=str(row.description) if row.description is not None else None,
                depth=int(row.depth),
                path_term_ids=[str(v) for v in row.path_term_ids],
                path_term_names=[str(v) for v in row.path_term_names],
                path_term_type_codes=[str(v) for v in row.path_term_type_codes],
                path_term_desc_summaries=[
                    str(v) if v is not None else "" for v in row.path_term_desc_summaries
                ],
                path_descriptions=[str(v) if v is not None else "" for v in row.path_descriptions],
                path_relations=[str(v) for v in row.path_relations],
            )
            for row in rows
        )

    def get_dimension_values(self) -> Sequence[DimensionValueItem]:
        """查询所有 cat=2 维度枚举值（全量加载到内存）。"""
        warnings.warn(
            "get_dimension_values() is deprecated: binds dimension domain concept. Use query_terms instead.",
            FutureWarning,
            stacklevel=2,
        )
        try:
            with self._get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT t.term_name, tt.type_name "
                        "FROM term t "
                        "JOIN term_type tt ON t.term_type_code = tt.type_code "
                        "WHERE tt.type_category = 2 "
                        "ORDER BY t.term_name"
                    )
                ).fetchall()
        except Exception:
            logger.exception("get_dimension_values failed")
            raise

        return tuple(
            DimensionValueItem(term_name=str(r.term_name), type_name=str(r.type_name)) for r in rows
        )

    def get_user_scoped_names(self, *, user_id: str) -> Sequence[UserScopedNameItem]:
        """查询指定用户作用域下的术语别名记录。"""
        warnings.warn(
            "get_user_scoped_names() is deprecated: user-scoped query in reader protocol. Use list_term_names + scope filter instead.",
            FutureWarning,
            stacklevel=2,
        )
        try:
            with self._get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT tn.name_text, t.term_id, t.term_type_code, tn.search_scope "
                        "FROM term_name tn "
                        "JOIN term t ON tn.term_id = t.term_id "
                        "WHERE tn.search_scope->>'scope_user_id' = :user_id"
                    ),
                    {"user_id": user_id},
                ).fetchall()
        except Exception:
            logger.exception("get_user_scoped_names failed: user_id=%s", user_id)
            raise

        return tuple(
            UserScopedNameItem(
                name_text=str(r.name_text),
                term_id=str(r.term_id),
                term_type_code=str(r.term_type_code),
                search_scope=dict(r.search_scope) if r.search_scope is not None else {},
            )
            for r in rows
        )

    def get_scope_term_ids(self, *, scope_code: str) -> Sequence[str]:
        """根据 scope_code 查询 view/object term_id。"""
        try:
            with self._get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT term_id FROM term "
                        "WHERE term_code = :scope_code "
                        "AND term_type_code IN ('view', 'object')"
                    ),
                    {"scope_code": scope_code},
                ).fetchall()
        except Exception:
            logger.exception("get_scope_term_ids failed: scope_code=%s", scope_code)
            raise
        return tuple(str(r.term_id) for r in rows)

    def get_type_codes_by_category(self, *, categories: set[int]) -> set[str]:
        """按 term_type 的 type_category 加载 type_code 集合。"""
        warnings.warn(
            "get_type_codes_by_category() is deprecated: exposes internal type_category concept. Use list_term_types instead.",
            FutureWarning,
            stacklevel=2,
        )
        if not categories:
            return set()
        try:
            with self._get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT type_code FROM term_type WHERE type_category IN :categories"
                    ).bindparams(bindparam("categories", expanding=True)),
                    {"categories": tuple(sorted(categories))},
                ).fetchall()
        except Exception:
            logger.exception("get_type_codes_by_category failed: categories=%s", categories)
            raise
        return {str(r.type_code) for r in rows}

    def get_term_codes_by_names(
        self, *, terms: Sequence[str], scope_code: str | None = None
    ) -> dict[str, str]:
        """Look up ``term_code`` by ``term_name`` for a batch of terms.

        Used as a fallback when field-alias resolution cannot resolve a Chinese
        display name (e.g., "回款金额") — queries the term table directly by
        ``term_name`` and returns ``{term_name: term_code}`` mappings.

        ``scope_code`` is accepted for call-site compatibility but NOT used as
        a filter: ``term_code`` is globally unique per term, and restricting by
        scope would miss valid mappings (e.g., "回款金额" is a standalone prop
        not linked to any specific object). The caller is responsible for
        validating the returned codes against the ontology if needed.
        """
        if not terms:
            return {}
        unique_terms = list(dict.fromkeys(terms))
        mapping: dict[str, str] = {}
        try:
            with self._get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT term_name, term_code FROM term "
                        "WHERE term_name IN :terms AND term_type_code = 'prop'"
                    ).bindparams(bindparam("terms", expanding=True)),
                    {"terms": tuple(unique_terms)},
                ).fetchall()
        except Exception:
            logger.exception("get_term_codes_by_names failed: terms=%s", terms)
            raise
        for term_name, term_code in rows:
            mapping[str(term_name)] = str(term_code)
        return mapping

    def get_matching_objects(
        self,
        *,
        ontology_code: str,
        field_codes: Sequence[str],
        limit: int = 2,
    ) -> Sequence[tuple[str, int]]:
        """查询与指定字段集最佳匹配的对象 term_code。"""
        warnings.warn(
            "get_matching_objects() is deprecated: binds object/field/ontology domain concepts. Use query_term_relations + application logic instead.",
            FutureWarning,
            stacklevel=2,
        )
        if not field_codes:
            return ()
        try:
            with self._get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT obj.term_code, COUNT(prop.term_id) AS matched_count "
                        "FROM term AS view "
                        "JOIN term_relation AS vor ON vor.source_term_id = view.term_id "
                        "JOIN term AS obj ON obj.term_id = vor.target_term_id "
                        "JOIN term_relation AS opr ON opr.source_term_id = obj.term_id "
                        "JOIN term AS prop ON prop.term_id = opr.target_term_id "
                        "WHERE view.term_code = :ontology_code "
                        "AND view.term_type_code IN ('view', 'object') "
                        "AND obj.term_type_code = 'object' "
                        "AND prop.term_type_code = 'prop' "
                        "AND prop.term_code IN :field_codes "
                        "GROUP BY obj.term_code "
                        "ORDER BY matched_count DESC "
                        "LIMIT :limit"
                    ).bindparams(bindparam("field_codes", expanding=True)),
                    {
                        "ontology_code": ontology_code,
                        "field_codes": tuple(field_codes),
                        "limit": limit,
                    },
                ).fetchall()
        except Exception:
            logger.exception(
                "get_matching_objects failed: ontology=%s fields=%s",
                ontology_code,
                field_codes,
            )
            raise
        return tuple((str(r.term_code), int(r.matched_count)) for r in rows)

    def get_relation_target_ids(
        self,
        *,
        source_term_ids: Sequence[str] | None = None,
        target_term_ids: Sequence[str] | None = None,
        relation_category: str | None = None,
    ) -> Sequence[str]:
        """查询术语关系的目标/源术语 ID（distinct）。

        正向查询（source→target）：传入 source_term_ids，返回 target_term_ids。
        反向查询（target→source）：传入 target_term_ids，返回 source_term_ids。
        可选 relation_category 过滤。
        """
        if source_term_ids is not None and target_term_ids is not None:
            raise ValueError("source_term_ids 和 target_term_ids 不能同时指定")
        if source_term_ids is not None:
            ids = tuple(source_term_ids)
            if not ids:
                return ()
            select_col = "target_term_id"
            where_col = "source_term_id"
        elif target_term_ids is not None:
            ids = tuple(target_term_ids)
            if not ids:
                return ()
            select_col = "source_term_id"
            where_col = "target_term_id"
        else:
            return ()
        try:
            with self._get_session() as session:
                where_clause = f"{where_col} IN :ids"
                params: dict[str, object] = {"ids": ids}
                if relation_category:
                    where_clause += " AND relation_category = :cat"
                    params["cat"] = relation_category
                rows = session.execute(
                    text(
                        f"SELECT DISTINCT {select_col} FROM term_relation WHERE {where_clause}"
                    ).bindparams(bindparam("ids", expanding=True)),
                    params,
                ).fetchall()
        except Exception:
            logger.exception(
                "get_relation_target_ids failed: source_ids=%s target_ids=%s category=%s",
                source_term_ids,
                target_term_ids,
                relation_category,
            )
            raise
        return tuple(str(r[0]) for r in rows)

    def get_terms_batch_raw(
        self,
        *,
        term_ids: Sequence[str] | None = None,
        term_codes: Sequence[str] | None = None,
    ) -> Sequence[dict[str, object]]:
        """批量查询术语的基本字段（term_id, term_code, term_name, term_type_code, parent_term_id, domain_ids）。

        支持按 term_ids 或 term_codes 查询。
        """
        if term_ids is not None and term_codes is not None:
            raise ValueError("term_ids 和 term_codes 不能同时指定")
        if term_ids is not None:
            ids = tuple(term_ids)
            if not ids:
                return ()
            where_col = "term_id"
        elif term_codes is not None:
            ids = tuple(term_codes)
            if not ids:
                return ()
            where_col = "term_code"
        else:
            return ()
        try:
            with self._get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT term_id, term_code, term_name, term_type_code, "
                        "parent_term_id, domain_ids "
                        f"FROM term WHERE {where_col} IN :ids"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"ids": ids},
                ).fetchall()
        except Exception:
            logger.exception(
                "get_terms_batch_raw failed: term_ids=%s term_codes=%s",
                term_ids,
                term_codes,
            )
            raise
        return tuple(
            {
                "term_id": str(r.term_id),
                "term_code": str(r.term_code),
                "term_name": str(r.term_name),
                "term_type_code": str(r.term_type_code),
                "parent_term_id": None if r.parent_term_id is None else str(r.parent_term_id),
                "domain_ids": list(r.domain_ids) if r.domain_ids else [],
            }
            for r in rows
        )

    def get_global_name_index(
        self,
    ) -> dict[str, list[tuple[str, str, str]]]:
        """构建全局术语名称索引（公共 term_name，不含用户专属记录）。

        Returns:
            {name_text → [(term_id, term_type_code, match_type), ...]} 索引。
        """
        try:
            with self._get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT t.term_id, t.term_type_code, tn.name_text, "
                        "CASE WHEN tn.name_text = t.term_name "
                        "THEN 'standard_name' ELSE 'alias' END AS match_type "
                        "FROM term_name tn "
                        "JOIN term t ON tn.term_id = t.term_id "
                        "WHERE tn.search_scope = '{}'::jsonb "
                        "OR COALESCE((tn.search_scope->>'scope_user_id'), '') = ''"
                    )
                ).fetchall()
        except Exception:
            logger.exception("get_global_name_index failed")
            raise
        index: dict[str, list[tuple[str, str, str]]] = {}
        for term_id, term_type_code, name_text, match_type in rows:
            index.setdefault(str(name_text), []).append(
                (str(term_id), str(term_type_code), str(match_type))
            )
        return index

    def get_name_ids_by_word(
        self,
        *,
        word: str,
        term_ids: Sequence[str],
        user_id: str | None = None,
    ) -> dict[str, str]:
        """按单词+术语ID查询 name_id，用户专属记录优先。

        Returns:
            {term_id → name_id} 映射。
        """
        if not term_ids:
            return {}
        if user_id:
            sql_str = (
                "SELECT tn.term_id, tn.name_id FROM term_name tn "
                "WHERE tn.name_text = :name_text "
                "AND tn.term_id IN :term_ids "
                "AND (tn.search_scope = '{}'::jsonb "
                "OR COALESCE((tn.search_scope->>'scope_user_id'), '') = '' "
                "OR COALESCE((tn.search_scope->>'scope_user_id'), '') = :user_id) "
                "ORDER BY CASE WHEN COALESCE((tn.search_scope->>'scope_user_id'), '') = :user_id "
                "THEN 0 ELSE 1 END, tn.updated_time DESC"
            )
            params = {"name_text": word, "term_ids": tuple(term_ids), "user_id": user_id}
        else:
            sql_str = (
                "SELECT tn.term_id, tn.name_id FROM term_name tn "
                "WHERE tn.name_text = :name_text "
                "AND tn.term_id IN :term_ids "
                "AND (tn.search_scope = '{}'::jsonb "
                "OR COALESCE((tn.search_scope->>'scope_user_id'), '') = '') "
                "ORDER BY tn.updated_time DESC"
            )
            params = {"name_text": word, "term_ids": tuple(term_ids)}
        try:
            with self._get_session() as session:
                rows = session.execute(
                    text(sql_str).bindparams(bindparam("term_ids", expanding=True)),
                    params,
                ).fetchall()
        except Exception:
            logger.exception("get_name_ids_by_word failed: word=%s", word)
            raise
        mapping: dict[str, str] = {}
        for term_id, name_id in rows:
            tid = str(term_id)
            if tid not in mapping:
                mapping[tid] = str(name_id)
        return mapping

    def get_term(
        self,
        *,
        term_code: str,
        term_type_code: str,
        library_id: str | None = None,
    ) -> str | None:
        """根据 term_code + term_type_code 查询 term_name。

        优先通过 get_term_by_ids 获取 term_id，再用 get_term_names 获取名称。
        返回标准名（is_primary=True）或第一个可用名称，不存在则返回 None。

        Args:
            term_code: 术语编码。
            term_type_code: 术语类型编码。
            library_id: 可选术语库 ID，传入时走 get_term_by_ids 精确匹配；
                None 时不按 library 过滤。

        Returns:
            术语名称字符串，不存在时返回 None。
        """
        if library_id is not None:
            id_map = self.get_term_by_ids(keys=[(library_id, term_type_code, term_code)])
            if not id_map:
                return None
            term_id = next(iter(id_map.values()))
        else:
            try:
                with self._get_session() as session:
                    row = session.execute(
                        select(Term.term_id)
                        .where(
                            Term.term_code == term_code,
                            Term.term_type_code == term_type_code,
                        )
                        .limit(1)
                    ).one_or_none()
            except Exception:
                logger.exception(
                    "get_term failed: term_code=%s term_type_code=%s",
                    term_code,
                    term_type_code,
                )
                raise
            if row is None:
                return None
            term_id = str(row[0])

        names = self.get_term_names(term_ids=[term_id])
        name_list = names.get(term_id, [])
        if not name_list:
            return None
        for name_item in name_list:
            if name_item.is_primary:
                return name_item.name_text
        return name_list[0].name_text

    def term_exists(
        self,
        *,
        term_code: str,
        term_type_code: str,
        library_id: str | None = None,
    ) -> bool:
        """检查指定 term_code + term_type_code 的术语是否存在。

        优先通过 get_term_by_ids 判空。

        Args:
            term_code: 术语编码。
            term_type_code: 术语类型编码。
            library_id: 可选术语库 ID，传入时走 get_term_by_ids 精确匹配；
                None 时不按 library 过滤。

        Returns:
            True 如果存在，否则 False。
        """
        if library_id is not None:
            id_map = self.get_term_by_ids(keys=[(library_id, term_type_code, term_code)])
            return len(id_map) > 0

        try:
            with self._get_session() as session:
                row = session.execute(
                    select(text("1"))
                    .select_from(Term)
                    .where(
                        Term.term_code == term_code,
                        Term.term_type_code == term_type_code,
                    )
                    .limit(1)
                ).one_or_none()
        except Exception:
            logger.exception(
                "term_exists failed: term_code=%s term_type_code=%s",
                term_code,
                term_type_code,
            )
            raise
        return row is not None

    # ── TermProvider 协议新增方法 ──────────────────────────────────────

    def query_terms(
        self,
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
        """检索术语（OpenGauss 实现）。

        根据 query_type 选择检索策略：
        - exact:     TermName.name_text 精确匹配 + Term.term_code 精确匹配
        - fulltext:  BM25 单字 OR + jieba 分词 RRF（仅 CJK）→ rrf_fuse(k=60)
        - embedding: name_embedding <=> CAST(:vector AS vector)，需 query_vector
        - mixed:     BM25 + jieba + vector → rrf_fuse 三路(k=60)

        Args:
            dataset_ids: 术语库 ID 列表。
            keyword: 搜索关键词（用于 fulltext/embedding/mixed）。
            term_name: 精确名称匹配（走 exact 路径）。
            term_type: 术语类型编码（支持驼峰简写）。
            query_type: 检索策略（exact/fulltext/embedding/mixed）。
            parent_term_code: 父术语 ID 过滤。
            label_filters: 标签过滤条件列表。
            label_condition: 标签组合条件（and/or）。
            term_ids: 精确 term_id 列表（走精确 ID 路径）。
            ext_attrs: 扩展属性键值过滤。
            query_vector: 查询向量（仅 embedding/mixed 需要）。
            top_k: 返回条数。
            offset: 分页偏移。

        Returns:
            分页检索结果。
        """
        try:
            with self._get_session() as session:
                canonical_type = self._normalize_type_code(term_type) if term_type else None
                # ── Step 1: 候选 term_ids + score_map ──────────────
                candidate_ids: set[str] | None = None
                score_map: dict[str, float] = {}

                if term_ids:
                    # 精确 term_id 路径，跳过文本搜索
                    candidate_ids = set(term_ids)
                    score_map = dict.fromkeys(term_ids, 1.0)
                elif term_name:
                    # term_name 精确匹配（exact 语义）
                    candidate_ids, score_map = self._text_search_candidates(
                        session,
                        keyword=term_name,
                        query_type="exact",
                        top_k=top_k + offset,
                    )

                kw = (keyword or "").strip()
                if kw:
                    # Determine effective query_type
                    effective_qtype: QueryType = query_type

                    # term_name 不存在 keyword 时 embedding/empty/mixed 回退
                    if query_type == "embedding" and query_vector is None:
                        logger.warning(
                            "embedding query_type requires query_vector — returning empty"
                        )
                        return QueryResult(total=0, items=[])
                    if query_type == "mixed" and query_vector is None:
                        logger.info("mixed query_type without query_vector — degrading to fulltext")
                        effective_qtype = "fulltext"

                    search_ids, search_scores = self._text_search_candidates(
                        session,
                        keyword=kw,
                        query_type=effective_qtype,
                        query_vector=query_vector,
                        top_k=top_k + offset,
                        label_filters=label_filters,
                        term_type=canonical_type,
                    )

                    if candidate_ids is not None:
                        # Intersect with existing candidate_ids (from term_ids or term_name)
                        candidate_ids = candidate_ids & search_ids
                    else:
                        candidate_ids = search_ids
                    score_map = {tid: search_scores.get(tid, 1.0) for tid in candidate_ids}

                # No text search at all — use empty result
                if candidate_ids is None:
                    return QueryResult(total=0, items=[])

                # ── Step 2: 元数据过滤 ─────────────────────────────
                filters = self._apply_metadata_filters(
                    candidate_ids=candidate_ids,
                    term_type_codes=[canonical_type] if canonical_type else None,
                    dataset_ids=dataset_ids,
                    parent_term_code=parent_term_code,
                    ext_attrs=ext_attrs,
                    label_filters=label_filters,
                    label_condition=label_condition,
                )

                where_clause = and_(*filters)

                # ── Step 3: 计数 ────────────────────────────────────
                total = int(
                    session.execute(
                        select(func.count()).select_from(Term).where(where_clause)
                    ).scalar_one()
                )
                if total == 0:
                    return QueryResult(total=0, items=[])

                # ── Step 4: 详情查询 + 响应构造 ──────────────────────
                rows = session.execute(
                    select(
                        Term.term_id,
                        Term.term_code,
                        Term.term_name,
                        Term.term_type_code,
                        Term.library_id,
                        Term.parent_term_id,
                        Term.desc_summary,
                        Term.term_tags,
                        Term.ext_attrs,
                        Term.created_time,
                        Term.updated_time,
                    )
                    .where(where_clause)
                    .limit(top_k)
                    .offset(offset)
                    .order_by(Term.updated_time.desc())
                ).all()
        except Exception:
            logger.exception(
                "query_terms failed: keyword=%s term_type=%s query_type=%s",
                keyword,
                term_type,
                query_type,
            )
            raise

        items: list[ProviderTermItem] = []
        for row in rows:
            tags: dict[str, str] = {}
            raw_tags = row[7]
            if isinstance(raw_tags, dict):
                tags = {str(k): str(v) for k, v in raw_tags.items()}
            term_ext_attrs: dict[str, str] = {}
            raw_ext_attrs = row[8]
            if isinstance(raw_ext_attrs, dict):
                term_ext_attrs = {str(k): str(v) for k, v in raw_ext_attrs.items()}

            items.append(
                ProviderTermItem(
                    term_id=str(row[0]),
                    term_code=str(row[1]),
                    term_name=str(row[2]),
                    term_type=str(row[3]),
                    dataset_id=str(row[4]) if row[4] else "",
                    parent_term_code=str(row[5]) if row[5] else "",
                    desc=str(row[6]) if row[6] else "",
                    labels=tags,
                    synonyms="",
                    ext_attrs=term_ext_attrs,
                    created_time=self._datetime_to_epoch(row[9]),
                    updated_time=self._datetime_to_epoch(row[10]),
                    score=score_map.get(str(row[0])),
                )
            )
        return QueryResult(total=total, items=items)

    def query_terms_batch(
        self,
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
        """批量检索术语 — BM25 / jieba / vector 三路 UNION ALL + per-kw RRF。

        Args:
            keywords: 搜索关键词列表。
            dataset_ids: 术语库 ID 列表。
            term_type_codes: 术语类型编码列表（IN 过滤）。None=不限，[]=空结果。
            query_type: 检索策略（exact/fulltext/embedding/mixed）。
            parent_term_code: 父术语 ID 过滤。
            label_filters: 标签过滤条件列表。
            label_condition: 标签组合条件（and/or）。
            ext_attrs: 扩展属性键值过滤。
            query_vectors: 查询向量列表（仅 embedding/mixed 需要，长度与 keywords 一致）。
            top_k: 返回条数。
            offset: 分页偏移。

        Returns:
            list[QueryResult]，与 keywords 一一对应。
        """
        if not keywords:
            return []

        # Empty term_type_codes list → no results
        if term_type_codes is not None and not term_type_codes:
            return [QueryResult(total=0, items=[])] * len(keywords)

        from datacloud_knowledge.adapters.opengauss.bm25 import (
            _build_char_tsquery,
            _has_name_keywords_column,
        )

        _ = _has_name_keywords_column  # referenced in batch helpers

        # ── Resolve effective query type ──────────────────────────
        if query_type in ("embedding", "mixed"):
            if query_vectors is None:
                if query_type == "embedding":
                    logger.warning(
                        "embedding batch requires query_vectors — returning empty results"
                    )
                    return [QueryResult(total=0, items=[])] * len(keywords)
                logger.info("mixed batch without query_vectors — degrading to fulltext")
                effective_type: QueryType = "fulltext"
            elif len(query_vectors) != len(keywords):
                raise ValueError(
                    f"query_vectors length ({len(query_vectors)}) must match "
                    f"keywords length ({len(keywords)})"
                )
            else:
                effective_type = query_type
        else:
            effective_type = query_type
            query_vectors = None

        canonical_types: list[str] | None = None
        if term_type_codes is not None:
            canonical_types = [self._normalize_type_code(t) for t in term_type_codes]
        n = len(keywords)

        # ── Build empty results array ────────────────────────────
        results: list[QueryResult | None] = [None] * n

        # ── Identify active keywords (non-empty after strip) ─────
        active: list[tuple[int, str]] = [
            (i, kw) for i, kw in enumerate(keywords) if (kw or "").strip()
        ]

        # ── Pre-compute tsqueries for BM25 ───────────────────────
        tsquery_map: dict[int, str] = {}
        has_bm25 = effective_type in ("fulltext", "mixed")
        if has_bm25:
            for i, kw in active:
                tsq = _build_char_tsquery(kw, ts_operator="|")
                if tsq:
                    tsquery_map[i] = tsq

        # ── Pre-compute jieba tokens for CJK keywords ────────────
        jieba_tokens_map: dict[int, list[str]] = {}
        if has_bm25:
            import jieba

            for i, kw in active:
                if self._has_cjk(kw):
                    tokens = [t for t in jieba.lcut(kw) if len(t.strip()) > 0]
                    if tokens:
                        jieba_tokens_map[i] = tokens

        # ── Pre-compute vector map ───────────────────────────────
        vec_map: dict[int, list[float]] = {}
        if effective_type == "mixed" and query_vectors is not None:
            for i in range(n):
                if i < len(query_vectors) and query_vectors[i]:
                    vec_map[i] = query_vectors[i]

        try:
            with self._get_session() as session:
                # ── Phase 1: BM25 batch (UNION ALL) ──────────────
                bm25_by_kw: dict[int, list[tuple[str, str, str, str, str]]] = {}
                if tsquery_map:
                    bm25_by_kw = self._bm25_batch_union(
                        session,
                        tsquery_map=tsquery_map,
                        top_k=top_k + offset,
                        term_type_codes=canonical_types,
                    )

                # ── Phase 2: Jieba batch (UNION ALL) ─────────────
                jieba_by_kw: dict[int, list[tuple[str, str, str, str, str]]] = {}
                if jieba_tokens_map:
                    jieba_by_kw = self._jieba_batch_union(
                        session,
                        jieba_tokens_map=jieba_tokens_map,
                        top_k=top_k + offset,
                        term_type_codes=canonical_types,
                    )

                # ── Phase 3: Vector batch (UNION ALL) ────────────
                vec_by_kw: dict[int, list[tuple[str, str, str, str, str]]] = {}
                vec_scores_map: dict[int, dict[str, float]] = {}
                if vec_map:
                    vec_by_kw, vec_scores_map = self._vector_batch_union(
                        session,
                        vec_map=vec_map,
                        top_k=top_k + offset,
                        label_filters=label_filters,
                        term_type_codes=canonical_types,
                    )

                # ── Phase 3.5: Exact batch (UNION ALL) ──────────────
                # query_type="exact"：term_name.name_text / term.term_code
                # 精确命中即结果（无 RRF 需要），per-kw 直接分发。
                exact_by_kw: dict[int, list[tuple[str, str, str, str, str]]] = {}
                if effective_type == "exact":
                    exact_by_kw = self._exact_batch_union(
                        session,
                        keywords_map=dict(active),
                        top_k=top_k + offset,
                        term_type_codes=canonical_types,
                    )

                # ── Phase 4: Per-keyword RRF fuse ────────────────
                all_candidate_ids: set[str] = set()
                kw_score_maps: dict[int, dict[str, float]] = {}

                for i, _kw in active:
                    # exact 分支：精确命中直接作为结果，跳过 RRF 融合
                    if effective_type == "exact":
                        hits = exact_by_kw.get(i, [])
                        if not hits:
                            results[i] = QueryResult(total=0, items=[])
                            continue
                        candidate_ids = {c[0] for c in hits}
                        all_candidate_ids.update(candidate_ids)
                        kw_score_maps[i] = dict.fromkeys(candidate_ids, 1.0)
                        continue

                    ranked_lists: list[list[tuple[str, str, str, str, str]]] = []
                    if i in bm25_by_kw:
                        ranked_lists.append(bm25_by_kw[i])
                    if i in jieba_by_kw:
                        ranked_lists.append(jieba_by_kw[i])
                    if i in vec_by_kw:
                        ranked_lists.append(vec_by_kw[i])

                    if not ranked_lists:
                        results[i] = QueryResult(total=0, items=[])
                        continue

                    fused = rrf_fuse(ranked_lists, k=60, top_n=top_k + offset)
                    if not fused:
                        results[i] = QueryResult(total=0, items=[])
                        continue

                    candidate_ids = {c.term_id for c in fused}
                    base_scores: dict[str, float] = {c.term_id: float(c.rrf_score) for c in fused}

                    if effective_type == "mixed" and i in vec_scores_map:
                        vs = vec_scores_map[i]
                        result_scores = {
                            tid: max(base_scores.get(tid, 0.0), vs.get(tid, 0.0))
                            for tid in candidate_ids
                        }
                    else:
                        result_scores = base_scores

                    all_candidate_ids.update(candidate_ids)
                    kw_score_maps[i] = result_scores

                # ── Phase 5: One-shot detail query ────────────────
                if all_candidate_ids:
                    self._detail_batch(
                        session,
                        term_ids=all_candidate_ids,
                    )

                # ── Phase 6: Build per-keyword QueryResult ────────
                for i, _kw in active:
                    if results[i] is not None:
                        continue

                    candidate_ids_i = kw_score_maps.get(i, {})
                    if not candidate_ids_i:
                        results[i] = QueryResult(total=0, items=[])
                        continue

                    filters = self._apply_metadata_filters(
                        candidate_ids=set(candidate_ids_i.keys()),
                        term_type_codes=canonical_types,
                        dataset_ids=dataset_ids,
                        parent_term_code=parent_term_code,
                        ext_attrs=ext_attrs,
                        label_filters=label_filters,
                        label_condition=label_condition,
                    )
                    where_clause = and_(*filters)

                    total = int(
                        session.execute(
                            select(func.count()).select_from(Term).where(where_clause)
                        ).scalar_one()
                    )
                    if total == 0:
                        results[i] = QueryResult(total=0, items=[])
                        continue

                    filtered_rows = session.execute(
                        select(
                            Term.term_id,
                            Term.term_code,
                            Term.term_name,
                            Term.term_type_code,
                            Term.library_id,
                            Term.parent_term_id,
                            Term.desc_summary,
                            Term.term_tags,
                            Term.ext_attrs,
                            Term.created_time,
                            Term.updated_time,
                        )
                        .where(where_clause)
                        .limit(top_k)
                        .offset(offset)
                        .order_by(Term.updated_time.desc())
                    ).all()

                    score_map_i = candidate_ids_i
                    items: list[ProviderTermItem] = []
                    for row in filtered_rows:
                        tid = str(row[0])
                        tags: dict[str, str] = {}
                        raw_tags = row[7]
                        if isinstance(raw_tags, dict):
                            tags = {str(k): str(v) for k, v in raw_tags.items()}
                        term_ext_attrs: dict[str, str] = {}
                        raw_ext_attrs = row[8]
                        if isinstance(raw_ext_attrs, dict):
                            term_ext_attrs = {str(k): str(v) for k, v in raw_ext_attrs.items()}

                        items.append(
                            ProviderTermItem(
                                term_id=tid,
                                term_code=str(row[1]),
                                term_name=str(row[2]),
                                term_type=str(row[3]),
                                dataset_id=str(row[4]) if row[4] else "",
                                parent_term_code=(str(row[5]) if row[5] else ""),
                                desc=str(row[6]) if row[6] else "",
                                labels=tags,
                                synonyms="",
                                ext_attrs=term_ext_attrs,
                                created_time=self._datetime_to_epoch(row[9]),
                                updated_time=self._datetime_to_epoch(row[10]),
                                score=score_map_i.get(tid),
                            )
                        )
                    results[i] = QueryResult(total=total, items=items)

                # Fill empty results for inactive keywords
                for i in range(n):
                    if results[i] is None:
                        results[i] = QueryResult(total=0, items=[])

        except Exception:
            logger.exception(
                "query_terms_batch failed: keywords=%s term_type_codes=%s query_type=%s",
                keywords,
                term_type_codes,
                query_type,
            )
            raise

        return [r for r in results if r is not None]

    def enumerate_object_instances(
        self,
        *,
        object_codes: list[str],
        kb_resource_ids: list[str],
        filters: list[dict[str, Any]] | None = None,
        sort: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> EnumeratedObjectInstances:
        """枚举带度数的对象实例 — 单条 SQL 完成范围过滤 + 度数聚合 + 条件过滤 + 稳定排序 + 分页。

        条件框架：filters 数组按 ``_FILTER_REGISTRY`` 查表（type 走 dict key，
        绝不拼接进 SQL）；degree 为注册表首个 filter 类型（HAVING 阶段）。
        排序框架：sort 按 ``_SORT_REGISTRY`` 查表（by 走 dict key）；similarity
        为注册表首个（且目前唯一）排序类型（Embedding 向量或 BM25 降级）。

        度数语义（T-65，**范围统计**）：out_degree/in_degree 只统计对端 term
        （out → target_term_id / in → source_term_id）落在
        ``object_codes ∪ kb_resource_ids`` **并集**范围内的实例级 BUSINESS 边；
        对端维度之间 OR（任一命中即计），主查询 WHERE 范围维度之间仍 AND。
        实现：out_rel/in_rel LEFT JOIN ON 追加对端 EXISTS 范围条件（独立
        参数 degree_object_codes / degree_kb_resource_ids 绑定同一值）。

        Args:
            object_codes: 对象类型编码范围（尊重输入不校验）。与 kb_resource_ids 为 AND。
            kb_resource_ids: 知识库资源 ID 范围（``ext_attrs->>'kb_resource_id'``）。
            filters: 条件数组 = [{"type": <注册表 key>, "params": {...}}, ...]，v1 只 AND。
            sort: 排序规格 = {"by": <注册表 key>, "params": {...}}，None = 默认序。
                  similarity 在候选集内重排（不截断），Embedding 失败静默降级 BM25；
                  query 空串退化 term_id ASC。显式 sort 优先于 degree filter 隐式排序。
            page: 页码（>=1，1-based）。
            page_size: 每页条数（>=1）。

        Returns:
            items + 诚实 total（同 WHERE+HAVING 的 COUNT 变体，无 ORDER BY/LIMIT）。

        Raises:
            ValueError: filter type 不在注册表 / metric/op 白名单非法 / value 非数字 /
                        sort by 不在注册表 / params 非 dict / query 非 str /
                        page/page_size 非法。
        """
        if page < 1:
            raise ValueError(f"page 必须 >= 1，收到: {page}")
        if page_size < 1:
            raise ValueError(f"page_size 必须 >= 1，收到: {page_size}")
        # 范围全空 → 空结果（即使 filters/sort 有值：它们不代替范围）
        if not object_codes and not kb_resource_ids:
            return EnumeratedObjectInstances(items=[], total=0)

        # ── 解析 filters：查注册表 → validate → build → 按 stage 分组 ──
        having_parts: list[str] = []
        where_parts: list[str] = []
        bind_params: dict[str, object] = {}
        required_joins: set[str] = set()
        degree_sort_expr: str | None = None

        for idx, filt in enumerate(filters or []):
            if not isinstance(filt, dict):
                # 验收钉死 ValueError（_EXCEPTION_MAP: ValueError → 400 invalid_params）
                raise ValueError(f"filter 项必须是 dict，收到: {filt!r}")  # noqa: TRY004
            filter_type = filt.get("type")
            spec = _FILTER_REGISTRY.get(filter_type) if isinstance(filter_type, str) else None
            if spec is None:
                raise ValueError(
                    f"未知 filter type: {filter_type!r}（注册表: {sorted(_FILTER_REGISTRY)}）"
                )
            filter_params = filt.get("params")
            if not isinstance(filter_params, dict):
                # 验收钉死 ValueError（_EXCEPTION_MAP: ValueError → 400 invalid_params）
                raise ValueError(f"filter {filter_type!r} 的 params 必须是 dict")  # noqa: TRY004
            spec.validate(filter_params)
            fragment, extra_binds = spec.build("", filter_params)
            # 绑定参数名唯一化（支持多个 filter AND 组合；整词替换防误改长参数名）
            for name, value in extra_binds.items():
                new_name = f"{filter_type}_{name}_{idx}"
                fragment = re.sub(rf":{re.escape(name)}(?!\w)", f":{new_name}", fragment)
                bind_params[new_name] = value
            if spec.stage == "where":
                where_parts.append(fragment)
            else:
                having_parts.append(fragment)
            required_joins.update(spec.required_joins)
            # 排序：第一个带 sort_expr 的 filter 的度量表达式降序 + term_id ASC
            if spec.sort_expr is not None and degree_sort_expr is None:
                degree_sort_expr = spec.sort_expr(filter_params)

        # ── 解析 sort：查注册表 → validate → build（similarity 含 Embedding/降级逻辑）──
        sort_order_by: str | None = None
        sort_binds: dict[str, object] = {}
        requires_name_join = False
        if sort is not None:
            if not isinstance(sort, dict):
                # 验收钉死 ValueError（_EXCEPTION_MAP: ValueError → 400 invalid_params）
                raise ValueError(f"sort 必须是 dict，收到: {sort!r}")
            sort_by = sort.get("by")
            entry = _SORT_REGISTRY.get(sort_by) if isinstance(sort_by, str) else None
            if entry is None:
                raise ValueError(f"未知 sort by: {sort_by!r}（注册表: {sorted(_SORT_REGISTRY)}）")
            sort_params = sort.get("params")
            if not isinstance(sort_params, dict):
                # 验收钉死 ValueError（_EXCEPTION_MAP: ValueError → 400 invalid_params）
                raise ValueError(f"sort {sort_by!r} 的 params 必须是 dict")
            entry.validate(sort_params)
            fragment, sort_binds = entry.build(sort_params)
            if fragment:
                # 双键（钉死）：分数 DESC + term_id ASC 稳定 tie-break
                sort_order_by = f"{fragment}, t.term_id ASC"
                requires_name_join = entry.requires_name_join

        # ── 动态组装 SQL ──────────────────────────────────────────────
        select_cols = ["t.term_id", "t.term_code", "t.term_name", "t.term_type_code"]
        joins: list[str] = []
        if requires_name_join:
            # similarity 排序键在 name 级（name_embedding / name_keywords）
            joins.append("LEFT JOIN term_name tn\n       ON tn.term_id = t.term_id")
        if "out" in required_joins:
            # SELECT 度数列与 HAVING/ORDER BY 共用同一表达式源，防计数规则漂移
            select_cols.append(f"{_degree_metric_expr('out')} AS out_degree")
            joins.append(
                "LEFT JOIN term_relation out_rel\n"
                "       ON out_rel.source_term_id = t.term_id\n"
                "      AND out_rel.source_term_id IS NOT NULL\n"
                "      AND out_rel.target_term_id  IS NOT NULL\n"
                "      AND out_rel.relation_category = 'BUSINESS'\n"
                "      AND "
                + _degree_opposite_range(
                    "out_rel",
                    "target_term_id",
                    object_codes=object_codes,
                    kb_resource_ids=kb_resource_ids,
                )
            )
        if "in" in required_joins:
            select_cols.append(f"{_degree_metric_expr('in')} AS in_degree")
            joins.append(
                "LEFT JOIN term_relation in_rel\n"
                "       ON in_rel.target_term_id = t.term_id\n"
                "      AND in_rel.source_term_id IS NOT NULL\n"
                "      AND in_rel.target_term_id  IS NOT NULL\n"
                "      AND in_rel.relation_category = 'BUSINESS'\n"
                "      AND "
                + _degree_opposite_range(
                    "in_rel",
                    "source_term_id",
                    object_codes=object_codes,
                    kb_resource_ids=kb_resource_ids,
                )
            )

        where_conditions: list[str] = []
        if object_codes:
            where_conditions.append("t.term_type_code IN :object_codes")
        if kb_resource_ids:
            where_conditions.append("t.ext_attrs->>'kb_resource_id' IN :kb_resource_ids")
        where_conditions.extend(where_parts)

        group_by = "GROUP BY t.term_id, t.term_code, t.term_name, t.term_type_code"
        having_sql = f"HAVING {' AND '.join(having_parts)}" if having_parts else ""
        if sort_order_by is not None:
            # 显式 sort（_SORT_REGISTRY）优先于 degree filter 的隐式排序
            order_by = f"ORDER BY {sort_order_by}"
        elif degree_sort_expr is not None:
            order_by = f"ORDER BY {degree_sort_expr} DESC, t.term_id ASC"
        else:
            order_by = "ORDER BY t.term_id ASC"

        # 降级 BM25 需单行 tsquery（bm25.py 同款 to_tsquery('simple', ...) 形态）
        from_sql = "FROM term t"
        if "tsquery" in sort_binds:
            from_sql += ", to_tsquery('simple', :tsquery) q"
        select_sql = "SELECT " + ", ".join(select_cols) + f"\n{from_sql}"
        join_sql = "\n" + "\n".join(joins) if joins else ""
        where_sql = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        sql = (
            f"{select_sql}{join_sql}\n{where_sql}\n{group_by}\n"
            f"{having_sql}\n{order_by}\nLIMIT :limit OFFSET :offset"
        )
        # total：同 WHERE + GROUP BY + HAVING 的 COUNT(*) 变体（无 ORDER BY/LIMIT）。
        # 必须包一层子查询：无 GROUP BY 时 sqlite 会静默忽略 HAVING。
        total_sql = (
            "SELECT COUNT(*) FROM (\n"
            f"SELECT t.term_id\n{from_sql}{join_sql}\n{where_sql}\n{group_by}\n{having_sql}\n"
            ") AS filtered"
        )

        params: dict[str, object] = {}
        if object_codes:
            params["object_codes"] = object_codes
            if required_joins:
                # 度数对端范围条件独立参数（同一值两份绑定，勿与主 WHERE 混用）
                params["degree_object_codes"] = object_codes
        if kb_resource_ids:
            params["kb_resource_ids"] = kb_resource_ids
            if required_joins:
                params["degree_kb_resource_ids"] = kb_resource_ids
        params.update(bind_params)
        params.update(sort_binds)
        params["limit"] = page_size
        params["offset"] = (page - 1) * page_size

        # ── 执行 ─────────────────────────────────────────────────────
        binds: list[Any] = []
        if object_codes:
            binds.append(bindparam("object_codes", expanding=True))
            if required_joins:
                binds.append(bindparam("degree_object_codes", expanding=True))
        if kb_resource_ids:
            binds.append(bindparam("kb_resource_ids", expanding=True))
            if required_joins:
                binds.append(bindparam("degree_kb_resource_ids", expanding=True))
        stmt = text(sql) if not binds else text(sql).bindparams(*binds)
        total_stmt = text(total_sql) if not binds else text(total_sql).bindparams(*binds)
        with self._get_session() as session:
            rows = session.execute(stmt, params).fetchall()
            total = int(session.execute(total_stmt, params).scalar() or 0)

        items = [
            ObjectInstanceItem(
                term_id=str(row[0]),
                term_code=str(row[1]),
                term_name=str(row[2]),
                term_type_code=str(row[3]),
                out_degree=int(row[4]) if len(row) > 4 and row[4] is not None else 0,
                in_degree=int(row[5]) if len(row) > 5 and row[5] is not None else 0,
            )
            for row in rows
        ]
        return EnumeratedObjectInstances(items=items, total=total)

    # ── Batch SQL helpers ─────────────────────────────────────────────

    @staticmethod
    def _exact_batch_union(
        session: Any,
        *,
        keywords_map: dict[int, str],
        top_k: int,
        term_type_codes: list[str] | None = None,
    ) -> dict[int, list[tuple[str, str, str, str, str]]]:
        """Run exact-match search for multiple keywords via UNION ALL.

        每 kw 一段，``term_name.name_text = kw OR term.term_code = kw`` 精确
        匹配（term_name 表参与 JOIN，别名行同样命中；kw 先 strip 与单条
        ``query_terms(exact)`` 语义一致；不 ilike、不 BM25、不 jieba）。
        ``term_type_codes`` 作为 IN 过滤推入每段 SQL。

        Returns ``{kw_idx: [(term_id, term_name, name_id, term_type_code, term_code)]}``。
        """
        # Build term_type_codes IN clause
        term_type_where = ""
        if term_type_codes is not None:
            if not term_type_codes:
                return {}
            placeholders = ", ".join(f":_exact_tt_{i}" for i in range(len(term_type_codes)))
            term_type_where = f"AND t.term_type_code IN ({placeholders})"

        subqueries: list[str] = []
        params: dict[str, Any] = {}
        if term_type_codes is not None:
            for i, tc in enumerate(term_type_codes):
                params[f"_exact_tt_{i}"] = tc
        for idx, kw in keywords_map.items():
            k = kw.strip()
            if not k:
                continue
            # 每段用 FROM (子查询) 包裹 LIMIT：OpenGauss 与 sqlite 双兼容
            # （sqlite 不支持 "(SELECT .. LIMIT n) UNION ALL (..)" 或
            #  "SELECT .. LIMIT n UNION ALL .." 两种写法）。
            subqueries.append(
                f"SELECT kw_label, term_id, name_text, name_id, "
                f"term_type_code, term_code "
                f"FROM ("
                f"SELECT CAST(:kw_{idx} AS text) AS kw_label, "
                f"tn.term_id, tn.name_text, tn.name_id, t.term_type_code, "
                f"t.term_code "
                f"FROM term_name tn "
                f"JOIN term t ON t.term_id = tn.term_id "
                f"WHERE (tn.name_text = :ex_{idx} OR t.term_code = :ec_{idx}) "
                f"{term_type_where} "
                f"ORDER BY t.updated_time DESC "
                f"LIMIT {int(top_k)}"
                f")"
            )
            params[f"kw_{idx}"] = f"kw_{idx}"
            params[f"ex_{idx}"] = k
            params[f"ec_{idx}"] = k

        if not subqueries:
            return {}

        sql = text(" UNION ALL ".join(subqueries))
        rows = session.execute(sql, params).fetchall()

        grouped: dict[int, list[tuple[str, str, str, str, str]]] = {}
        for row in rows:
            kw_label, term_id, term_name, name_id, tt, tc = row
            kw_idx = int(kw_label.split("_", 1)[1])
            grouped.setdefault(kw_idx, []).append(
                (str(term_id), str(term_name), str(name_id), str(tt), str(tc or ""))
            )
        return grouped

    @staticmethod
    def _bm25_batch_union(
        session: Any,
        *,
        tsquery_map: dict[int, str],
        top_k: int,
        term_type_codes: list[str] | None = None,
    ) -> dict[int, list[tuple[str, str, str, str, str]]]:
        """Run BM25 search for multiple keywords via UNION ALL.

        Returns ``{kw_idx: [(term_id, term_name, name_id, term_type_code, term_code)]}``.
        """
        from datacloud_knowledge.adapters.opengauss.bm25 import (
            _has_name_keywords_column,
        )

        if not _has_name_keywords_column(session):
            logger.error("BM25 requires term_name.name_keywords column")
            return {}

        # Build term_type_codes IN clause
        term_type_where = ""
        if term_type_codes is not None:
            if not term_type_codes:
                return {}
            placeholders = ", ".join(f":_bm25_tt_{i}" for i in range(len(term_type_codes)))
            term_type_where = f"AND t.term_type_code IN ({placeholders})"

        subqueries: list[str] = []
        params: dict[str, Any] = {}
        if term_type_codes is not None:
            for i, tc in enumerate(term_type_codes):
                params[f"_bm25_tt_{i}"] = tc
        for idx, tsquery in tsquery_map.items():
            subqueries.append(
                f"("
                f"SELECT CAST(:kw_{idx} AS text) AS kw_label, "
                f"tn.term_id, tn.name_text, tn.name_id, t.term_type_code, "
                f"ts_rank_cd(tn.name_keywords, q_{idx}, 32) AS score, "
                f"t.term_code "
                f"FROM term_name tn, term t, "
                f"to_tsquery('simple', :ts_{idx}) q_{idx} "
                f"WHERE tn.name_keywords @@ q_{idx} "
                f"AND tn.term_id = t.term_id "
                f"AND tn.name_keywords IS NOT NULL "
                f"{term_type_where} "
                f"ORDER BY score DESC "
                f"LIMIT {int(top_k)}"
                f")"
            )
            params[f"kw_{idx}"] = f"kw_{idx}"
            params[f"ts_{idx}"] = tsquery

        if not subqueries:
            return {}

        sql = text(" UNION ALL ".join(subqueries))
        rows = session.execute(sql, params).fetchall()

        grouped: dict[int, list[tuple[str, str, str, str, str]]] = {}
        for row in rows:
            kw_label, term_id, term_name, name_id, tt, _score, tc = row
            kw_idx = int(kw_label.split("_", 1)[1])
            grouped.setdefault(kw_idx, []).append(
                (str(term_id), str(term_name), str(name_id), str(tt), str(tc or ""))
            )
        return grouped

    @staticmethod
    def _jieba_batch_union(
        session: Any,
        *,
        jieba_tokens_map: dict[int, list[str]],
        top_k: int,
        term_type_codes: list[str] | None = None,
    ) -> dict[int, list[tuple[str, str, str, str, str]]]:
        """Run jieba-token BM25 batch for multiple keywords via UNION ALL.

        Each keyword's tokens are searched by BM25, results are fused per keyword
        via RRF. Returns ``{kw_idx: [(term_id, ...)}]``.
        """
        from datacloud_knowledge.adapters.opengauss.bm25 import (
            _build_char_tsquery,
            _has_name_keywords_column,
        )

        if not _has_name_keywords_column(session):
            return {}

        # Build term_type_codes IN clause
        term_type_where = ""
        if term_type_codes is not None:
            if not term_type_codes:
                return {}
            placeholders = ", ".join(f":_jieba_tt_{i}" for i in range(len(term_type_codes)))
            term_type_where = f"AND t.term_type_code IN ({placeholders})"

        # Flatten (kw_idx, token) pairs
        flat: list[tuple[int, str]] = []
        for kw_idx, tokens in jieba_tokens_map.items():
            for token in tokens:
                flat.append((kw_idx, token))

        if not flat:
            return {}

        subqueries: list[str] = []
        params: dict[str, Any] = {}
        if term_type_codes is not None:
            for i, tc in enumerate(term_type_codes):
                params[f"_jieba_tt_{i}"] = tc
        for seq, (kw_idx, token) in enumerate(flat):
            tsq = _build_char_tsquery(token, ts_operator="|")
            if not tsq:
                continue
            subqueries.append(
                f"("
                f"SELECT CAST(:jt_{seq} AS text) AS jt_label, "
                f"tn.term_id, tn.name_text, tn.name_id, t.term_type_code, "
                f"ts_rank_cd(tn.name_keywords, q_{seq}, 32) AS score, "
                f"t.term_code "
                f"FROM term_name tn, term t, "
                f"to_tsquery('simple', :jts_{seq}) q_{seq} "
                f"WHERE tn.name_keywords @@ q_{seq} "
                f"AND tn.term_id = t.term_id "
                f"AND tn.name_keywords IS NOT NULL "
                f"{term_type_where} "
                f"ORDER BY score DESC "
                f"LIMIT {int(top_k * 2)}"
                f")"
            )
            params[f"jt_{seq}"] = f"{kw_idx}_{seq}"
            params[f"jts_{seq}"] = tsq

        if not subqueries:
            return {}

        sql = text(" UNION ALL ".join(subqueries))
        rows = session.execute(sql, params).fetchall()

        # Group by kw_idx
        kw_ranked: dict[int, list[tuple[str, str, str, str, str]]] = {}
        for row in rows:
            jt_label, term_id, term_name, name_id, tt, _score, tc = row
            kw_idx = int(str(jt_label).split("_", 1)[0])
            kw_ranked.setdefault(kw_idx, []).append(
                (
                    str(term_id),
                    str(term_name),
                    str(name_id),
                    str(tt),
                    str(tc or ""),
                )
            )

        # Per-kw RRF fuse tokens
        result: dict[int, list[tuple[str, str, str, str, str]]] = {}
        for kw_idx, ranked in kw_ranked.items():
            fused = rrf_fuse([ranked], k=60, top_n=top_k)
            result[kw_idx] = [
                (c.term_id, c.term_name, c.name_id, c.term_type_code, c.term_code) for c in fused
            ]

        return result

    @staticmethod
    def _vector_batch_union(
        session: Any,
        *,
        vec_map: dict[int, list[float]],
        top_k: int,
        label_filters: list[LabelFilter] | None = None,
        term_type_codes: list[str] | None = None,
    ) -> tuple[
        dict[int, list[tuple[str, str, str, str, str]]],
        dict[int, dict[str, float]],
    ]:
        """Run vector similarity search for multiple keywords via UNION ALL.

        ``term_type_codes`` and ``label_filters`` are pushed into the SQL so vector
        scan is scoped to the target term types.

        Returns ``(ranked_by_kw, scores_by_kw)``.
        """
        # ── build SQL clauses for term_type_codes + label_filters ─────────
        need_term_join = False
        extra_where_parts: list[str] = []
        if term_type_codes is not None and term_type_codes:
            need_term_join = True
            placeholders = ", ".join(f":_batch_term_type_{i}" for i in range(len(term_type_codes)))
            extra_where_parts.append(f"t.term_type_code IN ({placeholders})")
        if label_filters:
            need_term_join = True
            for i, lf in enumerate(label_filters):
                if isinstance(lf, dict):
                    key = str(lf.get("field_code", ""))
                    fv = lf.get("filter_value")
                else:
                    key = lf.field_code
                    fv = lf.filter_value
                if key and fv is not None:
                    pname = f"bvlf_{i}"
                    extra_where_parts.append(f"t.term_tags->>'{key}' = :{pname}")
        term_join = "JOIN term t ON t.term_id = tn.term_id" if need_term_join else ""
        term_where = "AND " + " AND ".join(extra_where_parts) if extra_where_parts else ""

        subqueries: list[str] = []
        params: dict[str, Any] = {}
        if term_type_codes is not None and term_type_codes:
            for i, tc in enumerate(term_type_codes):
                params[f"_batch_term_type_{i}"] = tc
        for kw_idx, vec in vec_map.items():
            vec_str = "[" + ",".join(str(round(v, 8)) for v in vec) + "]"
            subqueries.append(
                f"("
                f"SELECT CAST(:vl_{kw_idx} AS text) AS kw_label, "
                f"tn.term_id, "
                f"1 - (tn.name_embedding <=> CAST(:vec_{kw_idx} AS vector)) AS score "
                f"FROM term_name tn "
                f"{term_join} "
                f"WHERE tn.name_embedding IS NOT NULL "
                f"{term_where} "
                f"ORDER BY tn.name_embedding <=> CAST(:vec_{kw_idx} AS vector) "
                f"LIMIT {int(top_k)}"
                f")"
            )
            params[f"vl_{kw_idx}"] = f"kw_{kw_idx}"
            params[f"vec_{kw_idx}"] = vec_str
            # Bind label filter param values
            if label_filters:
                for i, lf in enumerate(label_filters):
                    fv_val = lf.get("filter_value") if isinstance(lf, dict) else lf.filter_value  # type: ignore[redundant-expr]
                    if fv_val is not None:
                        pname = f"bvlf_{i}"
                        params.setdefault(pname, str(fv_val))

        if not subqueries:
            return {}, {}

        sql = text(" UNION ALL ".join(subqueries))
        rows = session.execute(sql, params).fetchall()

        ranked: dict[int, list[tuple[str, str, str, str, str]]] = {}
        scores: dict[int, dict[str, float]] = {}
        for row in rows:
            kw_label, term_id, score = row
            kw_idx = int(str(kw_label).split("_", 1)[1])
            ranked.setdefault(kw_idx, []).append((str(term_id), "", "", "", ""))
            scores.setdefault(kw_idx, {})[str(term_id)] = float(score)

        return ranked, scores

    @staticmethod
    def _json_col_to_dict(value: Any) -> dict[str, Any]:
        """jsonb 列 → dict 的防御性转换。

        psycopg 驱动对 OpenGauss jsonb 列返回 dict；sqlite（测试/其他驱动）
        对 TEXT 列返回 str。统一转换为 dict，避免 ``dict(str)`` 抛 ValueError
        导致整条查询静默回退 ``[]``。生产 OpenGauss 路径行为不变。
        """
        if not value:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (ValueError, TypeError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def query_terms_by_labels(
        self,
        *,
        label_filters: list[LabelFilter] | None = None,
        label_condition: LabelCondition = "or",
        term_type_codes: list[str] | None = None,
        filters: list[TermFilterSpec] | None = None,
        top_k: int = 200,
    ) -> list[TermItem]:
        """纯标签过滤检索 — 不需要关键词。

        SQL: WHERE <label 组> AND term_type_code IN (...) AND
                  <filters 元素 0> AND <filters 元素 1> ...
              LIMIT :_lbl_limit

        过滤通道：
          - label_filters / label_condition: 兼容通道（OR/AND 组，A/C 点在用）；
          - term_type_codes: 兼容通道（None=忽略，[]=全滤）；
          - filters: 通用过滤通道（三参数收编于此），元素按传入顺序逐项展开，
            全 AND 组合；field 走白名单映射表（_FILTER_FIELD_MAP），未知 field /
            非法 op / 缺键 / eq 值数 ≠ 1 → 入口抛 ValueError。

        空值契约：
          - filters: None=忽略；[]=全滤（return []，禁止生成 IN ()）；
            元素 in+values=[] → 全滤 return []；元素 eq+values=[] → 契约错误；
          - 全维度空（无任何生效维度）→ return []（不执行无 WHERE 查询）。

        LIMIT 截断发生在全部 WHERE 过滤之后（截断点后移，修复「过滤前截断」）。
        不做 BM25/jieba/vector 子查询，直接 label_filter 作为 WHERE 条件。
        """
        # ── 结构契约校验（try/except 兜底之外）：filters 元素级校验 +
        #    值归一化（term_type_code 维度与独立参数同函数同时机）。契约错误
        #    直接抛 ValueError，不被「异常 → logger.exception + return []」吞掉。
        normalized_filters: list[tuple[str, str, list[str]]] | None = None
        if filters is not None:
            normalized_filters = self._validate_filters(filters)

        # ── 空值契约短路（SQL 组装前）
        if filters is not None and not filters:
            return []  # 4.2 filters=[] → 全滤
        if normalized_filters:
            for _field, op, values in normalized_filters:
                if op == "in" and not values:
                    return []  # 4.3 元素 in+values=[] → 全滤
                # 4.4 eq+values=[] 已在 _validate_filters 抛 ValueError

        canonical_types: list[str] | None = None
        if term_type_codes is not None and term_type_codes:
            canonical_types = [self._normalize_type_code(t) for t in term_type_codes]

        try:
            with self._get_session() as session:
                where_parts: list[str] = []
                params: dict[str, Any] = {}

                # label 组（跳过规则：None/[]/全部条目无效 → 不生成片段）
                label_parts: list[str] = []
                for i, lf in enumerate(label_filters or []):
                    if isinstance(lf, dict):
                        key = str(lf.get("field_code", ""))
                        fv = lf.get("filter_value")
                    else:
                        key = lf.field_code
                        fv = lf.filter_value
                    if key and fv is not None:
                        pname = f"_lbl_{i}"
                        label_parts.append(f"t.term_tags->>'{key}' = :{pname}")
                        params[pname] = str(fv)
                if label_parts:
                    where_parts.append(
                        " AND ".join(label_parts)
                        if label_condition == "and"
                        else f"({' OR '.join(label_parts)})"
                    )

                # term_type_codes（None=忽略，[]=全滤）—— 值经 _normalize_type_code 归一化
                if term_type_codes is not None:
                    if not canonical_types:
                        return []
                    placeholders = ", ".join(f":_lbl_tt_{i}" for i in range(len(canonical_types)))
                    where_parts.append(f"t.term_type_code IN ({placeholders})")
                    for i, tc in enumerate(canonical_types):
                        params[f"_lbl_tt_{i}"] = tc

                # filters 元素（按调用方传入顺序逐元素展开，全 AND）。
                # SQL 列表达式只从白名单映射表取值（禁止动态拼接）。
                if normalized_filters:
                    for idx, (field, op, values) in enumerate(normalized_filters):
                        column = _FILTER_FIELD_MAP[field][0]
                        if op == "eq":
                            pname = f"_flt_{idx}_0"
                            where_parts.append(f"{column} = :{pname}")
                            params[pname] = str(values[0])
                        else:  # "in"
                            placeholders = ", ".join(f":_flt_{idx}_{n}" for n in range(len(values)))
                            where_parts.append(f"{column} IN ({placeholders})")
                            for n, v in enumerate(values):
                                params[f"_flt_{idx}_{n}"] = str(v)

                # 全维度空守卫：无任何 WHERE 片段 → 直接 return []，不执行无过滤查询
                if not where_parts:
                    return []

                where = " AND ".join(where_parts)

                sql = f"""
                    SELECT t.term_id, t.term_code, t.term_name, t.term_type_code,
                           t.library_id, t.term_tags, t.ext_attrs, t.desc_summary,
                           t.created_time, t.updated_time
                    FROM term t
                    WHERE {where}
                    LIMIT :_lbl_limit
                """
                params["_lbl_limit"] = top_k

                rows = session.execute(text(sql), params).all()

                results: list[dict[str, Any]] = []
                for r in rows:
                    tt = self._json_col_to_dict(r[5])
                    ea = self._json_col_to_dict(r[6])
                    results.append(
                        {
                            "term_id": str(r[0]),
                            "term_code": str(r[1] or ""),
                            "term_name": str(r[2] or ""),
                            "term_type": str(r[3] or ""),
                            "term_tags": tt,
                            "ext_attrs": ea,
                            "score": 1.0,
                        }
                    )
                return results  # type: ignore[return-value]

        except Exception:
            logger.exception("query_terms_by_labels failed")
            return []

    @staticmethod
    def _detail_batch(
        session: Any,
        *,
        term_ids: set[str],
    ) -> dict[str, tuple[Any, ...]]:
        """One-shot detail query for all candidate term_ids.

        Returns ``{term_id: row_tuple}``.
        """
        if not term_ids:
            return {}

        rows = session.execute(
            select(
                Term.term_id,
                Term.term_code,
                Term.term_name,
                Term.term_type_code,
                Term.library_id,
                Term.parent_term_id,
                Term.desc_summary,
                Term.term_tags,
                Term.ext_attrs,
                Term.created_time,
                Term.updated_time,
            ).where(Term.term_id.in_(list(term_ids)))
        ).all()

        return {str(row[0]): row for row in rows}

    def get_term_detail(
        self,
        *,
        library_id: str,
        term_id: str,
    ) -> TermDetail | None:
        """查询单条术语完整详情（OpenGauss 实现 — term API 重构版）。

        从 term 表查询完整字段，补充：
        - parentChain: 递归上行 parent_term_id 到根节点
        - names: term_name 表的所有别名（name_id, name_text, search_scope）
        - knowledges: term_knowledge 表的所有知识条目
        - childrenCount: 直接子术语数
        - relationCount: 作为 source 或 target 的关系总数
        - domain: domain_ids[] 转换为 [{code, name}]
        """
        try:
            with self._get_session() as session:
                row = session.execute(
                    select(
                        Term.term_id,
                        Term.term_code,
                        Term.term_name,
                        Term.term_type_code,
                        Term.library_id,
                        Term.parent_term_id,
                        Term.desc_summary,
                        Term.term_tags,
                        Term.ext_attrs,
                        Term.domain_ids,
                        Term.created_time,
                        Term.updated_time,
                    ).where(Term.term_id == term_id)
                ).one_or_none()

                if row is None:
                    return None

                # ── parentChain: recursively walk parent_term_id up to root ──
                # Guard against cycles and unreasonable depth (max 50 levels)
                _max_parent_chain_depth = 50
                parent_chain: list[dict[str, str]] = []
                visited_ids: set[str] = {term_id}
                current_parent_id = str(row[5]) if row[5] else None
                depth = 0
                while current_parent_id and depth < _max_parent_chain_depth:
                    if current_parent_id in visited_ids:
                        logger.warning(
                            "Cycle detected in parent chain for term_id=%s at depth=%d",
                            term_id,
                            depth,
                        )
                        break
                    visited_ids.add(current_parent_id)
                    parent_row = session.execute(
                        select(
                            Term.term_id,
                            Term.term_code,
                            Term.term_name,
                            Term.parent_term_id,
                        ).where(Term.term_id == current_parent_id)
                    ).one_or_none()
                    if parent_row is None:
                        break
                    parent_chain.append(
                        {
                            "termId": str(parent_row[0]),
                            "termCode": str(parent_row[1]),
                            "termName": str(parent_row[2]),
                        }
                    )
                    current_parent_id = str(parent_row[3]) if parent_row[3] else None
                    depth += 1

                if depth >= _max_parent_chain_depth:
                    logger.warning(
                        "Parent chain exceeded max depth for term_id=%s, truncated at %d",
                        term_id,
                        _max_parent_chain_depth,
                    )

                # ── names: query term_name table ──
                name_rows = session.execute(
                    select(
                        TermName.name_id,
                        TermName.name_text,
                        TermName.search_scope,
                    ).where(TermName.term_id == term_id)
                ).all()
                names = [
                    {
                        "name_id": str(n[0]),
                        "name_text": str(n[1]),
                        "search_scope": n[2] if isinstance(n[2], dict) else {},
                    }
                    for n in name_rows
                ]

                # ── knowledges: query term_knowledge table ──
                knowledge_rows = session.execute(
                    select(
                        TermKnowledge.knowledge_id,
                        TermKnowledge.desc_summary,
                        TermKnowledge.desc,
                        TermKnowledge.ext_system,
                        TermKnowledge.ext_kb_id,
                        TermKnowledge.ext_doc_id,
                        TermKnowledge.sort_order,
                        TermKnowledge.created_time,
                        TermKnowledge.updated_time,
                    )
                    .where(TermKnowledge.term_id == term_id)
                    .order_by(TermKnowledge.sort_order)
                ).all()
                knowledges = [
                    {
                        "knowledge_id": str(k[0]),
                        "desc_summary": str(k[1]) if k[1] else None,
                        "desc": str(k[2]) if k[2] else None,
                        "ext_system": str(k[3]) if k[3] else None,
                        "ext_kb_id": str(k[4]) if k[4] else None,
                        "ext_doc_id": str(k[5]) if k[5] else None,
                        "sort_order": int(k[6]) if k[6] is not None else 0,
                        "created_time": k[7].isoformat() if k[7] is not None else None,
                        "updated_time": k[8].isoformat() if k[8] is not None else None,
                    }
                    for k in knowledge_rows
                ]

                # ── childrenCount: COUNT(*) WHERE parent_term_id = :id ──
                children_count = int(
                    session.execute(
                        select(func.count()).select_from(Term).where(Term.parent_term_id == term_id)
                    ).scalar_one()
                )

                # ── relationCount: COUNT(*) WHERE source_term_id or target_term_id = :id ──
                relation_count = int(
                    session.execute(
                        select(func.count())
                        .select_from(TermRelation)
                        .where(
                            or_(
                                TermRelation.source_term_id == term_id,
                                TermRelation.target_term_id == term_id,
                            )
                        )
                    ).scalar_one()
                )

                # ── domain translation: resolve domain_ids[] to [{code, name}] ──
                domain_ids: list[str] = list(row[9]) if row[9] else []
                domain_list: list[dict[str, str]] = []
                if domain_ids:
                    domain_rows = session.execute(
                        select(
                            TermDomain.domain_id,
                            TermDomain.domain_code,
                            TermDomain.domain_name,
                        ).where(TermDomain.domain_id.in_(domain_ids))
                    ).all()
                    domain_list = [{"code": str(d[1]), "name": str(d[2])} for d in domain_rows]

        except Exception:
            logger.exception("get_term_detail failed: term_id=%s", term_id)
            raise

        return TermDetail(
            term_id=str(row[0]),
            term_code=str(row[1]),
            term_name=str(row[2]),
            term_type=str(row[3]),
            dataset_id=str(row[4]) if row[4] else "",
            library_id=str(row[4]) if row[4] else "",
            parent_term_code=str(row[5]) if row[5] else "",
            desc=str(row[6]) if row[6] else "",
            term_tags=row[7] if isinstance(row[7], dict) else {},
            ext_attrs=row[8] if isinstance(row[8], dict) else {},
            domain=domain_list,
            parent_chain=parent_chain,
            names=names,
            knowledges=knowledges,
            children_count=children_count,
            relation_count=relation_count,
            created_time=self._datetime_to_epoch(row[10]),
            updated_time=self._datetime_to_epoch(row[11]),
        )

    def list_terms(
        self,
        *,
        library_id: str,
        term_type: str | None = None,
        term_type_no_eq: str | None = None,
        domain_code: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """分页列出术语（term API 重构版）。

        OpenGauss 实现：按 term_type、library_id、domain_code、keyword 分页查询，
        返回 term dict 列表（含 domain 翻译）。
        """
        # Resolve domain_code → domain_id if provided
        domain_id: str | None = None
        if domain_code:
            domain_id = self._resolve_domain_code(library_id, domain_code)
            if domain_id is None:
                return {
                    "data": [],
                    "pageIndex": page_index,
                    "pageSize": page_size,
                    "totalCount": 0,
                    "totalPages": 0,
                }

        try:
            with self._get_session() as session:
                filters: list[Any] = [Term.library_id == library_id]
                if term_type:
                    canonical = self._normalize_type_code(term_type)
                    filters.append(Term.term_type_code == canonical)
                if term_type_no_eq:
                    canonical_no_eq = self._normalize_type_code(term_type_no_eq)
                    filters.append(Term.term_type_code != canonical_no_eq)
                if domain_id is not None:
                    filters.append(text("term.domain_ids @> ARRAY[:domain_id]::varchar[]"))
                if keyword and keyword.strip():
                    filters.append(text("(term.term_name ILIKE :kw OR term.term_code ILIKE :kw)"))

                where_clause = and_(*filters) if filters else text("1=1")

                params: dict[str, Any] = {}
                if domain_id is not None:
                    params["domain_id"] = domain_id
                if keyword and keyword.strip():
                    params["kw"] = f"%{keyword.strip()}%"

                total = int(
                    session.execute(
                        select(func.count()).select_from(Term).where(where_clause),
                        params,
                    ).scalar_one()
                )

                if total == 0:
                    return {
                        "data": [],
                        "pageIndex": page_index,
                        "pageSize": page_size,
                        "totalCount": 0,
                        "totalPages": 0,
                    }

                offset = (page_index - 1) * page_size
                rows = session.execute(
                    select(
                        Term.term_id,
                        Term.term_code,
                        Term.term_name,
                        Term.term_type_code,
                        Term.library_id,
                        Term.parent_term_id,
                        Term.desc_summary,
                        Term.term_tags,
                        Term.ext_attrs,
                        Term.domain_ids,
                        Term.created_time,
                        Term.updated_time,
                    )
                    .where(where_clause)
                    .limit(page_size)
                    .offset(offset)
                    .order_by(Term.updated_time.desc()),
                    params,
                ).all()

                # ── Batch resolve domain translation ──
                all_domain_ids: set[str] = set()
                for r_ in rows:
                    if r_[9]:
                        all_domain_ids.update(r_[9])
                domain_map = self._batch_resolve_domain_codes(library_id, all_domain_ids)

        except Exception:
            logger.exception(
                "list_terms failed: library_id=%s term_type=%s keyword=%s",
                library_id,
                term_type,
                keyword,
            )
            raise

        data: list[dict[str, Any]] = []
        for row in rows:
            domain_ids_for_row: list[str] = list(row[9]) if row[9] else []
            domain_translated = self._build_domain_list(domain_ids_for_row, domain_map)

            data.append(
                {
                    "term_id": str(row[0]),
                    "term_code": str(row[1]),
                    "term_name": str(row[2]),
                    "term_type_code": str(row[3]),
                    "library_id": str(row[4]) if row[4] else None,
                    "parent_term_id": str(row[5]) if row[5] else None,
                    "desc_summary": str(row[6]) if row[6] else None,
                    "term_tags": row[7] if isinstance(row[7], dict) else {},
                    "ext_attrs": row[8] if isinstance(row[8], dict) else {},
                    "domain": domain_translated,
                    "created_time": row[10].isoformat() if row[10] is not None else None,
                    "updated_time": row[11].isoformat() if row[11] is not None else None,
                }
            )

        return {
            "data": data,
            "pageIndex": page_index,
            "pageSize": page_size,
            "totalCount": total,
            "totalPages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }

    def delete_scope(self, scope: str) -> dict[str, Any]:
        """删除指定 scope 下的所有术语数据（术语 + 名称 + 关系 + 知识）。

        通过递归 CTE 找到根术语及其所有子孙术语，按正确顺序删除
        关联表数据以避免外键约束冲突。

        Args:
            scope: scope 字符串，格式 ``"{scope_type}:{resource_code}"``
                   例如 ``"object:by_test"`` 或 ``"view:v_task_summary"``。

        Returns:
            ``{"ok": True}`` 或 ``{"ok": False, "error": "..."}``。
        """
        parts = scope.split(":", 1)
        if len(parts) != 2:
            return {"ok": False, "error": f"非法 scope 格式: {scope}，期望 {{type}}:{{code}}"}
        scope_type, scope_code = parts

        # 递归 CTE：从根术语出发，收集所有子孙 term_id
        cte_sql = """
            WITH RECURSIVE scope_terms AS (
                SELECT t.term_id FROM term t
                WHERE t.term_type_code = :scope_type AND t.term_code = :scope_code
                UNION
                SELECT t.term_id FROM term t
                JOIN scope_terms s ON t.parent_term_id = s.term_id
            )
        """

        try:
            with self._get_session() as session:
                # 先删除 term_knowledge（FK → term.term_id）
                session.execute(
                    text(
                        cte_sql
                        + "DELETE FROM term_knowledge "
                        + "WHERE term_id IN (SELECT term_id FROM scope_terms)"
                    ),
                    {"scope_type": scope_type, "scope_code": scope_code},
                )

                # 再删除 term_relation（FK source/target → term.term_id）
                session.execute(
                    text(
                        cte_sql
                        + "DELETE FROM term_relation "
                        + "WHERE source_term_id IN (SELECT term_id FROM scope_terms) "
                        + "OR target_term_id IN (SELECT term_id FROM scope_terms)"
                    ),
                    {"scope_type": scope_type, "scope_code": scope_code},
                )

                # 删除 scoped term_names（按 search_scope JSONB 匹配）
                scope_json = json.dumps(
                    {"scope": scope_type, "code": scope_code}, ensure_ascii=False
                )
                session.execute(
                    text("DELETE FROM term_name WHERE search_scope @> CAST(:scope_json AS jsonb)"),
                    {"scope_json": scope_json},
                )
                # 再按 term_id 删除剩余的 term_name
                session.execute(
                    text(
                        cte_sql
                        + "DELETE FROM term_name "
                        + "WHERE term_id IN (SELECT term_id FROM scope_terms)"
                    ),
                    {"scope_type": scope_type, "scope_code": scope_code},
                )

                # 最后删除 term 本身
                session.execute(
                    text(
                        cte_sql
                        + "DELETE FROM term "
                        + "WHERE term_id IN (SELECT term_id FROM scope_terms)"
                    ),
                    {"scope_type": scope_type, "scope_code": scope_code},
                )

                session.commit()

            logger.info("delete_scope 完成: scope=%s", scope)
            return {"ok": True}
        except Exception as exc:
            logger.exception("delete_scope 失败: scope=%s", scope)
            return {"ok": False, "error": str(exc)}

    def resolve_field_aliases_with_names(
        self,
        *,
        terms: Sequence[str],
        scope_code: str,
    ) -> FieldResolutionResultWithNames:
        """扩展版字段别名消歧：resolved 同时返回 term_name。

        在 scope_code 对应的视图/对象下，通过 TermName 别名和 term_code 直接匹配两种方式
        查找 prop，并将命中的用户输入（terms）映射到 ResolvedField(term_code, term_name)。
        支持值级别消歧（resolve_values=True 时对 value_terms 追加匹配）。
        """
        warnings.warn(
            "resolve_field_aliases_with_names() is deprecated: binds field/alias domain concepts. Use query_terms + list_term_names instead.",
            FutureWarning,
            stacklevel=2,
        )
        unique_field_terms = list(dict.fromkeys(terms)) if terms else []
        if not scope_code or not unique_field_terms:
            return FieldResolutionResultWithNames(unresolved=list(unique_field_terms))

        view_scope = {"scope": "view", "code": scope_code}
        obj_scope = {"scope": "object", "code": scope_code}
        global_scope = {"scope": "global"}

        try:
            with self._get_session() as session:
                queries = []

                # 子查询 1a：通过 TermName 别名匹配（中文名/别名 → prop）
                field_q = (
                    select(
                        literal("field").label("match_type"),
                        TermName.name_text.label("matched_text"),
                        Term.term_code,
                        Term.term_name,
                        TermName.search_scope,
                    )
                    .join(Term, Term.term_id == TermName.term_id)
                    .where(
                        TermName.name_text.in_(unique_field_terms),
                        Term.term_type_code == "prop",
                        or_(
                            TermName.search_scope.contains(view_scope),
                            TermName.search_scope.contains(obj_scope),
                            TermName.search_scope.contains(global_scope),
                        ),
                    )
                )
                queries.append(field_q)

                # 子查询 1b：通过 Term.term_code 直接匹配（英文 field_code → prop）
                view_obj_fc = aliased(Term, name="view_obj_fc")
                prop_fc = aliased(Term, name="prop_fc")
                _null_scope_fc = cast(literal(None), JSONB)
                field_code_q = (
                    select(
                        literal("field").label("match_type"),
                        prop_fc.term_code.label("matched_text"),
                        prop_fc.term_code,
                        prop_fc.term_name,
                        _null_scope_fc.label("search_scope"),
                    )
                    .select_from(view_obj_fc)
                    .join(TermRelation, TermRelation.source_term_id == view_obj_fc.term_id)
                    .join(prop_fc, prop_fc.term_id == TermRelation.target_term_id)
                    .where(
                        view_obj_fc.term_code == scope_code,
                        view_obj_fc.term_type_code.in_(["view", "object"]),
                        prop_fc.term_type_code == "prop",
                        prop_fc.term_code.in_(unique_field_terms),
                    )
                )
                queries.append(field_code_q)

                stmt = queries[0].union_all(queries[1])
                rows = session.execute(stmt).all()
        except Exception:
            logger.exception(
                "resolve_field_aliases_with_names failed: terms=%s, scope_code=%s",
                unique_field_terms,
                scope_code,
            )
            raise

        # 分拣结果
        field_hits: dict[str, dict[str, tuple[str, dict[str, str]]]] = {}
        for match_type, matched_text, term_code, term_name, search_scope in rows:
            if str(match_type) != "field":
                continue
            alias = str(matched_text)
            code = str(term_code)
            if alias not in field_hits:
                field_hits[alias] = {}
            if code not in field_hits[alias]:
                raw_scope: dict[str, str] = (
                    {str(k): str(v) for k, v in search_scope.items()}
                    if isinstance(search_scope, dict)
                    else {}
                )
                field_hits[alias][code] = (str(term_name), raw_scope)

        resolved: dict[str, ResolvedField] = {}
        ambiguous: dict[str, list[AmbiguousCandidate]] = {}
        unresolved: list[str] = []

        for term in unique_field_terms:
            candidates = field_hits.get(term)
            if candidates is None:
                unresolved.append(term)
            elif len(candidates) == 1:
                code, (name, _scope) = next(iter(candidates.items()))
                resolved[term] = ResolvedField(term_code=code, term_name=name)
            else:
                ambiguous[term] = [
                    AmbiguousCandidate(
                        term_code=code,
                        term_name=name,
                        matched_alias=term,
                        scope=scope,
                    )
                    for code, (name, scope) in candidates.items()
                ]

        logger.info(
            "[resolve_field_aliases_with_names] scope=%s resolved=%d ambiguous=%d unresolved=%d",
            scope_code,
            len(resolved),
            len(ambiguous),
            len(unresolved),
        )
        return FieldResolutionResultWithNames(
            resolved=resolved,
            ambiguous=ambiguous,
            unresolved=unresolved,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 内部辅助方法
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _normalize_type_code(type_code: str) -> str:
        """将术语类型编码规范化为标准短编码（如 ONTOLOGY_VIEW → view）。"""
        raw = (type_code or "").strip()
        if not raw:
            raise ValueError("term_type_code 不能为空")
        mapping = {
            "ONTOLOGY_VIEW": "view",
            "ONTOLOGY_OBJ": "object",
            "ONTOLOGY_ACTION": "action",
            "ONTOLOGY_FUNC": "func",
            "ONTOLOGY_PARAM": "param",
            "ONTOLOGY_PROP": "prop",
            "VIEW": "view",
            "OBJ": "object",
            "ACTION": "action",
            "FUNC": "func",
            "PARAM": "param",
            "PROP": "prop",
        }
        return mapping.get(raw, raw)

    @staticmethod
    def _validate_filters(
        filters: list[TermFilterSpec],
    ) -> list[tuple[str, str, list[str]]]:
        """filters 结构契约校验 + term_type_code 值归一化。

        在 SQL 组装之前、try/except 兜底之外调用 —— 契约错误直接抛 ValueError，
        不被「异常 → logger.exception + return []」吞掉（编程错误早暴露）。

        契约错误（抛 ValueError）：
          - 元素非 dict / 缺 field / field 不在白名单 / 缺 op / op 非法 /
            缺 values / values 非 list / eq 且 len(values) != 1（含 eq+[]）。

        值语义（不抛错，返回供空值契约短路）：
          - in + values=[] → 返回后由调用方全滤 return []。

        返回规范化后的 (field, op, 归一化 values) 三元组列表；term_type_code
        维度值经 _normalize_type_code 归一化（与独立参数同函数、同一时机——
        组装前统一归一化）；kb 三键为原始字符串 ID，仅 str 绑定不归一化。
        """
        normalized: list[tuple[str, str, list[str]]] = []
        for idx, flt in enumerate(filters):
            if not isinstance(flt, Mapping):
                # 结构契约错误统一抛 ValueError（RPC 映射 400），非法类型亦归入契约错误
                raise ValueError(  # noqa: TRY004
                    f"filters[{idx}] 必须是 dict（FilterSpec），收到: {type(flt).__name__}"
                )
            if "field" not in flt:
                raise ValueError(f"filters[{idx}] 缺少 field 键（FilterSpec 三键必填）")
            field = str(flt["field"])
            if field not in _FILTER_FIELD_MAP:
                raise ValueError(
                    f"filters[{idx}] 未知 field: {field!r}（白名单: {sorted(_FILTER_FIELD_MAP)}）"
                )
            if "op" not in flt:
                raise ValueError(f"filters[{idx}] 缺少 op 键（FilterSpec 三键必填）")
            op = flt["op"]
            if op not in ("eq", "in"):
                raise ValueError(f"filters[{idx}] 非法 op: {op!r}（仅支持 'eq' / 'in'）")
            if "values" not in flt:
                raise ValueError(f"filters[{idx}] 缺少 values 键（FilterSpec 三键必填）")
            values = flt["values"]
            if not isinstance(values, (list, tuple)):
                # 结构契约错误统一抛 ValueError（同字段类型错误归入契约）
                raise ValueError(  # noqa: TRY004
                    f"filters[{idx}] values 必须是 list，收到: {type(values).__name__}"
                )
            if op == "eq" and len(values) != 1:
                raise ValueError(f"filters[{idx}] op=eq 需要恰 1 个值，收到 {len(values)} 个")
            normalizer = _FILTER_FIELD_MAP[field][1]
            if normalizer is not None:
                values = [normalizer(str(v)) for v in values]
            else:
                values = [str(v) for v in values]
            normalized.append((field, op, values))
        return normalized

    @staticmethod
    def _build_filters(
        *,
        canonical_type: str,
        keyword: str | None,
        tags: list[TagFilter] | None,
    ) -> list[Any]:
        """构建 SQLAlchemy 过滤条件列表。

        Args:
            canonical_type: 标准化后的术语类型编码。
            keyword: 可选关键词（精确匹配 term_name 或 term_code）。
            tags: 可选标签过滤条件列表。

        Returns:
            SQLAlchemy where 表达式列表。
        """
        filters: list[Any] = [Term.term_type_code == canonical_type]

        normalized_keyword = (keyword or "").strip()
        if normalized_keyword:
            filters.append(
                or_(
                    Term.term_name == normalized_keyword,
                    Term.term_code == normalized_keyword,
                )
            )

        if tags:
            filters.extend(_TermReader._tag_filter_expr(tf) for tf in tags)

        return filters

    @staticmethod
    def _tag_filter_expr(tf: TagFilter) -> Any:
        """将单个 TagFilter 转换为 SQLAlchemy 表达式。

        支持 JSONB 字段中的 text/number/timestamp 类型标签过滤。
        """
        key = tf.key
        op = tf.op
        vtype = tf.value_type

        val_text = Term.term_tags.op("->>")(key)

        if op == "in":
            if not isinstance(tf.value, list):
                raise TypeError("tag filter op=in 时 value 必须是数组")
            return val_text.in_(tf.value)

        if op == "like":
            if isinstance(tf.value, list):
                raise TypeError("tag filter op=like 时 value 必须是字符串")
            return val_text.ilike(f"%{tf.value}%")

        if isinstance(tf.value, list):
            raise TypeError(f"tag filter op={op} 时 value 必须是字符串")

        if op == "eq":
            return val_text == tf.value

        op_map = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
        sql_op = op_map.get(op)
        if not sql_op:
            raise ValueError(f"不支持的 tag op: {op}")

        left: Any
        right: Any
        if vtype == "number":
            left = cast(func.nullif(val_text, ""), NUMERIC)
            right = cast(tf.value, NUMERIC)
        elif vtype == "timestamp":
            left = cast(func.nullif(val_text, ""), TIMESTAMP)
            right = cast(tf.value, TIMESTAMP)
        else:
            left = val_text
            right = tf.value

        return left.op(sql_op)(right)

    @staticmethod
    def _apply_order_by(stmt: Any, *, order_by: str) -> Any:
        """为查询语句附加排序子句。

        Args:
            stmt: SQLAlchemy select 语句。
            order_by: 排序方式（relevance/updated_time/created_time/term_name）。

        Returns:
            附加了 order_by 的语句。

        Raises:
            ValueError: 未知排序字段时抛出。
        """
        ob = (order_by or "").strip().lower()
        if ob in ("", "relevance"):
            return stmt.order_by(Term.updated_time.desc(), Term.term_id.asc())
        if ob == "updated_time":
            return stmt.order_by(Term.updated_time.desc(), Term.term_id.asc())
        if ob == "created_time":
            return stmt.order_by(Term.created_time.desc(), Term.term_id.asc())
        if ob == "term_name":
            return stmt.order_by(Term.term_name.asc(), Term.term_id.asc())
        raise ValueError(f"未知排序字段: {order_by}")

    @staticmethod
    def _has_cjk(text: str) -> bool:
        """Check if text contains CJK characters."""
        return bool(re.search(r"[\u4e00-\u9fff]", text))

    @staticmethod
    def _label_filter_expr(lf: LabelFilter | dict[str, Any]) -> Any:
        """Convert a LabelFilter (or dict) to a SQLAlchemy expression.

        Supports both LabelFilter objects and plain dicts with keys:
        field_code, filter_value, min_filter_value, max_filter_value.
        """
        exprs: list[Any] = []
        # Accept both LabelFilter objects and dicts (from serialized JSON).
        if isinstance(lf, dict):
            key = str(lf.get("field_code", ""))
            fv = lf.get("filter_value")
            mn = lf.get("min_filter_value")
            mx = lf.get("max_filter_value")
        else:
            key = lf.field_code
            fv = lf.filter_value
            mn = lf.min_filter_value
            mx = lf.max_filter_value
        val_text = Term.term_tags.op("->>")(key)

        if fv is not None:
            exprs.append(val_text == fv)
        if mn is not None:
            val_num = cast(func.nullif(val_text, ""), NUMERIC)
            exprs.append(val_num >= mn)
        if mx is not None:
            val_num = cast(func.nullif(val_text, ""), NUMERIC)
            exprs.append(val_num <= mx)

        if not exprs:
            return text("1=1")
        return and_(*exprs)

    def _text_search_candidates(
        self,
        session: Any,
        *,
        keyword: str,
        query_type: QueryType,
        query_vector: list[float] | None = None,
        top_k: int = 500,
        label_filters: list[LabelFilter] | None = None,
        term_type: str | None = None,
    ) -> tuple[set[str], dict[str, float]]:
        """Unified text search entry — returns ``(candidate_term_ids, score_map)``.

        Dispatches to BM25 / vector / exact match based on ``query_type``.

        ``term_type`` and ``label_filters`` are pushed into the embedding/mixed
        SQL so that the vector search itself is scoped to the target term type,
        avoiding wasted top‑K slots from irrelevant types.

        Returns:
            ``(set of term_ids, {term_id: score})``.  Empty set when no candidates.
        """
        kw = keyword.strip()
        if not kw:
            return set(), {}

        # ── build SQL clauses for term_type + label_filters ───────────
        # Both are pushed into embedding/mixed SQL to filter during vector scan.
        need_term_join = False
        extra_where_parts: list[str] = []
        extra_params: dict[str, str] = {}

        if term_type:
            need_term_join = True
            extra_where_parts.append("t.term_type_code = :_term_type")
            extra_params["_term_type"] = term_type

        if label_filters:
            need_term_join = True
            for i, lf in enumerate(label_filters):
                if isinstance(lf, dict):
                    key = str(lf.get("field_code", ""))
                    fv = lf.get("filter_value")
                else:
                    key = lf.field_code
                    fv = lf.filter_value
                if key and fv is not None:
                    pname = f"lf_{i}"
                    extra_where_parts.append(f"t.term_tags->>'{key}' = :{pname}")
                    extra_params[pname] = str(fv)

        term_join = "JOIN term t ON t.term_id = tn.term_id" if need_term_join else ""
        term_where = "AND " + " AND ".join(extra_where_parts) if extra_where_parts else ""

        # ── exact ──────────────────────────────────────────────────
        if query_type == "exact":
            rows1 = session.execute(select(TermName.term_id).where(TermName.name_text == kw)).all()
            rows2 = session.execute(select(Term.term_id).where(Term.term_code == kw)).all()
            eids: set[str] = {str(r[0]) for r in rows1} | {str(r[0]) for r in rows2}
            return eids, dict.fromkeys(eids, 1.0)

        # ── embedding ──────────────────────────────────────────────
        if query_type == "embedding":
            if query_vector is None:
                logger.warning(
                    "embedding query_type requires query_vector, got None — returning empty"
                )
                return set(), {}
            sql = text(
                f"""
                SELECT tn.term_id,
                       1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS score
                FROM term_name tn
                {term_join}
                WHERE tn.name_embedding IS NOT NULL
                {term_where}
                ORDER BY tn.name_embedding <=> CAST(:vector AS vector)
                LIMIT :limit
                """
            )
            vec_str = "[" + ",".join(str(round(v, 8)) for v in query_vector) + "]"
            params: dict[str, object] = {"vector": vec_str, "limit": top_k, **extra_params}
            rows = session.execute(sql, params).all()
            return {str(r[0]) for r in rows}, {str(r[0]): float(r[1]) for r in rows}

        # ── fulltext / mixed ───────────────────────────────────────
        bm25_results = bm25_search_with_or(session, kw, top_k=top_k, min_score=0.001)
        ranked_lists: list[list[tuple[str, str, str, str, str]]] = []
        if bm25_results:
            ranked_lists.append(
                [
                    (r.term_id, r.term_name, r.name_id, r.term_type_code, r.term_code)
                    for r in bm25_results
                ]
            )

        has_cjk = self._has_cjk(kw)
        if has_cjk:
            jieba_results = jieba_recall(session, kw, top_k=top_k)
            if jieba_results:
                ranked_lists.append(jieba_results)

        # ── mixed: add vector results ──────────────────────────────
        vec_scores: dict[str, float] = {}
        if query_type == "mixed" and query_vector is not None:
            vec_sql = text(
                f"""
                SELECT tn.term_id,
                       1 - (tn.name_embedding <=> CAST(:vector AS vector)) AS score
                FROM term_name tn
                {term_join}
                WHERE tn.name_embedding IS NOT NULL
                {term_where}
                ORDER BY tn.name_embedding <=> CAST(:vector AS vector)
                LIMIT :limit
                """
            )
            vec_str = "[" + ",".join(str(round(v, 8)) for v in query_vector) + "]"
            params = {"vector": vec_str, "limit": top_k, **extra_params}
            vec_rows = session.execute(vec_sql, params).all()
            if vec_rows:
                ranked_lists.append([(str(r[0]), "", "", "", "") for r in vec_rows])
                vec_scores = {str(r[0]): float(r[1]) for r in vec_rows}
        elif query_type == "mixed":
            logger.info("mixed query_type without query_vector — degrading to fulltext")

        if not ranked_lists:
            return set(), {}

        fused = rrf_fuse(ranked_lists, k=60, top_n=top_k)
        fused_ids = {c.term_id for c in fused}
        fused_scores = {c.term_id: float(c.rrf_score) for c in fused}

        if query_type == "mixed" and vec_scores:
            result_ids = fused_ids
            result_scores = {
                tid: max(fused_scores.get(tid, 0.0), vec_scores.get(tid, 0.0)) for tid in fused_ids
            }
        else:
            result_ids = fused_ids
            result_scores = fused_scores
        return result_ids, result_scores

    @staticmethod
    def _apply_metadata_filters(
        *,
        candidate_ids: set[str] | None = None,
        term_type_codes: list[str] | None = None,
        dataset_ids: list[str] | None = None,
        parent_term_code: str | None = None,
        ext_attrs: dict[str, Any] | None = None,
        label_filters: list[LabelFilter] | None = None,
        label_condition: LabelCondition = "and",
    ) -> list[Any]:
        """Build a list of SQLAlchemy filter expressions for Term metadata.

        All filters are AND-ed together; callers pass the list to ``.where(*filters)``.
        """
        filters: list[Any] = []

        if candidate_ids is not None:
            filters.append(Term.term_id.in_(list(candidate_ids)))

        if term_type_codes:
            filters.append(Term.term_type_code.in_(term_type_codes))

        if dataset_ids:
            filters.append(Term.library_id.in_(dataset_ids))

        if parent_term_code:
            filters.append(Term.parent_term_id == parent_term_code)

        if ext_attrs:
            for key, value in ext_attrs.items():
                filters.append(Term.ext_attrs[key].astext == str(value))

        if label_filters:
            tag_exprs = [_TermReader._label_filter_expr(lf) for lf in label_filters]
            if label_condition == "and":
                filters.append(and_(*tag_exprs))
            else:
                filters.append(or_(*tag_exprs))

        if not filters:
            filters.append(text("1=1"))

        return filters

    @staticmethod
    def _convert_db_row_to_term_row(row: Any, *, score: float | None = None) -> _TermSearchRow:
        """将 DB 查询行转换为内部 _TermSearchRow 结构。"""
        term_tags = row[5] if isinstance(row[5], dict) else {}
        return _TermSearchRow(
            term_id=str(row[0]),
            term_code=str(row[1]),
            term_name=str(row[2]),
            term_type_code=str(row[3]),
            desc_summary=row[4],
            term_tags=term_tags,
            created_time=row[6],
            updated_time=row[7],
            score=score,
        )

    @staticmethod
    def _convert_bm25_rows_to_term_rows(
        *,
        session: Any,
        bm25_rows: list[Any],
        filters: list[Any],
    ) -> list[_TermSearchRow]:
        """将 BM25 搜索结果行转换为内部 _TermSearchRow 结构。

        按 score 排序后从 DB 补充完整字段信息，保留原先 BM25 分数。
        """
        if not bm25_rows:
            return []

        score_by_term_id = {str(row.term_id): float(row.score) for row in bm25_rows}
        ordered_term_ids = list(score_by_term_id)
        db_rows = session.execute(
            select(
                Term.term_id,
                Term.term_code,
                Term.term_name,
                Term.term_type_code,
                Term.desc_summary,
                Term.term_tags,
                Term.created_time,
                Term.updated_time,
            ).where(Term.term_id.in_(ordered_term_ids), *filters)
        ).all()
        row_by_term_id = {
            str(row[0]): _TermReader._convert_db_row_to_term_row(
                row, score=score_by_term_id[str(row[0])]
            )
            for row in db_rows
        }
        return [
            row_by_term_id[term_id] for term_id in ordered_term_ids if term_id in row_by_term_id
        ]

    def query_term_relations_tree(
        self,
        *,
        term_id: str,
        relation_category: str | None = None,
        direction: str = "both",
        max_depth: int = 3,
    ) -> dict[str, Any]:
        """Query entire relation tree via recursive CTE with term detail JOINs.

        Returns all relations up to ``max_depth`` in a single query, including
        source/target term names, codes, types, and ext_attrs.  Each result
        dict carries ``depth`` (hop distance from root) and ``next_term_id``
        (the newly-discovered endpoint at this edge).
        """
        # direction filtering in the CTE base step
        direction_clause: str
        if direction == "outgoing":
            direction_clause = "tr.source_term_id = :root_id"
            next_expr = "tr.target_term_id"
        elif direction == "incoming":
            direction_clause = "tr.target_term_id = :root_id"
            next_expr = "tr.source_term_id"
        else:
            direction_clause = "(tr.source_term_id = :root_id OR tr.target_term_id = :root_id)"
            next_expr = (
                "CASE WHEN tr.source_term_id = :root_id "
                "THEN tr.target_term_id ELSE tr.source_term_id END"
            )

        # Build category filter clause (avoid NULL parameter type ambiguity)
        cat_filter: str
        cat_param: dict[str, str]
        if relation_category:
            cat_filter = "AND tr.relation_category = :rel_cat"
            cat_param = {"rel_cat": relation_category}
        else:
            cat_filter = ""
            cat_param = {}

        sql = text(f"""
            WITH RECURSIVE bfs AS (
                SELECT
                    tr.relation_id,
                    tr.source_term_id,
                    tr.target_term_id,
                    tr.relation_name,
                    tr.relation_category,
                    1 AS depth,
                    ({next_expr}) AS next_term_id,
                     ARRAY[CAST(:root_id AS varchar)]::varchar[] AS visited_ids
                FROM term_relation tr
                WHERE {direction_clause}
                  {cat_filter}

                UNION ALL

                SELECT
                    tr.relation_id,
                    tr.source_term_id,
                    tr.target_term_id,
                    tr.relation_name,
                    tr.relation_category,
                    b.depth + 1,
                    CASE
                        WHEN tr.source_term_id = b.next_term_id THEN tr.target_term_id
                        ELSE tr.source_term_id
                    END AS next_term_id,
                    b.visited_ids || b.next_term_id
                FROM bfs b
                JOIN term_relation tr
                    ON (tr.source_term_id = b.next_term_id
                        OR tr.target_term_id = b.next_term_id)
                    AND tr.relation_id != b.relation_id
                WHERE b.depth < :max_depth
                  AND NOT (
                      CASE
                          WHEN tr.source_term_id = b.next_term_id THEN tr.target_term_id
                          ELSE tr.source_term_id
                      END
                  ) = ANY(b.visited_ids)
                  {cat_filter}
            )
            SELECT DISTINCT ON (bfs.relation_id)
                bfs.source_term_id,
                bfs.target_term_id,
                bfs.relation_name,
                bfs.relation_category,
                bfs.depth,
                bfs.next_term_id,
                st.term_name   AS source_term_name,
                st.term_code   AS source_term_code,
                st.term_type_code AS source_term_type,
                st.ext_attrs   AS source_ext_attrs,
                tt.term_name   AS target_term_name,
                tt.term_code   AS target_term_code,
                tt.term_type_code AS target_term_type,
                tt.ext_attrs   AS target_ext_attrs
            FROM bfs
            LEFT JOIN term st ON st.term_id = bfs.source_term_id
            LEFT JOIN term tt ON tt.term_id = bfs.target_term_id
            ORDER BY bfs.relation_id, bfs.depth
        """)

        with self._get_session() as session:
            rows = session.execute(
                sql,
                {"root_id": term_id, "max_depth": max_depth, **cat_param},
            ).fetchall()

        data = [
            {
                "source_term_id": str(r[0]) if r[0] else None,
                "target_term_id": str(r[1]) if r[1] else None,
                "relation_name": str(r[2]),
                "relation_category": str(r[3]),
                "depth": int(r[4]),
                "next_term_id": str(r[5]) if r[5] else "",
                "source_term_name": str(r[6]) if r[6] else "",
                "source_term_code": str(r[7]) if r[7] else "",
                "source_term_type": str(r[8]) if r[8] else "",
                "source_ext_attrs": r[9] if isinstance(r[9], dict) else {},
                "target_term_name": str(r[10]) if r[10] else "",
                "target_term_code": str(r[11]) if r[11] else "",
                "target_term_type": str(r[12]) if r[12] else "",
                "target_ext_attrs": r[13] if isinstance(r[13], dict) else {},
            }
            for r in rows
        ]

        total = len(data)
        return {
            "data": data,
            "pageIndex": 1,
            "pageSize": total,
            "totalCount": total,
            "totalPages": 1,
        }

    def query_term_relations_tree_batch(
        self,
        *,
        term_ids: list[str],
        max_depth: int = 3,
        direction: str = "both",
        relation_category: str | None = None,
    ) -> dict[str, Any]:
        """Multi-root recursive CTE — load full subgraph from all seeds in one query.

        Unlike ``query_term_relations_tree`` (single-root, varchar[] visited_ids),
        this method uses ``text[]`` for visited_ids to avoid OpenGauss type-length
        inference issues with ``varchar(1000)[]`` in recursive CTEs.

        Returns same format as ``query_term_relations_tree``.
        """
        if not term_ids:
            return {"data": [], "pageIndex": 1, "pageSize": 0, "totalCount": 0, "totalPages": 0}

        direction_clause: str
        if direction == "outgoing":
            direction_clause = "tr.source_term_id = ANY(:root_ids)"
            next_expr = "tr.target_term_id"
        elif direction == "incoming":
            direction_clause = "tr.target_term_id = ANY(:root_ids)"
            next_expr = "tr.source_term_id"
        else:
            direction_clause = (
                "(tr.source_term_id = ANY(:root_ids) OR tr.target_term_id = ANY(:root_ids))"
            )
            next_expr = (
                "CASE WHEN tr.source_term_id = ANY(:root_ids) "
                "THEN tr.target_term_id ELSE tr.source_term_id END"
            )

        cat_filter: str
        cat_param: dict[str, str]
        if relation_category:
            cat_filter = "AND tr.relation_category = :rel_cat"
            cat_param = {"rel_cat": relation_category}
        else:
            cat_filter = ""
            cat_param = {}

        sql = text(f"""
            WITH RECURSIVE bfs AS (
                SELECT
                    tr.relation_id,
                    tr.source_term_id,
                    tr.target_term_id,
                    tr.relation_name,
                    1 AS depth,
                    ({next_expr}) AS next_term_id,
                    ARRAY[CAST(tr.source_term_id AS text), CAST(tr.target_term_id AS text)]::text[] AS visited_ids
                FROM term_relation tr
                WHERE {direction_clause}
                  {cat_filter}

                UNION ALL

                SELECT
                    tr.relation_id,
                    tr.source_term_id,
                    tr.target_term_id,
                    tr.relation_name,
                    b.depth + 1,
                    CASE
                        WHEN tr.source_term_id = b.next_term_id THEN tr.target_term_id
                        ELSE tr.source_term_id
                    END AS next_term_id,
                    b.visited_ids || CAST(b.next_term_id AS text)
                FROM bfs b
                JOIN term_relation tr
                    ON (tr.source_term_id = b.next_term_id
                        OR tr.target_term_id = b.next_term_id)
                    AND tr.relation_id != b.relation_id
                WHERE b.depth < :max_depth
                  AND NOT (
                      CASE
                          WHEN tr.source_term_id = b.next_term_id THEN tr.target_term_id
                          ELSE tr.source_term_id
                      END
                  ) = ANY(b.visited_ids)
                  {cat_filter}
            )
            SELECT DISTINCT ON (bfs.relation_id)
                bfs.source_term_id,
                bfs.target_term_id,
                bfs.relation_name,
                bfs.depth,
                bfs.next_term_id,
                st.term_name   AS source_term_name,
                st.term_code   AS source_term_code,
                st.term_type_code AS source_term_type,
                st.ext_attrs   AS source_ext_attrs,
                tt.term_name   AS target_term_name,
                tt.term_code   AS target_term_code,
                tt.term_type_code AS target_term_type,
                tt.ext_attrs   AS target_ext_attrs
            FROM bfs
            LEFT JOIN term st ON st.term_id = bfs.source_term_id
            LEFT JOIN term tt ON tt.term_id = bfs.target_term_id
            ORDER BY bfs.relation_id, bfs.depth
        """)

        with self._get_session() as session:
            rows = session.execute(
                sql,
                {"root_ids": term_ids, "max_depth": max_depth, **cat_param},
            ).fetchall()

        data = [
            {
                "source_term_id": str(r[0]) if r[0] else None,
                "target_term_id": str(r[1]) if r[1] else None,
                "relation_name": str(r[2]),
                "relation_category": "",
                "depth": int(r[3]),
                "next_term_id": str(r[4]) if r[4] else "",
                "source_term_name": str(r[5]) if r[5] else "",
                "source_term_code": str(r[6]) if r[6] else "",
                "source_term_type": str(r[7]) if r[7] else "",
                "source_ext_attrs": r[8] if isinstance(r[8], dict) else {},
                "target_term_name": str(r[9]) if r[9] else "",
                "target_term_code": str(r[10]) if r[10] else "",
                "target_term_type": str(r[11]) if r[11] else "",
                "target_ext_attrs": r[12] if isinstance(r[12], dict) else {},
            }
            for r in rows
        ]

        total = len(data)
        return {
            "data": data,
            "pageIndex": 1,
            "pageSize": total,
            "totalCount": total,
            "totalPages": 1,
        }

    def query_term_relations(
        self,
        *,
        term_id: str,
        relation_category: str | None = None,
        direction: str = "both",
        depth: int = 1,
        keyword: str | None = None,
        term_type_codes: list[str] | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Query term relations via recursive or direct lookup with pagination.

        Args:
            term_id: Core term ID.
            relation_category: Optional relation category filter.
            direction: "outgoing", "incoming", or "both" (default).
            depth: Recursion depth (1 = direct only).
            keyword: Optional keyword, searches relation_name (ILIKE).
            term_type_codes: Optional list of term_type_code filters on the
                *neighbor* term (the endpoint opposite to the given term_id).
                Any matching type keeps the relation (SQL IN).  Applied at the
                SQL layer via JOIN on the ``term`` table:
                - outgoing → filter target term type
                - incoming → filter source term type
                - both     → (source==term_id AND target.type IN ttc)
                             OR (target==term_id AND source.type IN ttc)
                None / empty list behaves exactly as before (no JOIN, no filter);
                elements are stripped and blank strings dropped.
            page_index: 1-based page number (default 1).
            page_size: Items per page (default 20, max 100).

        Returns:
            Dict with ``data``, ``pageIndex``, ``pageSize``, ``totalCount``, ``totalPages``.
            Each relation includes source/target term names.
        """
        page_size = min(page_size, 100)
        offset = (page_index - 1) * page_size

        with self._get_session() as session:
            filters: list[Any] = []
            params: dict[str, Any] = {}

            if direction == "outgoing":
                filters.append(TermRelation.source_term_id == term_id)
            elif direction == "incoming":
                filters.append(TermRelation.target_term_id == term_id)
            else:
                filters.append(
                    or_(
                        TermRelation.source_term_id == term_id,
                        TermRelation.target_term_id == term_id,
                    )
                )
            if relation_category:
                filters.append(TermRelation.relation_category == relation_category)
            if keyword and keyword.strip():
                filters.append(text("term_relation.relation_name ILIKE :kw"))
                params["kw"] = f"%{keyword.strip()}%"

            # SQL 层 JOIN term 表按"邻居端" term_type_codes IN 过滤（禁止 Python 层过滤）。
            # 未传 / 空列表 / 全空串时保持零 JOIN，行为与改造前完全一致。
            joins: list[tuple[Any, Any]] = []
            neighbor_type_codes = [c.strip() for c in (term_type_codes or []) if c and c.strip()]
            if neighbor_type_codes:
                if direction == "outgoing":
                    neighbor_term = aliased(Term)
                    joins.append(
                        (neighbor_term, neighbor_term.term_id == TermRelation.target_term_id)
                    )
                    filters.append(neighbor_term.term_type_code.in_(neighbor_type_codes))
                elif direction == "incoming":
                    neighbor_term = aliased(Term)
                    joins.append(
                        (neighbor_term, neighbor_term.term_id == TermRelation.source_term_id)
                    )
                    filters.append(neighbor_term.term_type_code.in_(neighbor_type_codes))
                else:
                    target_alias = aliased(Term)
                    source_alias = aliased(Term)
                    joins.append(
                        (target_alias, target_alias.term_id == TermRelation.target_term_id)
                    )
                    joins.append(
                        (source_alias, source_alias.term_id == TermRelation.source_term_id)
                    )
                    filters.append(
                        or_(
                            and_(
                                TermRelation.source_term_id == term_id,
                                target_alias.term_type_code.in_(neighbor_type_codes),
                            ),
                            and_(
                                TermRelation.target_term_id == term_id,
                                source_alias.term_type_code.in_(neighbor_type_codes),
                            ),
                        )
                    )

            where_clause = and_(*filters) if filters else text("1=1")

            # count 与主查询必须使用同一组 JOIN + 过滤条件，保证 totalCount 一致
            count_stmt = select(func.count()).select_from(TermRelation)
            for entity, onclause in joins:
                count_stmt = count_stmt.outerjoin(entity, onclause)
            total = int(
                session.execute(
                    count_stmt.where(where_clause),
                    params,
                ).scalar_one()
            )

            if total == 0:
                return {
                    "data": [],
                    "pageIndex": page_index,
                    "pageSize": page_size,
                    "totalCount": 0,
                    "totalPages": 0,
                }

            stmt = select(
                TermRelation.relation_id,
                TermRelation.source_term_id,
                TermRelation.target_term_id,
                TermRelation.relation_name,
                TermRelation.relation_category,
                TermRelation.cardinality,
                TermRelation.created_time,
                TermRelation.updated_time,
            )
            for entity, onclause in joins:
                stmt = stmt.outerjoin(entity, onclause)
            rows = session.execute(
                stmt.where(where_clause)
                .order_by(TermRelation.updated_time.desc().nulls_last())
                .limit(page_size)
                .offset(offset),
                params,
            ).all()

            # Collect all term_ids for batch name resolution
            term_ids: set[str] = set()
            for r_ in rows:
                if r_[1]:
                    term_ids.add(str(r_[1]))
                if r_[2]:
                    term_ids.add(str(r_[2]))

            term_info_map = self._batch_get_term_infos(session, term_ids)

        data = [
            {
                "relation_id": str(r[0]),
                "source_term_id": str(r[1]) if r[1] else None,
                "target_term_id": str(r[2]) if r[2] else None,
                "relation_name": str(r[3]),
                "relation_category": str(r[4]),
                "cardinality": str(r[5]) if r[5] else None,
                "source_term_name": term_info_map.get(str(r[1]), {}).get("name") if r[1] else None,
                "target_term_name": term_info_map.get(str(r[2]), {}).get("name") if r[2] else None,
                "source_term_code": term_info_map.get(str(r[1]), {}).get("code") if r[1] else None,
                "target_term_code": term_info_map.get(str(r[2]), {}).get("code") if r[2] else None,
                "created_time": r[6].isoformat() if r[6] is not None else None,
                "updated_time": r[7].isoformat() if r[7] is not None else None,
            }
            for r in rows
        ]

        return {
            "data": data,
            "pageIndex": page_index,
            "pageSize": page_size,
            "totalCount": total,
            "totalPages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }

    # ── Flat edge loading (no CTE, no recursion) ──────────────────────

    def query_edges_by_kb_id(
        self,
        *,
        kb_ids: list[str],
        limit: int = 2000,
        relation_category: str | None = None,
    ) -> dict[str, Any]:
        """Flat query: load all edges where either endpoint belongs to any kb_id.

        Replaces recursive CTE for the bridge-node computation.  Single
        scan of term_relation + term with ext_attrs->>'kb_id' filter.
        """
        if not kb_ids:
            return {"data": []}

        cat_clause = ""
        cat_param: dict[str, str] = {}
        if relation_category:
            cat_clause = "AND tr.relation_category = :rel_cat"
            cat_param = {"rel_cat": relation_category}

        sql = text(f"""
            SELECT
                tr.source_term_id,
                tr.target_term_id,
                tr.relation_name,
                st.term_name           AS source_term_name,
                st.term_type_code      AS source_term_type,
                st.ext_attrs           AS source_ext_attrs,
                tt.term_name           AS target_term_name,
                tt.term_type_code      AS target_term_type,
                tt.ext_attrs           AS target_ext_attrs
            FROM term_relation tr
            JOIN term st ON st.term_id = tr.source_term_id
            JOIN term tt ON tt.term_id = tr.target_term_id
            WHERE (st.ext_attrs->>'kb_id' = ANY(:kb_ids)
               OR tt.ext_attrs->>'kb_id' = ANY(:kb_ids))
              {cat_clause}
            ORDER BY tr.relation_id
            LIMIT :limit
        """)

        with self._get_session() as session:
            rows = session.execute(
                sql,
                {"kb_ids": list(kb_ids), "limit": limit, **cat_param},
            ).fetchall()

        data = [
            {
                "source_term_id": str(r[0]) if r[0] else None,
                "target_term_id": str(r[1]) if r[1] else None,
                "relation_name": str(r[2]),
                "source_term_name": str(r[3]) if r[3] else "",
                "source_term_type": str(r[4]) if r[4] else "",
                "source_ext_attrs": r[5] if isinstance(r[5], dict) else {},
                "target_term_name": str(r[6]) if r[6] else "",
                "target_term_type": str(r[7]) if r[7] else "",
                "target_ext_attrs": r[8] if isinstance(r[8], dict) else {},
            }
            for r in rows
        ]

        return {"data": data}

    # ── end of _TermReader ────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════════
# filters 通道白名单映射（query_terms_by_labels）
#
# key = FilterSpec["field"]；value = (SQL 列表达式, 值归一化器或 None)。
# - SQL 列表达式**只**从本表取值（注入面控制：禁止任何动态拼接；
#   新增维度 = 映射表 +1 行 + 协议 Literal 同步 + Spec 修订 + 验收测试）；
# - term_type_code 维度值经 _TermReader._normalize_type_code 归一化（与独立
#   参数 term_type_codes 同一函数、同一时机——组装前统一归一化）；
# - kb 三键为原始字符串 ID，不归一化（None）。
# ═══════════════════════════════════════════════════════════════════════════════

_FILTER_FIELD_MAP: dict[str, tuple[str, Callable[[str], str] | None]] = {
    "kb_id": ("t.ext_attrs->>'kb_id'", None),
    "kb_resource_id": ("t.ext_attrs->>'kb_resource_id'", None),
    "kb_file_path": ("t.term_tags->>'kb_file_path'", None),
    "term_type_code": ("t.term_type_code", _TermReader._normalize_type_code),
}
