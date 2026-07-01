"""ViewMixin — view CRUD operations."""

from __future__ import annotations

import logging
import warnings
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend
from datacloud_platform.ontology_store import CacheMode

logger = logging.getLogger(__name__)


class ViewMixin:
    """Mixin for view-level operations: list, detail, create, update, delete."""

    def get_views(
        self: _HasOntologyBackend,
        base_id: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[dict[str, Any]]:
        """Get all views under a base."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_views(loader, base_id)

    def get_view_detail(
        self: _HasOntologyBackend,
        base_id: str,
        view_code: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> dict[str, Any] | None:
        """Get single view detail by code."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_view_detail(loader, base_id, view_code)

    def create_view(self: _HasOntologyBackend, base_id: str, view: Any) -> Any:
        """Create a view. Raises PermissionError on read-only backends."""
        warnings.warn(
            "create_view() is deprecated; use create_view_with_scene() to "
            "guarantee scene membership",
            FutureWarning,
            stacklevel=2,
        )
        return self._ontology_for(base_id).create_view(base_id, view)

    def update_view(
        self: _HasOntologyBackend, base_id: str, view_code: str, view: Any
    ) -> Any:
        """Update a view. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).update_view(base_id, view_code, view)

    def delete_view(self: _HasOntologyBackend, base_id: str, view_code: str) -> None:
        """Delete a view. Raises PermissionError on read-only backends."""
        warnings.warn(
            "delete_view() is deprecated; use delete_view_from_all_scenes() "
            "to clean up scene references",
            FutureWarning,
            stacklevel=2,
        )
        self._ontology_for(base_id).delete_view(base_id, view_code)
