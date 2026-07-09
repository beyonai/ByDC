"""ViewMixin — view CRUD operations."""

from __future__ import annotations

import logging
import warnings
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend

logger = logging.getLogger(__name__)


class ViewMixin:
    """Mixin for view-level operations: list, detail, create, update, delete."""

    def get_views(
        self: _HasOntologyBackend,
        base_id: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated views under a base with optional filtering.

        Returns:
            Tuple of (items list, total count).
        """
        return self._ontology_for(base_id).get_views(
            base_id=base_id,
            owner_type=owner_type,
            user_code=user_code,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )

    def get_view_detail(
        self: _HasOntologyBackend,
        base_id: str,
        view_code: str,
    ) -> dict[str, Any] | None:
        """Get single view detail by code."""
        return self._ontology_for(base_id).get_view_detail(view_code, base_id=base_id)

    def get_objects_by_view(
        self: _HasOntologyBackend,
        base_id: str,
        view_code: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get objects (code/name/desc) referenced by a view, with filtering."""
        return self._ontology_for(base_id).get_objects_by_view(
            view_code,
            base_id=base_id,
            owner_type=owner_type,
            user_code=user_code,
            keyword=keyword,
        )

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
