"""TermLibrary reader Mixin."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from datacloud_knowledge.adapters.opengauss._db.models import TermLibrary

from ._base import _ReaderBase


class _LibraryReader(_ReaderBase):
    """TermLibrary read operations."""

    def list_term_libraries(
        self,
        *,
        library_code: str | None = None,
        library_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List term libraries, optionally filtered."""
        with self._get_session() as session:
            stmt = select(TermLibrary)
            if library_code is not None:
                stmt = stmt.where(TermLibrary.library_code == library_code)
            if library_name is not None:
                stmt = stmt.where(TermLibrary.library_name.ilike(f"%{library_name}%"))
            stmt = stmt.order_by(TermLibrary.library_name)
            rows = session.execute(stmt).scalars().all()
        return [
            {
                "library_id": r.library_id,
                "library_code": r.library_code,
                "library_name": r.library_name,
                "created_time": r.created_time.isoformat(),
                "updated_time": r.updated_time.isoformat(),
            }
            for r in rows
        ]

    def get_term_library(self, *, library_id: str) -> dict[str, Any] | None:
        """Get single term library by ID."""
        with self._get_session() as session:
            row = session.execute(
                select(TermLibrary).where(TermLibrary.library_id == library_id)
            ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "library_id": row.library_id,
            "library_code": row.library_code,
            "library_name": row.library_name,
            "created_time": row.created_time.isoformat(),
            "updated_time": row.updated_time.isoformat(),
        }
