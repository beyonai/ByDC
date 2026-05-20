"""PostgresTermReader — 基于 PostgreSQL 的 TermReader 协议实现。

从 ``term_search.py`` 提取所有无副作用查询逻辑，以类形式封装，
接受 session 工厂实现完整的 TermReader 协议（8 个方法）。
中文注释，类型标注完备，可直接用于生产环境。

协议方法：
- search_terms           按术语类型检索术语列表（支持关键词、标签过滤、BM25 兜底）
- get_term_by_ids        批量根据三元组查询 term_id
- get_term_names         批量查询术语的所有名称（标准名 + 别名）
- resolve_field_aliases  轻量级字段别名精确消歧（可选值消歧）
- resolve_value_aliases  轻量级属性值精确消歧
- get_object_props       批量查询对象/视图下的属性
- get_prop_values_with_aliases  批量查询对象下属性的值术语及其别名
- get_prop_enum_values   查询指定 prop 的枚举值
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, bindparam, cast, func, literal, or_, select, text
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC, TIMESTAMP
from sqlalchemy.orm import Session, aliased

from datacloud_knowledge.adapters.opengauss._db.connection import get_session
from datacloud_knowledge.adapters.opengauss._db.models import (
    Term,
    TermName,
    TermRelation,
)
from datacloud_knowledge.adapters.opengauss.bm25 import bm25_search_with_or
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
    owl_doc_id: str | None
    created_time: Any | None
    updated_time: Any | None
    score: float | None = None


class PostgresTermReader:
    """基于 PostgreSQL 的术语读取实现。

    实现 TermReader 协议的全部 8 个只读方法，所有查询无副作用。
    通过构造函数注入 session 工厂来管理 DB 会话生命周期，
    默认使用 ``get_session`` 上下文管理器。

    Usage::

        reader = PostgresTermReader()
        result = reader.search_terms(term_type_code="view", keyword="客户")
        names = reader.get_term_names(term_ids=["term_001", "term_002"])
    """

    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ) -> None:
        """初始化读取器。

        Args:
            session_factory: 返回 session 上下文管理器的可调用对象。
                传入 None 则默认使用 ``get_session``。
        """
        self._session_factory: Callable[[], AbstractContextManager[Session]] = (
            session_factory if session_factory is not None else get_session
        )

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
            with self._session_factory() as session:
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
                        Term.owl_doc_id,
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
                    owl_doc_id=row.owl_doc_id,
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
            with self._session_factory() as session:
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
                            Term.owl_doc_id,
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
                    owl_doc_id=row.owl_doc_id,
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
            with self._session_factory() as session:
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
            with self._session_factory() as session:
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
        和可选值别名（child term 的 term_name/TermName 别名）。

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
            with self._session_factory() as session:
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
                        .join(child, child.parent_term_id == prop.term_id)
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
                        .join(child2, child2.parent_term_id == prop2.term_id)
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
        ``view/object → HAS_FIELD → prop → (parent_term_id) → child term``
        查找值术语，并在 child term 的 ``term_name`` 和 ``TermName.name_text``（别名）
        中精确匹配输入 terms。

        Args:
            terms: 待匹配的值列表（如企业名、地区名等）。
            scope_code: 视图或对象 code（如 "scene_enterprise_analysis"）。

        Returns:
            ValueResolutionResult，包含 matched（已知值）和 unmatched（未知值）。
        """
        terms_list = list(terms)
        if not terms_list or not scope_code:
            return ValueResolutionResult(unmatched=terms_list)

        unique_terms = list(dict.fromkeys(terms_list))
        global_scope: dict[str, str] = {"scope": "global"}

        view_obj = aliased(Term, name="view_obj")
        prop = aliased(Term, name="prop")
        child = aliased(Term, name="child")

        try:
            with self._session_factory() as session:
                # Step 1: 通过 child.term_name 直接匹配
                direct_rows = session.execute(
                    select(child.term_name)
                    .select_from(view_obj)
                    .join(
                        TermRelation,
                        TermRelation.source_term_id == view_obj.term_id,
                    )
                    .join(prop, prop.term_id == TermRelation.target_term_id)
                    .join(child, child.parent_term_id == prop.term_id)
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
                            TermRelation,
                            TermRelation.source_term_id == view_obj.term_id,
                        )
                        .join(prop, prop.term_id == TermRelation.target_term_id)
                        .join(child, child.parent_term_id == prop.term_id)
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
        source_term_ids_list = list(source_term_ids)
        if not source_term_ids_list:
            return {}

        try:
            with self._session_factory() as session:
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
        if not scope_code:
            return []

        with self._session_factory() as session:
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

        路径: source → (HAS_FIELD) → prop → (parent_term_id) → child term。

        Args:
            source_term_ids: 源术语 ID 列表。

        Returns:
            {source_term_id → [ValueWithAliases]} 映射。每个 source_term_id 至少包含一个空列表。
        """
        source_term_ids_list = list(source_term_ids)
        if not source_term_ids_list:
            return {}

        prop = aliased(Term, name="prop")
        child = aliased(Term, name="child")

        try:
            with self._session_factory() as session:
                child_rows = session.execute(
                    select(
                        TermRelation.source_term_id,
                        child.parent_term_id,
                        child.term_id,
                        child.term_code,
                        child.term_name,
                    )
                    .join(prop, prop.term_id == TermRelation.target_term_id)
                    .join(child, child.parent_term_id == prop.term_id)
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
        for source_id, parent_term_id, term_id, term_code, term_name in child_rows:
            result.setdefault(str(source_id), []).append(
                ValueWithAliases(
                    parent_term_id=str(parent_term_id),
                    term_id=str(term_id),
                    term_code=str(term_code),
                    term_name=str(term_name),
                    aliases=alias_map.get(str(term_id), []),
                )
            )
        return result

    def get_prop_enum_values(
        self, *, scope_code: str, field_codes: Sequence[str]
    ) -> dict[str, list[str]]:
        """查询指定 prop 的枚举值（child term_name + 别名）。

        路径: view/object(scope_code) → HAS_FIELD → prop(field_code) → child terms。
        child term 的 term_name 和 TermName 别名均作为枚举值返回。

        Args:
            scope_code: 视图或对象 code。
            field_codes: 待查询的 prop term_code 列表。

        Returns:
            {field_code → [枚举值列表]}，去重保序。未命中 field_code 的值为空列表。
        """
        field_codes_list = list(field_codes)
        if not scope_code or not field_codes_list:
            return {}

        unique_codes = list(dict.fromkeys(field_codes_list))

        view_obj = aliased(Term, name="view_obj")
        prop = aliased(Term, name="prop")
        child = aliased(Term, name="child")

        try:
            with self._session_factory() as session:
                # 查询 child term_name（直接值）
                direct_rows = session.execute(
                    select(
                        prop.term_code.label("field_code"),
                        child.term_name.label("value_name"),
                        child.term_id.label("child_id"),
                    )
                    .select_from(view_obj)
                    .join(TermRelation, TermRelation.source_term_id == view_obj.term_id)
                    .join(prop, prop.term_id == TermRelation.target_term_id)
                    .join(child, child.parent_term_id == prop.term_id)
                    .where(
                        view_obj.term_code == scope_code,
                        view_obj.term_type_code.in_(["view", "object"]),
                        prop.term_type_code == "prop",
                        prop.term_code.in_(unique_codes),
                    )
                ).all()

                # 收集 child term_id → field_code 映射
                child_to_field: dict[str, str] = {}
                result_raw: dict[str, list[str]] = {code: [] for code in unique_codes}
                for field_code, value_name, child_id in direct_rows:
                    fc = str(field_code)
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
        if source_term_id == target_term_id:
            return 0
        if max_depth <= 0:
            return None

        try:
            with self._session_factory() as session:
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
            with self._session_factory() as session:
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
        try:
            with self._session_factory() as session:
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
        try:
            with self._session_factory() as session:
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
            with self._session_factory() as session:
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
        if not categories:
            return set()
        try:
            with self._session_factory() as session:
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
            with self._session_factory() as session:
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
        if not field_codes:
            return ()
        try:
            with self._session_factory() as session:
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

    def get_relation_target_ids(self, *, source_term_ids: Sequence[str]) -> Sequence[str]:
        """查询给定源术语的所有目标术语 ID（distinct）。"""
        if not source_term_ids:
            return ()
        try:
            with self._session_factory() as session:
                rows = session.execute(
                    text(
                        "SELECT DISTINCT target_term_id FROM term_relation "
                        "WHERE source_term_id IN :ids"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"ids": tuple(source_term_ids)},
                ).fetchall()
        except Exception:
            logger.exception("get_relation_target_ids failed: source_ids=%s", source_term_ids)
            raise
        return tuple(str(r.target_term_id) for r in rows)

    def get_terms_batch_raw(self, *, term_ids: Sequence[str]) -> Sequence[dict[str, str | None]]:
        """批量查询术语的基本字段（term_id, term_name, term_type_code, owl_doc_id）。"""
        if not term_ids:
            return ()
        try:
            with self._session_factory() as session:
                rows = session.execute(
                    text(
                        "SELECT term_id, term_name, term_type_code, owl_doc_id "
                        "FROM term WHERE term_id IN :ids"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"ids": tuple(term_ids)},
                ).fetchall()
        except Exception:
            logger.exception("get_terms_batch_raw failed: ids=%s", term_ids)
            raise
        return tuple(
            {
                "term_id": str(r.term_id),
                "term_name": str(r.term_name),
                "term_type_code": str(r.term_type_code),
                "owl_doc_id": None if r.owl_doc_id is None else str(r.owl_doc_id),
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
            with self._session_factory() as session:
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
            with self._session_factory() as session:
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
            with self._session_factory() as session:
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
            filters.extend(PostgresTermReader._tag_filter_expr(tf) for tf in tags)

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
            owl_doc_id=row[6],
            created_time=row[7],
            updated_time=row[8],
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
                Term.owl_doc_id,
                Term.created_time,
                Term.updated_time,
            ).where(Term.term_id.in_(ordered_term_ids), *filters)
        ).all()
        row_by_term_id = {
            str(row[0]): PostgresTermReader._convert_db_row_to_term_row(
                row, score=score_by_term_id[str(row[0])]
            )
            for row in db_rows
        }
        return [
            row_by_term_id[term_id] for term_id in ordered_term_ids if term_id in row_by_term_id
        ]

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
        unique_field_terms = list(dict.fromkeys(terms)) if terms else []
        if not scope_code or not unique_field_terms:
            return FieldResolutionResultWithNames(unresolved=list(unique_field_terms))

        view_scope = {"scope": "view", "code": scope_code}
        obj_scope = {"scope": "object", "code": scope_code}
        global_scope = {"scope": "global"}

        try:
            with self._session_factory() as session:
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
