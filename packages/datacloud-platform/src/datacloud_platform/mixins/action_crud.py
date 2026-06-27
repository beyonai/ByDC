"""ActionCRUDMixin — action CRUD operations."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend
from datacloud_platform.ontology_store import CacheMode

logger = logging.getLogger(__name__)


class ActionCRUDMixin:
    """Mixin for action-level operations: list, detail, create, update, delete."""

    def get_actions(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[dict[str, Any]]:
        """Get all actions on an object."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_actions(loader, base_id, object_code)

    def get_action_detail(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        action_code: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> dict[str, Any] | None:
        """Get single action detail by code."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_action_detail(loader, base_id, object_code, action_code)

    def create_action(
        self: _HasOntologyBackend, base_id: str, object_code: str, action: Any
    ) -> Any:
        """Create an action. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).create_action(base_id, object_code, action)

    def update_action(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        action_code: str,
        action: Any,
    ) -> Any:
        """Update an action. Raises PermissionError on read-only backends."""
        return self._ontology_for(base_id).update_action(
            base_id, object_code, action_code, action
        )

    def delete_action(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        action_code: str,
    ) -> None:
        """Delete an action. Raises PermissionError on read-only backends."""
        self._ontology_for(base_id).delete_action(base_id, object_code, action_code)
