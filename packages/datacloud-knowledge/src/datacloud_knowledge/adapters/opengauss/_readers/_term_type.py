"""_TermTypeReader — Mixin providing TermType read operations for the OpenGauss adapter.

Supports library_id-scoped queries with domain_code filtering, keyword search,
pagination, and per-type term count.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, func, select, text

from datacloud_knowledge.adapters.opengauss._db.models import Term, TermType
from datacloud_knowledge.adapters.opengauss._readers._base import _ReaderBase

logger = logging.getLogger(__name__)


class _TermTypeReader(_ReaderBase):
    """Mixin that reads ``term_type`` table rows via the shared reader base.

    Domain code↔id translation helpers (_resolve_domain_code,
    _batch_resolve_domain_codes) and utility methods (_build_domain_list,
    _format_time, _batch_get_term_names) are inherited from _ReaderBase.
    """

    def list_term_types(
        self,
        *,
        library_id: str,
        domain_code: str | None = None,
        type_category: int | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List term types scoped to a library, with keyword search and pagination."""
        page_size = min(page_size, 100)
        offset = (page_index - 1) * page_size

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
                where_parts: list[Any] = [TermType.library_id == library_id]
                exec_params: dict[str, Any] = {}

                if domain_id is not None:
                    where_parts.append(text("term_type.domain_ids @> ARRAY[:domain_id]::varchar[]"))
                    exec_params["domain_id"] = domain_id

                if type_category is not None:
                    where_parts.append(TermType.type_category == type_category)

                if keyword and keyword.strip():
                    kw = keyword.strip()
                    where_parts.append(
                        text("(term_type.type_name ILIKE :kw OR term_type.type_desc ILIKE :kw)")
                    )
                    exec_params["kw"] = f"%{kw}%"

                where_clause = and_(*where_parts) if len(where_parts) > 1 else where_parts[0]

                term_count_subq = (
                    select(Term.term_type_code, func.count(Term.term_id).label("cnt"))
                    .where(Term.library_id == library_id)
                    .group_by(Term.term_type_code)
                    .subquery()
                )

                total = int(
                    session.execute(
                        select(func.count()).select_from(TermType).where(where_clause),
                        exec_params,
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

                rows = session.execute(
                    select(
                        TermType.type_code,
                        TermType.type_name,
                        TermType.type_desc,
                        TermType.type_category,
                        TermType.is_builtin,
                        TermType.domain_ids,
                        TermType.created_time,
                        TermType.updated_time,
                        func.coalesce(term_count_subq.c.cnt, 0).label("term_count"),
                    )
                    .outerjoin(
                        term_count_subq,
                        TermType.type_code == term_count_subq.c.term_type_code,
                    )
                    .where(where_clause)
                    .order_by(TermType.type_code)
                    .limit(page_size)
                    .offset(offset),
                    exec_params,
                ).all()

        except Exception:
            logger.exception(
                "list_term_types failed: library_id=%s domain_code=%s type_category=%s keyword=%s",
                library_id,
                domain_code,
                type_category,
                keyword,
            )
            raise

        all_domain_ids: set[str] = set()
        for row in rows:
            if row[5]:
                all_domain_ids.update(row[5])

        domain_map = self._batch_resolve_domain_codes(library_id, all_domain_ids)

        data = []
        for row in rows:
            domain_list = self._build_domain_list(row[5] or [], domain_map)
            data.append(
                {
                    "type_code": str(row[0]),
                    "type_name": str(row[1]),
                    "type_desc": str(row[2]) if row[2] is not None else None,
                    "type_category": int(row[3]),
                    "is_builtin": bool(row[4]),
                    "domain": domain_list,
                    "term_count": int(row[8]) if row[8] is not None else 0,
                    "created_time": self._format_time(row[6]),
                    "updated_time": self._format_time(row[7]),
                }
            )

        return {
            "data": data,
            "pageIndex": page_index,
            "pageSize": page_size,
            "totalCount": total,
            "totalPages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }

    def get_term_type(self, *, library_id: str, type_code: str) -> dict[str, Any] | None:
        """Get a single term type definition scoped to a library.

        Issue #5 fix: uses LEFT JOIN LATERAL to get term_count in a single query
        instead of separate COUNT + SELECT.
        """
        try:
            with self._get_session() as session:
                row = session.execute(
                    select(
                        TermType.type_code,
                        TermType.type_name,
                        TermType.type_desc,
                        TermType.type_category,
                        TermType.is_builtin,
                        TermType.domain_ids,
                        TermType.library_id,
                        TermType.created_time,
                        TermType.updated_time,
                        func.coalesce(
                            select(func.count(Term.term_id))
                            .where(
                                Term.library_id == library_id,
                                Term.term_type_code == type_code,
                            )
                            .scalar_subquery(),
                            0,
                        ).label("term_count"),
                    ).where(
                        TermType.library_id == library_id,
                        TermType.type_code == type_code,
                    )
                ).first()

        except Exception:
            logger.exception(
                "get_term_type failed: library_id=%s type_code=%s",
                library_id,
                type_code,
            )
            raise

        if row is None:
            return None

        domain_ids: list[str] = list(row[5]) if row[5] else []
        domain_map = self._batch_resolve_domain_codes(library_id, set(domain_ids))

        return {
            "type_code": str(row[0]),
            "type_name": str(row[1]),
            "type_desc": str(row[2]) if row[2] is not None else None,
            "type_category": int(row[3]),
            "is_builtin": bool(row[4]),
            "domain": self._build_domain_list(domain_ids, domain_map),
            "library_id": str(row[6]),
            "term_count": int(row[9]) if row[9] is not None else 0,
            "created_time": self._format_time(row[7]),
            "updated_time": self._format_time(row[8]),
        }
