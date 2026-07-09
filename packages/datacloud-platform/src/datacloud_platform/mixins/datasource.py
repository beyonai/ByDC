"""DatasourceMixin — datasource CRUD operations."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend

logger = logging.getLogger(__name__)


class DatasourceMixin:
    """Mixin for datasource-level operations: list, detail, create, delete."""

    def get_datasources(
        self: _HasOntologyBackend,
        base_id: str,
        *,
        keyword: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get all datasources under a base with optional filtering."""
        return self._ontology_for(base_id).get_datasources(
            base_id=base_id, keyword=keyword
        )

    def get_datasource_detail(
        self: _HasOntologyBackend,
        base_id: str,
        db_id: str,
    ) -> dict[str, Any] | None:
        """Get single datasource detail by db_id."""
        return self._ontology_for(base_id).get_datasource_detail(db_id, base_id=base_id)

    def create_datasource(self: _HasOntologyBackend, base_id: str, ds: Any) -> Any:
        """Create a datasource. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).create_datasource(base_id, ds)

    def delete_datasource(self: _HasOntologyBackend, base_id: str, db_id: str) -> None:
        """Delete a datasource. Raises PermissionError on read-only backends."""
        self._ontology_for(base_id).delete_datasource(base_id, db_id)
