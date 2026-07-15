"""SceneMixin — scene query, detail, CRUD, and member management."""

from __future__ import annotations

import logging
import warnings
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend

logger = logging.getLogger(__name__)


class SceneMixin:
    """Mixin for scene-level operations: list, query, detail, CRUD, member management."""

    # ── Scene: query + detail ──

    def list_scenes(
        self: _HasOntologyBackend,
        base_id: str,
    ) -> list[dict[str, Any]]:
        """List scene directories under a base."""
        return self._ontology_for(base_id).list_scenes(base_id)

    def query_scenes(
        self: _HasOntologyBackend,
        base_id: str,
        keyword: str | None,
    ) -> list[dict[str, Any]]:
        """Query scenes with optional keyword filter."""
        return self._ontology_for(base_id).query_scenes(base_id, keyword)

    def count_scenes(
        self: _HasOntologyBackend,
        base_id: str,
        keyword: str | None,
    ) -> int:
        """Count scenes matching optional keyword filter."""
        return self._ontology_for(base_id).count_scenes(base_id, keyword)

    def get_term_scope_info(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
    ) -> dict[str, Any]:
        """Return {library_id, scene_id} identifying which scene contains object_code.

        Routes to backend.get_term_scope_info() — for remote backends this queries
        list_scenes + get_scene_members to find the matching scene.
        """
        backend = self._ontology_for(base_id)
        return backend.get_term_scope_info(base_id, object_code)

    def get_scene_details(
        self: _HasOntologyBackend,
        base_id: str,
        scene_id: str,
        *,
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get full scene details with optional filtering by view_code or object_code."""
        return self._ontology_for(base_id).get_scene_details(
            scene_id, base_id=base_id, view_code=view_code, object_code=object_code
        )

    def query_ontologies_by_scene(
        self: _HasOntologyBackend,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        type: str | None = None,
        owner_type: str | None = None,
        user_code: str | None = None,
        cross_scene: bool = False,
        ext_property_filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query ontologies (objects) in a scene with pagination and keyword filter."""
        return self._ontology_for(base_id).query_ontologies_by_scene(
            scene_id,
            base_id=base_id,
            page=page,
            page_size=page_size,
            keyword=keyword,
            type=type,
            owner_type=owner_type,
            user_code=user_code,
            cross_scene=cross_scene,
            ext_property_filters=ext_property_filters,
        )

    def get_object_subtree(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
    ) -> dict[str, Any]:
        """Get an object's subtree — detail + related views, relations, actions."""
        return self._ontology_for(base_id).get_object_subtree(
            object_code, base_id=base_id
        )

    def get_base_details(
        self: _HasOntologyBackend,
        *,
        base_id: str = "",
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get comprehensive base detail."""
        return self._ontology_for(base_id).get_base_details(
            base_id=base_id, view_code=view_code, object_code=object_code
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
        warnings.warn(
            "delete_scene() is deprecated; use delete_scene_with_migration() "
            "to migrate members to default scene",
            FutureWarning,
            stacklevel=2,
        )
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
        warnings.warn(
            "remove_scene_members() is deprecated; use remove_object_from_scene_safe() "
            "to prevent orphan objects",
            FutureWarning,
            stacklevel=2,
        )
        result = self._ontology_for(base_id).remove_scene_members(
            base_id, scene_id, object_codes, view_codes
        )
        if self._ontology_store:
            self._ontology_store.invalidate("scenes")
        return result
