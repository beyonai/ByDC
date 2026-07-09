"""RelationMixin — relation CRUD operations."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend

logger = logging.getLogger(__name__)


class RelationMixin:
    """Mixin for relation-level operations: list, detail, create, update, delete."""

    def get_relations(
        self: _HasOntologyBackend,
        base_id: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get all relations under a base with optional filtering."""
        return self._ontology_for(base_id).get_relations(
            base_id=base_id, owner_type=owner_type, user_code=user_code, keyword=keyword
        )

    def get_relation_detail(
        self: _HasOntologyBackend,
        base_id: str,
        rel_code: str,
    ) -> dict[str, Any] | None:
        """Get single relation detail by code."""
        return self._ontology_for(base_id).get_relation_detail(
            rel_code, base_id=base_id
        )

    def get_relations_by_object(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all relation details involving *object_code* (source or target), with filtering."""
        return self._ontology_for(base_id).get_relations_by_object(
            object_code,
            base_id=base_id,
            owner_type=owner_type,
            user_code=user_code,
        )

    def create_relation(self: _HasOntologyBackend, base_id: str, rel: Any) -> Any:
        """Create a relation. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).create_relation(base_id, rel)

    def update_relation(
        self: _HasOntologyBackend, base_id: str, rel_code: str, rel: Any
    ) -> Any:
        """Update a relation. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).update_relation(base_id, rel_code, rel)

    def delete_relation(self: _HasOntologyBackend, base_id: str, rel_code: str) -> None:
        """Delete a relation. Raises PermissionError on read-only backends."""
        self._ontology_for(base_id).delete_relation(base_id, rel_code)
