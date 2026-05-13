from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC, TIMESTAMP
from sqlalchemy.orm import aliased

from datacloud_knowledge.db.connection import get_session
from datacloud_knowledge.db.models import Term, TermName, TermRelation
from datacloud_knowledge.search import bm25_search_with_or

from datacloud_knowledge.api.types import (
    AmbiguousCandidate,
    FieldResolutionResult,
    FieldResolutionResultWithNames,
    NameItem,
    PropItem,
    ResolvedField,
    SearchTermsResult,
    TagFilter,
    TermItem,
    ValueResolutionResult,
    ValueWithAliases,
)

logger = logging.getLogger(__name__)


@contextmanager
def _maybe_session(session: Any = None) -> Any:
    """Return *session* if provided, otherwise yield from ``get_session()``."""
    if session is not None:
        yield session
    else:
        with get_session() as sess:
            yield sess


@dataclass(frozen=True, slots=True)
class _TermSearchRow:
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


def search_terms_by_type(
    *,
    term_type_code: str,
    term_codes: list[str] | None = None,
    keyword: str | None = None,
    tags: list[TagFilter] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str = "relevance",
    db_session: Any = None,
) -> SearchTermsResult:
    if not (1 <= limit <= 200):
        raise ValueError("limit 必须在 1..200")
    if offset < 0:
        raise ValueError("offset 必须 >= 0")

    canonical_type = _normalize_type_code(term_type_code)
    normalized_keyword = (keyword or "").strip()

    try:
        with _maybe_session(db_session) as session:
            base_filters = _build_filters(
                canonical_type=canonical_type,
                term_codes=term_codes,
                keyword=keyword,
                tags=tags,
            )
            bm25_filters = _build_filters(
                canonical_type=canonical_type,
                term_codes=term_codes,
                keyword=None,
                tags=tags,
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
                stmt = _apply_order_by(stmt, order_by=order_by)
                rows = [_convert_db_row_to_term_row(row) for row in session.execute(stmt).all()]
            elif normalized_keyword:
                bm25_rows = bm25_search_with_or(
                    session,
                    normalized_keyword,
                    top_k=limit + offset,
                    min_score=0.001,
                    term_type_codes={canonical_type},
                )
                rows = _convert_bm25_rows_to_term_rows(
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
            "search_terms_by_type failed: term_type_code=%s, term_codes=%s, keyword=%s, tags=%s, limit=%s, offset=%s",
            term_type_code,
            term_codes,
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


def _convert_db_row_to_term_row(row: Any, *, score: float | None = None) -> _TermSearchRow:
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


def _convert_bm25_rows_to_term_rows(
    *,
    session: Any,
    bm25_rows: list[Any],
    filters: list[Any],
) -> list[_TermSearchRow]:
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
        str(row[0]): _convert_db_row_to_term_row(row, score=score_by_term_id[str(row[0])])
        for row in db_rows
    }
    return [row_by_term_id[term_id] for term_id in ordered_term_ids if term_id in row_by_term_id]


def _normalize_type_code(type_code: str) -> str:
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


def _build_filters(
    *,
    canonical_type: str,
    term_codes: list[str] | None,
    keyword: str | None,
    tags: list[TagFilter] | None,
) -> list[Any]:
    filters: list[Any] = [Term.term_type_code == canonical_type]

    if term_codes:
        filters.append(Term.term_id.in_(term_codes))

    normalized_keyword = (keyword or "").strip()
    if normalized_keyword:
        filters.append(
            or_(
                Term.term_name == normalized_keyword,
                Term.term_code == normalized_keyword,
            )
        )

    if tags:
        filters.extend(_tag_filter_expr(tf) for tf in tags)

    return filters


def _tag_filter_expr(tf: TagFilter) -> Any:
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


def _apply_order_by(stmt: Any, *, order_by: str) -> Any:
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


def get_term_ids(
    *,
    keys: list[tuple[str, str, str]],
    db_session: Any = None,
) -> dict[tuple[str, str, str], str]:
    """批量根据 (library_id, term_type_code, term_code) 三元组查询 term_id。"""
    if not keys:
        return {}

    try:
        with _maybe_session(db_session) as session:
            conditions = [
                and_(
                    Term.library_id == library_id,
                    Term.term_type_code == term_type_code,
                    Term.term_code == term_code,
                )
                for library_id, term_type_code, term_code in keys
            ]
            rows = session.execute(
                select(Term.library_id, Term.term_type_code, Term.term_code, Term.term_id).where(
                    or_(*conditions)
                )
            ).all()
    except Exception:
        logger.exception("get_term_ids failed: keys=%s", keys)
        raise

    return {(str(row[0]), str(row[1]), str(row[2])): str(row[3]) for row in rows}


def get_object_props(
    *,
    source_term_ids: list[str],
    db_session: Any = None,
) -> dict[str, list[PropItem]]:
    """批量查询对象/视图下的属性（通过 term_relation HAS_FIELD）。"""
    if not source_term_ids:
        return {}

    try:
        with _maybe_session(db_session) as session:
            rows = session.execute(
                select(
                    TermRelation.source_term_id,
                    Term.term_id,
                    Term.term_code,
                    Term.term_name,
                )
                .join(Term, Term.term_id == TermRelation.target_term_id)
                .where(
                    TermRelation.source_term_id.in_(source_term_ids),
                    Term.term_type_code == "prop",
                )
            ).all()
    except Exception:
        logger.exception("get_object_props failed: source_term_ids=%s", source_term_ids)
        raise

    result: dict[str, list[PropItem]] = {source_term_id: [] for source_term_id in source_term_ids}
    for source_id, term_id, term_code, term_name in rows:
        result.setdefault(str(source_id), []).append(
            PropItem(term_id=str(term_id), term_code=str(term_code), term_name=str(term_name))
        )
    return result


def get_term_names(
    *,
    term_ids: list[str],
    scope_filter: dict[str, str] | None = None,
    db_session: Any = None,
) -> dict[str, list[NameItem]]:
    """批量查询术语的所有名称（标准名 + 别名），通用函数。"""
    if not term_ids:
        return {}

    try:
        with _maybe_session(db_session) as session:
            filters: list[Any] = [TermName.term_id.in_(term_ids)]
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
            "get_term_names failed: term_ids=%s, scope_filter=%s", term_ids, scope_filter
        )
        raise

    result: dict[str, list[NameItem]] = {term_id: [] for term_id in term_ids}
    for term_id, name_text, is_primary in rows:
        result.setdefault(str(term_id), []).append(
            NameItem(name_text=str(name_text), is_primary=bool(is_primary))
        )
    return result


def get_prop_values_with_aliases(
    *,
    source_term_ids: list[str],
    db_session: Any = None,
) -> dict[str, list[ValueWithAliases]]:
    """批量查询对象下属性的值术语及其别名。

    路径: source → (HAS_FIELD) → prop → (parent_term_id) → child term
    """
    if not source_term_ids:
        return {}

    prop = aliased(Term, name="prop")
    child = aliased(Term, name="child")

    try:
        with _maybe_session(db_session) as session:
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
                    TermRelation.source_term_id.in_(source_term_ids),
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
        logger.exception("get_prop_values_with_aliases failed: source_term_ids=%s", source_term_ids)
        raise

    alias_map: dict[str, list[str]] = {}
    for term_id, name_text in alias_rows:
        alias_map.setdefault(str(term_id), []).append(str(name_text))

    result: dict[str, list[ValueWithAliases]] = {
        source_term_id: [] for source_term_id in source_term_ids
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


def resolve_field_aliases(
    *,
    terms: list[str],
    scope_code: str,
    library_id: str | None = None,
    user_id: str | None = None,
    resolve_values: bool = False,
    value_terms: list[str] | None = None,
    db_session: Any = None,
) -> FieldResolutionResult:
    """轻量级字段 + 值别名精确消歧（单次 SQL）。

    通过 UNION 将字段别名查询和值 child term 查询合并为一条 SQL，
    用 ``match_type`` 列区分来源，Python 侧分拣结果。

    字段消歧：在 ``term_name`` 表中按 ``search_scope`` 过滤，
    精确匹配 ``name_text → prop term_code``。

    值消歧（``resolve_values=True``）：通过
    ``view/object → HAS_FIELD → prop → child term`` 关系链路，
    在 child term 的 ``term_name`` 和 ``TermName.name_text`` 中精确匹配。

    Args:
        terms: 待解析的字段中文名/别名列表。
        scope_code: 视图或对象 code（如 ``"scene_enterprise_analysis"``）。
        library_id: 预留参数，v1 不使用。
        resolve_values: 是否对 value_terms 追加值级别消歧。
        value_terms: 待值消歧的过滤值列表（如企业名、地区名等）。

    Returns:
        FieldResolutionResult，包含 resolved / ambiguous / unresolved 三类结果。
    """
    _ = library_id  # reserved for future use

    effective_values = value_terms or []
    if not scope_code or (not terms and not effective_values):
        all_unresolved = list(terms or []) + list(effective_values)
        return FieldResolutionResult(unresolved=all_unresolved)

    unique_field_terms = list(dict.fromkeys(terms)) if terms else []
    unique_value_terms = list(dict.fromkeys(effective_values)) if effective_values else []

    view_scope = {"scope": "view", "code": scope_code}
    obj_scope = {"scope": "object", "code": scope_code}
    global_scope = {"scope": "global"}
    user_scope = {"scope_user_id": user_id} if user_id else None

    try:
        with _maybe_session(db_session) as session:
            # ── 构建 UNION 查询 ───────────────────────────────────────────────
            queries = []

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
                            TermName.search_scope.contains(user_scope)
                            if user_scope
                            else literal(False),
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
                            TermName.search_scope.contains(user_scope)
                            if user_scope
                            else literal(False),
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

    # ── 分拣结果 ──────────────────────────────────────────────────────────────
    # 字段消歧：{name_text → {term_code → (term_name, scope)}}
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
    *,
    terms: list[str],
    scope_code: str,
    user_id: str | None = None,
    db_session: Any = None,
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

    Returns:
        ValueResolutionResult，包含 matched（已知值）和 unmatched（未知值）。
    """
    if not terms or not scope_code:
        return ValueResolutionResult(unmatched=list(terms) if terms else [])

    unique_terms = list(dict.fromkeys(terms))
    global_scope = {"scope": "global"}
    user_scope = {"scope_user_id": user_id} if user_id else None

    # 找到 scope_code 对应的 view/object term_id
    view_obj = aliased(Term, name="view_obj")
    prop = aliased(Term, name="prop")
    child = aliased(Term, name="child")

    try:
        with _maybe_session(db_session) as session:
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
                            TermName.search_scope.contains(user_scope)
                            if user_scope
                            else literal(False),
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


def resolve_field_aliases_with_names(
    *,
    terms: list[str],
    scope_code: str,
    library_id: str | None = None,
    user_id: str | None = None,
    resolve_values: bool = False,
    value_terms: list[str] | None = None,
    db_session: Any = None,
) -> FieldResolutionResultWithNames:
    """扩展版字段别名消歧：resolved 同时返回 term_name。

    与 ``resolve_field_aliases`` 共享 SQL 逻辑，区别仅在于
    resolved 字典的 value 类型为 ``ResolvedField(term_code, term_name)``
    而非纯 ``str``。

    Args:
        terms: 待解析的字段中文名/别名列表。
        scope_code: 视图或对象 code。
        library_id: 预留参数，v1 不使用。
        resolve_values: 是否对 value_terms 追加值级别消歧。
        value_terms: 待值消歧的过滤值列表。

    Returns:
        FieldResolutionResultWithNames。
    """
    _ = library_id

    effective_values = value_terms or []
    if not scope_code or (not terms and not effective_values):
        all_unresolved = list(terms or []) + list(effective_values)
        return FieldResolutionResultWithNames(unresolved=all_unresolved)

    unique_field_terms = list(dict.fromkeys(terms)) if terms else []
    unique_value_terms = list(dict.fromkeys(effective_values)) if effective_values else []

    view_scope = {"scope": "view", "code": scope_code}
    obj_scope = {"scope": "object", "code": scope_code}
    global_scope = {"scope": "global"}
    user_scope = {"scope_user_id": user_id} if user_id else None

    try:
        with _maybe_session(db_session) as session:
            queries = []

            if unique_field_terms:
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
                            TermName.search_scope.contains(user_scope)
                            if user_scope
                            else literal(False),
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

            if resolve_values and unique_value_terms:
                view_obj = aliased(Term, name="view_obj")
                prop = aliased(Term, name="prop")
                child = aliased(Term, name="child")

                _null_scope = cast(literal(None), JSONB)

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
                    )
                )
                queries.append(val_alias_q)

            if not queries:
                all_unresolved = unique_field_terms + unique_value_terms
                return FieldResolutionResultWithNames(unresolved=all_unresolved)

            stmt = queries[0].union_all(*queries[1:]) if len(queries) > 1 else queries[0]
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

    if resolve_values and unique_value_terms:
        if value_matched:
            logger.info(
                "[resolve_field_aliases_with_names] value_aliases: matched=%d unmatched=%d",
                len(value_matched),
                len(unique_value_terms) - len(value_matched),
            )
        unresolved.extend(t for t in unique_value_terms if t not in value_matched)
    elif unique_value_terms:
        unresolved.extend(unique_value_terms)

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


def get_prop_enum_values(
    *,
    scope_code: str,
    field_codes: list[str],
    db_session: Any = None,
) -> dict[str, list[str]]:
    """查询指定 prop 的枚举值（child term_name + 别名）。

    路径: view/object(scope_code) → HAS_FIELD → prop(field_code) → child terms
    child term 的 term_name 和 TermName 别名均作为枚举值返回。

    Args:
        scope_code: 视图或对象 code。
        field_codes: 待查询的 prop term_code 列表。

    Returns:
        {field_code: [枚举值列表]}，去重保序。
    """
    if not scope_code or not field_codes:
        return {}

    unique_codes = list(dict.fromkeys(field_codes))

    view_obj = aliased(Term, name="view_obj")
    prop = aliased(Term, name="prop")
    child = aliased(Term, name="child")

    try:
        with _maybe_session(db_session) as session:
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
