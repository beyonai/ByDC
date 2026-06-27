"""OntologyQueryMixin — read-only ontology query methods."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from datacloud_platform.backends._contracts import _HasOntologyBackend
from datacloud_platform.ontology_store import CacheMode

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable
    from datacloud_platform.models.shared import ObjectSummary

logger = logging.getLogger(__name__)


class OntologyQueryMixin:
    """Mixin for read-only ontology loading and object queries."""

    def load_ontology(
        self: _HasOntologyBackend,
        base_id: str,
        base_path: str | Path,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> OntologyQueryable:
        """Load ontology from a base_path, returning a queryable handle.

        Respects *cache_mode* for OntologyStore index priming before loading.
        """
        _ = base_path  # passed for backward API compatibility; internally derived
        return self._load_ontology_cached(base_id, cache_mode=cache_mode)

    def get_objects(
        self: _HasOntologyBackend,
        base_id: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[ObjectSummary]:
        """Get all ontology object summaries under a base."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_objects(loader, base_id)

    def get_object_detail(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> dict[str, Any] | None:
        """Get a single object's full detail (ObjectType with properties and actions)."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_object_detail(loader, object_code)
