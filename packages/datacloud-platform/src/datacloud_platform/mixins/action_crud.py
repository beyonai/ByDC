"""ActionCRUDMixin — action CRUD operations."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend

logger = logging.getLogger(__name__)


class ActionCRUDMixin:
    """Mixin for action-level operations: list, detail, create, update, delete."""

    def get_actions(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get all actions on an object with optional filtering."""
        return self._ontology_for(base_id).get_actions(
            object_code,
            base_id=base_id,
            owner_type=owner_type,
            user_code=user_code,
            keyword=keyword,
        )

    def get_action_detail(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        action_code: str,
    ) -> dict[str, Any] | None:
        """Get single action detail by code."""
        return self._ontology_for(base_id).get_action_detail(
            object_code, action_code, base_id=base_id
        )

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
