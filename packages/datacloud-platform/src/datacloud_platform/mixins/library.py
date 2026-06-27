"""LibraryMixin — base registry management (always local)."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from datacloud_platform.base_entry import generate_snowflake

logger = logging.getLogger(__name__)


class LibraryMixin:
    """Mixin providing library-level CRUD for ontology bases.

    All methods operate on the local ``_base_registry`` — no backend routing.
    """

    def list_bases(self) -> list[dict[str, Any]]:
        """List all registered ontology bases as dicts."""
        return [asdict(e) for e in self._base_registry.list()]  # type: ignore[attr-defined]

    def base_exists(self, base_id: str) -> bool:
        """Return True if *base_id* is registered."""
        return self._base_registry.exists(base_id)  # type: ignore[attr-defined,no-any-return]

    def create_base(self, entry: Any) -> dict[str, Any]:
        """Register a new ontology base.

        If *entry.base_id* is empty, a snowflake ID is auto-generated.

        Persists the registry to disk after registering.

        Raises:
            ValueError: If a base with the same base_id already exists.
        """
        if not entry.base_id:
            entry.base_id = generate_snowflake()
        self._base_registry.register(entry)  # type: ignore[attr-defined]
        return asdict(entry)

    def delete_base(self, base_id: str) -> None:
        """Remove a registered ontology base.

        Persists the registry to disk after removing.

        Raises:
            KeyError: If base_id is not registered.
        """
        self._base_registry.unregister(base_id)  # type: ignore[attr-defined]

    def update_base(self, base_id: str, updates: Any) -> dict[str, Any]:
        """Update fields of an existing ontology base.

        *updates* is an ``OntologyBaseUpdate``; only non-None fields are applied.
        ``baseId`` is read-only and ignored.

        Returns the full updated entry as a dict.

        Raises:
            KeyError: If base_id is not registered.
        """
        fields: dict[str, Any] = updates.model_dump(exclude_none=True)
        entry = self._base_registry.update(base_id, **fields)  # type: ignore[attr-defined]
        return asdict(entry)
