"""RelationMixin — relation CRUD operations."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend
from datacloud_platform.ontology_store import CacheMode

logger = logging.getLogger(__name__)


class RelationMixin:
    """Mixin for relation-level operations: list, detail, create, update, delete."""

    def get_relations(
        self: _HasOntologyBackend,
        base_id: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[dict[str, Any]]:
        """Get all relations under a base."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_relations(loader, base_id)

    def get_relation_detail(
        self: _HasOntologyBackend,
        base_id: str,
        rel_code: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> dict[str, Any] | None:
        """Get single relation detail by code."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_relation_detail(loader, base_id, rel_code)

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
