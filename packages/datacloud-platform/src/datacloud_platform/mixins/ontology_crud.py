"""OntologyCRUDMixin — ontology object create / update / delete."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from datacloud_platform.backends._contracts import _HasOntologyBackend

_build_terms: Callable[..., dict[str, Any]] | None
try:
    from datacloud_knowledge.ingestion.ontology_terms import build_terms as _build_terms
except ImportError:
    _build_terms = None

logger = logging.getLogger(__name__)


class OntologyCRUDMixin:
    """Mixin for ontology object CRUD operations."""

    def create_object(self: _HasOntologyBackend, base_id: str, obj: Any) -> Any:
        """Create an ontology object.

        REMOTE backends raise PermissionError internally — Platform does not
        check permissions.

        Side effect: if datacloud-knowledge is installed, writes term data
        so the new object can be hit by vector search.
        """
        result = self._ontology_for(base_id).create_object(base_id, obj)
        if _build_terms is not None:
            try:
                fields = [
                    {
                        "property_code": (
                            p.property_code if hasattr(p, "property_code") else str(p)
                        ),
                        "property_name": (
                            p.property_name if hasattr(p, "property_name") else str(p)
                        ),
                        "data_type": "STRING",
                    }
                    for p in (getattr(obj, "properties", None) or [])
                ]
                _build_terms(
                    entity_code=getattr(obj, "object_code", ""),
                    entity_name=str(
                        getattr(obj, "object_name", None)
                        or getattr(obj, "object_code", "")
                    ),
                    fields=fields,
                    entity_desc=getattr(obj, "object_desc", "") or "",
                )
                logger.info(
                    "create_object: build_terms done for %s",
                    getattr(obj, "object_code", "?"),
                )
            except Exception:
                logger.warning(
                    "create_object: build_terms failed for %s",
                    getattr(obj, "object_code", "?"),
                    exc_info=True,
                )
        return result

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
        self._ontology_for(base_id).delete_object(base_id, object_code)
