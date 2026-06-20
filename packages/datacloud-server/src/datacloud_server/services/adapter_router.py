"""AdapterRouter — single entry point for all Services to resolve OntologyRepository.

Consolidates Registry lookup + sourceType routing + fallback logic into one
injectable object.  Each Service injects only this one object instead of
registry + adapters dict + duplicated _get_adapter logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from datacloud_server.ports.ontology_repository import OntologyRepository
    from datacloud_server.registry.registry import OntologyBaseRegistry


class AdapterRouter:
    """Resolve an OntologyRepository for a given base_id.

    All three Services (Base, Resource, Search) inject this single object
    and call ``self._router.get(base_id)`` instead of copying the same
    6-line routing method.
    """

    def __init__(
        self,
        registry: OntologyBaseRegistry,
        adapters: Mapping[str, OntologyRepository],
    ) -> None:
        self._registry = registry
        self._adapters = adapters

    def get(self, base_id: str) -> OntologyRepository:
        """Look up Registry entry → determine sourceType → route to adapter.

        Falls back to the first available adapter if sourceType is unknown.
        """
        entry = self._registry.get(base_id)
        if entry is None:
            raise KeyError(f"OntologyBase '{base_id}' not found")
        adapter = self._adapters.get(entry.source_type)
        if adapter is not None:
            return adapter
        return next(iter(self._adapters.values()))

    @property
    def registry(self) -> OntologyBaseRegistry:
        """Expose registry for list_bases/create_base/delete_base operations."""
        return self._registry
