"""SceneMixin — scene query, detail, CRUD, and member management."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend
from datacloud_platform.ontology_store import CacheMode

logger = logging.getLogger(__name__)


class SceneMixin:
    """Mixin for scene-level operations: list, query, detail, CRUD, member management."""

    # ── Scene: query + detail ──

    def list_scenes(
        self: _HasOntologyBackend,
        base_id: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[dict[str, Any]]:
        """List scene directories under a base."""
        return self._ontology_for(base_id).list_scenes(base_id)

    def query_scenes(
        self: _HasOntologyBackend,
        base_id: str,
        keyword: str | None,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[dict[str, Any]]:
        """Query scenes with optional keyword filter."""
        return self._ontology_for(base_id).query_scenes(base_id, keyword)

    def count_scenes(
        self: _HasOntologyBackend,
        base_id: str,
        keyword: str | None,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> int:
        """Count scenes matching optional keyword filter."""
        return self._ontology_for(base_id).count_scenes(base_id, keyword)

    def get_scene_details(
        self: _HasOntologyBackend,
        base_id: str,
        scene_id: str,
        *,
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> dict[str, Any]:
        """Get full scene details with optional filtering by view_code or object_code."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_scene_details(
            loader, base_id, scene_id, view_code=view_code, object_code=object_code
        )

    def query_ontologies_by_scene(
        self: _HasOntologyBackend,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> dict[str, Any]:
        """Query ontologies (objects) in a scene with pagination and keyword filter."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.query_ontologies_by_scene(
            loader, base_id, scene_id, page=page, page_size=page_size, keyword=keyword
        )

    # ── Scene CRUD ──

    def create_scene(self: _HasOntologyBackend, base_id: str, scene: Any) -> Any:
        """Create a scene (grouping container)."""
        result = self._ontology_for(base_id).create_scene(base_id, scene)
        if self._ontology_store:
            self._ontology_store.invalidate("scenes")
        return result

    def update_scene(
        self: _HasOntologyBackend, base_id: str, scene_id: str, updates: Any
    ) -> Any:
        """Update scene metadata."""
        result = self._ontology_for(base_id).update_scene(base_id, scene_id, updates)
        if self._ontology_store:
            self._ontology_store.invalidate("scenes")
        return result

    def delete_scene(self: _HasOntologyBackend, base_id: str, scene_id: str) -> None:
        """Delete a scene — does NOT delete member resources."""
        self._ontology_for(base_id).delete_scene(base_id, scene_id)
        if self._ontology_store:
            self._ontology_store.invalidate("scenes")

    # ── Scene member management ──

    def add_scene_members(
        self: _HasOntologyBackend,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Add objects/views to a scene (idempotent)."""
        result = self._ontology_for(base_id).add_scene_members(
            base_id, scene_id, object_codes, view_codes
        )
        if self._ontology_store:
            self._ontology_store.invalidate("scenes")
        return result

    def remove_scene_members(
        self: _HasOntologyBackend,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Remove objects/views from a scene — does NOT delete resources."""
        result = self._ontology_for(base_id).remove_scene_members(
            base_id, scene_id, object_codes, view_codes
        )
        if self._ontology_store:
            self._ontology_store.invalidate("scenes")
        return result
