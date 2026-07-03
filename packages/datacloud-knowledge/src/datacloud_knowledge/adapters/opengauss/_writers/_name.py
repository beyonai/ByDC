"""_NameWriter — TermName write-side Mixin."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, update

from datacloud_knowledge.adapters.opengauss._db.models import TermName
from datacloud_knowledge.adapters.opengauss._writers._base import _WriterBase

logger = logging.getLogger(__name__)

_CAMEL_TO_SNAKE_NAME: dict[str, str] = {
    "nameId": "name_id",
    "termId": "term_id",
    "nameText": "name_text",
    "searchScope": "search_scope",
    "userId": "user_id",
    "createdTime": "created_time",
    "updatedTime": "updated_time",
}


class _NameWriter(_WriterBase):
    """Mixin providing TermName CRUD write operations."""

    def create_term_name_wrapper(self, *, name: dict[str, Any]) -> dict[str, Any]:
        """Create term name from dict — protocol entry point.

        Args:
            name: Dict with keys like termId/term_id, nameText/name_text,
                  searchScope/search_scope, userId/user_id (camelCase preferred).

        Returns:
            Dict with name_id, term_id, name_text, search_scope, created_time, updated_time.
        """
        return self._base_create_term_name(
            term_id=name.get("termId", name.get("term_id", "")),
            name_text=name.get("nameText", name.get("name_text", "")),
            search_scope=name.get("searchScope", name.get("search_scope", {})),
            user_id=name.get("userId", name.get("user_id")),
        )

    def _base_create_term_name(
        self,
        *,
        term_id: str,
        name_text: str,
        search_scope: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Core term name insertion using ORM session.add.

        Args:
            term_id: Target term ID.
            name_text: Name text to create.
            search_scope: Search scope JSONB dict.
            user_id: Optional user ID (for logging).

        Returns:
            Dict with the created record fields.
        """
        _ = user_id  # reserved for logging
        name_id = self._new_id()
        now = self._now()

        record = TermName(
            name_id=name_id,
            term_id=term_id,
            name_text=name_text,
            search_scope=search_scope,
            created_time=now,
            updated_time=now,
        )
        self.session.add(record)
        self.session.flush()

        logger.info(
            "create_term_name: name_id=%s term_id=%s name_text=%s",
            record.name_id,
            record.term_id,
            record.name_text,
        )
        return {
            "name_id": record.name_id,
            "term_id": record.term_id,
            "name_text": record.name_text,
            "search_scope": record.search_scope,
            "created_time": record.created_time,
            "updated_time": record.updated_time,
        }

    def update_term_name(self, *, name_id: str, updates: dict[str, Any]) -> None:
        """Update a term name record.

        Only non-None fields are updated. CamelCase keys are mapped to snake_case.

        Args:
            name_id: The name ID to update.
            updates: Dict of field updates (supports camelCase and snake_case keys).
        """
        mapped: dict[str, Any] = {}
        for key, value in updates.items():
            if key in _CAMEL_TO_SNAKE_NAME:
                mapped[_CAMEL_TO_SNAKE_NAME[key]] = value
            else:
                mapped[key] = value

        # Only update non-None fields (excluding name_id which is PK)
        values = {k: v for k, v in mapped.items() if v is not None and k != "name_id"}
        if not values:
            return

        values["updated_time"] = self._now()

        self.session.execute(update(TermName).where(TermName.name_id == name_id).values(**values))
        logger.info("update_term_name: name_id=%s fields=%s", name_id, list(values.keys()))

    def delete_term_name(self, *, name_id: str) -> None:
        """Delete a term name record.

        Args:
            name_id: The name ID to delete.
        """
        self.session.execute(delete(TermName).where(TermName.name_id == name_id))
        logger.info("delete_term_name: name_id=%s", name_id)
