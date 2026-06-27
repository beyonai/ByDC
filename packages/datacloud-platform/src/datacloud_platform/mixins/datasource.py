"""DatasourceMixin — datasource CRUD operations."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend
from datacloud_platform.ontology_store import CacheMode

logger = logging.getLogger(__name__)


class DatasourceMixin:
    """Mixin for datasource-level operations: list, detail, create, delete."""

    def get_datasources(
        self: _HasOntologyBackend,
        base_id: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[dict[str, Any]]:
        """Get all datasources under a base."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_datasources(loader, base_id)

    def get_datasource_detail(
        self: _HasOntologyBackend,
        base_id: str,
        db_id: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> dict[str, Any] | None:
        """Get single datasource detail by db_id."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_datasource_detail(loader, base_id, db_id)

    def create_datasource(self: _HasOntologyBackend, base_id: str, ds: Any) -> Any:
        """Create a datasource. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).create_datasource(base_id, ds)

    def delete_datasource(self: _HasOntologyBackend, base_id: str, db_id: str) -> None:
        """Delete a datasource. Raises PermissionError on read-only backends."""
        self._ontology_for(base_id).delete_datasource(base_id, db_id)
