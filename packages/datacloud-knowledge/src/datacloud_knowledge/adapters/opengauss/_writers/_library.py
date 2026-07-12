"""TermLibrary writer Mixin."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, update

from datacloud_knowledge.adapters.opengauss._db.models import TermDomain, TermLibrary

from ._base import _WriterBase

logger = logging.getLogger(__name__)


class _LibraryWriter(_WriterBase):
    """TermLibrary write operations."""

    def create_term_library(self, *, library: dict[str, Any]) -> dict[str, Any]:
        """Create a term library."""
        lid = library.get("libraryId") or library.get("library_id") or self._new_id()
        now = self._now()
        self.session.add(
            TermLibrary(
                library_id=lid,
                library_code=library.get("libraryCode", library.get("library_code", "")),
                library_name=library.get("libraryName", library.get("library_name", "")),
                created_time=now,
                updated_time=now,
            )
        )
        logger.info("Created term library: id=%s code=%s", lid, library.get("libraryCode", ""))
        return {
            "library_id": lid,
            "library_code": library.get("libraryCode", library.get("library_code", "")),
            "library_name": library.get("libraryName", library.get("library_name", "")),
            "created_time": now.isoformat(),
            "updated_time": now.isoformat(),
        }

    def update_term_library(self, *, library_id: str, updates: dict[str, Any]) -> None:
        """Update a term library. Only updates non-None fields."""
        fields = {k: v for k, v in updates.items() if v is not None}
        if not fields:
            return
        # Map camelCase to snake_case
        mapped: dict[str, Any] = {}
        if "libraryName" in fields or "library_name" in fields:
            mapped["library_name"] = fields.get("libraryName", fields.get("library_name"))
        if "libraryCode" in fields or "library_code" in fields:
            mapped["library_code"] = fields.get("libraryCode", fields.get("library_code"))
        if mapped:
            mapped["updated_time"] = self._now()
            self.session.execute(
                update(TermLibrary).where(TermLibrary.library_id == library_id).values(**mapped)
            )
        logger.info("Updated term library: id=%s", library_id)

    def delete_term_library(self, *, library_id: str) -> None:
        """Delete a term library and cascade-delete its term_domain rows."""
        # Cascade: delete term_domain rows under this library first
        self.session.execute(delete(TermDomain).where(TermDomain.library_id == library_id))
        # Then delete the library itself
        self.session.execute(delete(TermLibrary).where(TermLibrary.library_id == library_id))
        logger.info("Deleted term library (with domains): id=%s", library_id)
