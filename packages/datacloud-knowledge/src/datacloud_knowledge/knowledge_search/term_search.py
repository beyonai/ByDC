from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import NUMERIC, TIMESTAMP
from sqlalchemy.orm import aliased

from .db import get_session
from .db.models import Term, TermName, TermRelation
from .types import NameItem, PropItem, SearchTermsResult, TagFilter, TermItem, ValueWithAliases

logger = logging.getLogger(__name__)


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
    if not (1 <= limit <= 200):
        raise ValueError("limit 必须在 1..200")
    if offset < 0:
        raise ValueError("offset 必须 >= 0")

    canonical_type = _normalize_type_code(term_type_code)

    try:
        with get_session() as session:
            base_filters = _build_filters(
                canonical_type=canonical_type,
                term_codes=term_codes,
                keyword=keyword,
                tags=tags,
            )

            total = int(
                session.execute(
                    select(func.count()).select_from(Term).where(*base_filters)
                ).scalar_one()
            )

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

            rows = session.execute(stmt).all()
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
        term_id = str(row[0])
        term_code = str(row[1])
        term_name = str(row[2])
        ttype = str(row[3])
        desc_summary = row[4]
        term_tags = row[5] or {}
        owl_doc_id = row[6]
        created_time = row[7]
        updated_time = row[8]

        items.append(
            TermItem(
                term_id=term_id,
                term_code=term_code,
                term_name=term_name,
                term_type_code=ttype,
                desc_summary=desc_summary,
                term_tags=term_tags,
                owl_doc_id=owl_doc_id,
                created_time=created_time,
                updated_time=updated_time,
                score=None,
            )
        )

    return SearchTermsResult(total=total, items=items)


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

    if keyword:
        filters.append(func.coalesce(Term.term_name, "").ilike(f"%{keyword}%"))

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
) -> dict[tuple[str, str, str], str]:
    """批量根据 (library_id, term_type_code, term_code) 三元组查询 term_id。"""
    if not keys:
        return {}

    try:
        with get_session() as session:
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
) -> dict[str, list[PropItem]]:
    """批量查询对象/视图下的属性（通过 term_relation HAS_FIELD）。"""
    if not source_term_ids:
        return {}

    try:
        with get_session() as session:
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
) -> dict[str, list[NameItem]]:
    """批量查询术语的所有名称（标准名 + 别名），通用函数。"""
    if not term_ids:
        return {}

    try:
        with get_session() as session:
            rows = session.execute(
                select(
                    TermName.term_id,
                    TermName.name_text,
                    (TermName.name_text == Term.term_name).label("is_primary"),
                )
                .join(Term, Term.term_id == TermName.term_id)
                .where(TermName.term_id.in_(term_ids))
            ).all()
    except Exception:
        logger.exception("get_term_names failed: term_ids=%s", term_ids)
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
) -> dict[str, list[ValueWithAliases]]:
    """批量查询对象下属性的值术语及其别名。

    路径: source → (HAS_FIELD) → prop → (parent_term_id) → child term
    """
    if not source_term_ids:
        return {}

    prop = aliased(Term, name="prop")
    child = aliased(Term, name="child")

    try:
        with get_session() as session:
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
