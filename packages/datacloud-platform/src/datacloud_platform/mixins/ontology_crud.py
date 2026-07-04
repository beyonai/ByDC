"""OntologyCRUDMixin — ontology object create / update / delete."""

from __future__ import annotations

import warnings
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend


class OntologyCRUDMixin:
    """Mixin for ontology object CRUD operations."""

    def create_object(self: _HasOntologyBackend, base_id: str, obj: Any) -> Any:
        """Create an ontology object.

        REMOTE backends raise PermissionError internally — Platform does not
        check permissions.
        """
        warnings.warn(
            "create_object() is deprecated; use create_object_with_scene() to "
            "guarantee scene membership",
            FutureWarning,
            stacklevel=2,
        )
        return self._ontology_for(base_id).create_object(base_id, obj)

    def update_object(
        self: _HasOntologyBackend, base_id: str, object_code: str, obj: Any
    ) -> Any:
        """Update an ontology object.

        REMOTE backends raise PermissionError internally.
        """
        return self._ontology_for(base_id).update_object(base_id, object_code, obj)

    def delete_object(
        self: _HasOntologyBackend, base_id: str, object_code: str
    ) -> None:
        """Delete an ontology object.

        REMOTE backends raise PermissionError internally.
        """
        warnings.warn(
            "delete_object() is deprecated; use delete_object_from_all_scenes() "
            "to clean up scene references",
            FutureWarning,
            stacklevel=2,
        )
        self._ontology_for(base_id).delete_object(base_id, object_code)
