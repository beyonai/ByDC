from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import NUMERIC, TIMESTAMP

from .db import get_session
from .db.models import Term
from .types import SearchTermsResult, TagFilter, TermItem

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
    if limit <= 0 or limit > 200:
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

            score_col = None

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
                    *([score_col] if score_col is not None else []),
                )
                .where(*base_filters)
                .limit(limit)
                .offset(offset)
            )

            stmt = _apply_order_by(stmt, order_by=order_by, score_col=score_col)

            rows = session.execute(stmt).all()
    except Exception as e:
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
        # row is tuple with optional score at end
        term_id = str(row[0])
        term_code = str(row[1])
        term_name = str(row[2])
        ttype = str(row[3])
        desc_summary = row[4]
        term_tags = row[5] or {}
        owl_doc_id = row[6]
        created_time = row[7]
        updated_time = row[8]
        score = float(row[9]) if len(row) > 9 and row[9] is not None else None

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
                score=score,
            )
        )

    return SearchTermsResult(total=total, items=items)


def _normalize_type_code(type_code: str) -> str:
    raw = (type_code or "").strip()
    if not raw:
        raise ValueError("term_type_code 不能为空")
    if raw.startswith("ONTOLOGY_"):
        return raw

    mapping = {
        "VIEW": "ONTOLOGY_VIEW",
        "OBJ": "ONTOLOGY_OBJ",
        "ACTION": "ONTOLOGY_ACTION",
        "FUNC": "ONTOLOGY_FUNC",
        "PARAM": "ONTOLOGY_PARAM",
        "PROP": "ONTOLOGY_PROP",
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

    for tf in tags or []:
        filters.append(_tag_filter_expr(tf))

    return filters


def _tag_filter_expr(tf: TagFilter):
    key = tf.key
    op = tf.op
    vtype = tf.value_type

    val_text = Term.term_tags.op("->>")(key)

    if op == "in":
        if not isinstance(tf.value, list):
            raise ValueError("tag filter op=in 时 value 必须是数组")
        return val_text.in_(tf.value)

    if op == "like":
        if isinstance(tf.value, list):
            raise ValueError("tag filter op=like 时 value 必须是字符串")
        return val_text.ilike(f"%{tf.value}%")

    if isinstance(tf.value, list):
        raise ValueError(f"tag filter op={op} 时 value 必须是字符串")

    if op == "eq":
        return val_text == tf.value

    op_map = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    sql_op = op_map.get(op)
    if not sql_op:
        raise ValueError(f"不支持的 tag op: {op}")

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


def _apply_order_by(stmt, *, order_by: str, score_col):
    ob = (order_by or "").strip().lower()
    if ob in ("", "relevance"):
        if score_col is not None:
            return stmt.order_by(score_col.desc(), Term.term_id.asc())
        return stmt.order_by(Term.updated_time.desc(), Term.term_id.asc())
    if ob == "updated_time":
        return stmt.order_by(Term.updated_time.desc(), Term.term_id.asc())
    if ob == "created_time":
        return stmt.order_by(Term.created_time.desc(), Term.term_id.asc())
    if ob == "term_name":
        return stmt.order_by(Term.term_name.asc(), Term.term_id.asc())
    raise ValueError(f"未知排序字段: {order_by}")

