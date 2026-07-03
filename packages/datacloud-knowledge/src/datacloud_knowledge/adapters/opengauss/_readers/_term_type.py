"""_TermTypeReader — Mixin providing TermType read operations for the OpenGauss adapter."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from datacloud_knowledge.adapters.opengauss._db.models import TermType
from datacloud_knowledge.adapters.opengauss._readers._base import _ReaderBase

logger = logging.getLogger(__name__)


class _TermTypeReader(_ReaderBase):
    """Mixin that reads ``term_type`` table rows via the shared reader base.

    Usage::

        reader = _TermTypeReader()
        all_types = reader.list_term_types()
        one_type = reader.get_term_type(type_code="view")
    """

    def list_term_types(self, *, type_category: int | None = None) -> list[dict[str, Any]]:
        """List term type definitions, optionally filtered by category.

        Args:
            type_category: Optional filter by ``type_category``
                (1=list, 2=dict, 3=ontology, 4=document).  ``None`` returns all.

        Returns:
            List of dicts with keys: type_code, type_name, type_desc,
            type_category, is_builtin — ordered by type_code.
        """
        try:
            with self._get_session() as session:
                stmt = select(
                    TermType.type_code,
                    TermType.type_name,
                    TermType.type_desc,
                    TermType.type_category,
                    TermType.is_builtin,
                )
                if type_category is not None:
                    stmt = stmt.where(TermType.type_category == type_category)
                stmt = stmt.order_by(TermType.type_code)

                rows = session.execute(stmt).all()
        except Exception:
            logger.exception("list_term_types failed: type_category=%s", type_category)
            raise

        return [
            {
                "type_code": str(row[0]),
                "type_name": str(row[1]),
                "type_desc": str(row[2]) if row[2] is not None else None,
                "type_category": int(row[3]),
                "is_builtin": bool(row[4]),
            }
            for row in rows
        ]

    def get_term_type(self, *, type_code: str) -> dict[str, Any] | None:
        """Get a single term type definition by its code.

        Args:
            type_code: The term type code (unique, non-PK column).

        Returns:
            Dict with keys: type_code, type_name, type_desc, type_category,
            is_builtin — or ``None`` if not found.
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
                    ).where(TermType.type_code == type_code)
                ).first()
        except Exception:
            logger.exception("get_term_type failed: type_code=%s", type_code)
            raise

        if row is None:
            return None

        return {
            "type_code": str(row[0]),
            "type_name": str(row[1]),
            "type_desc": str(row[2]) if row[2] is not None else None,
            "type_category": int(row[3]),
            "is_builtin": bool(row[4]),
        }
