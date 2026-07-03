"""_NameReader — TermName read-side Mixin."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from datacloud_knowledge.adapters.opengauss._db.models import TermName
from datacloud_knowledge.adapters.opengauss._readers._base import _ReaderBase

logger = logging.getLogger(__name__)


class _NameReader(_ReaderBase):
    """Mixin providing TermName CRUD read operations."""

    def list_term_names(
        self,
        *,
        term_id: str | None = None,
        name_text: str | None = None,
    ) -> list[dict[str, Any]]:
        """List term names with optional filters.

        Args:
            term_id: Optional filter by term_id (exact match).
            name_text: Optional filter by name_text (ilike match).

        Returns:
            List of dicts with keys: name_id, term_id, name_text, search_scope,
            created_time, updated_time.
        """
        try:
            with self._get_session() as session:
                stmt = select(
                    TermName.name_id,
                    TermName.term_id,
                    TermName.name_text,
                    TermName.search_scope,
                    TermName.created_time,
                    TermName.updated_time,
                )
                if term_id is not None:
                    stmt = stmt.where(TermName.term_id == term_id)
                if name_text is not None:
                    stmt = stmt.where(TermName.name_text.ilike(f"%{name_text}%"))

                rows = session.execute(stmt).all()
        except Exception:
            logger.exception(
                "list_term_names failed: term_id=%s, name_text=%s",
                term_id,
                name_text,
            )
            raise

        return [
            {
                "name_id": str(row.name_id),
                "term_id": str(row.term_id),
                "name_text": str(row.name_text),
                "search_scope": dict(row.search_scope) if row.search_scope else {},
                "created_time": row.created_time,
                "updated_time": row.updated_time,
            }
            for row in rows
        ]

    def get_term_name(self, *, name_id: str) -> dict[str, Any] | None:
        """Get a single term name by name_id.

        Args:
            name_id: The name ID to look up.

        Returns:
            Dict with keys: name_id, term_id, name_text, search_scope,
            created_time, updated_time. Returns None if not found.
        """
        try:
            with self._get_session() as session:
                row = session.execute(
                    select(
                        TermName.name_id,
                        TermName.term_id,
                        TermName.name_text,
                        TermName.search_scope,
                        TermName.created_time,
                        TermName.updated_time,
                    ).where(TermName.name_id == name_id)
                ).one_or_none()
        except Exception:
            logger.exception("get_term_name failed: name_id=%s", name_id)
            raise

        if row is None:
            return None

        return {
            "name_id": str(row.name_id),
            "term_id": str(row.term_id),
            "name_text": str(row.name_text),
            "search_scope": dict(row.search_scope) if row.search_scope else {},
            "created_time": row.created_time,
            "updated_time": row.updated_time,
        }
