"""EntityStore Protocol — swappable CRUD abstraction for million-scale ontology entities.

Supports pluggable backends: JSON file store → PostgreSQL → MongoDB.
"""

from __future__ import annotations

from typing import Any, Protocol


class EntityStore(Protocol):
    """Storage abstraction for Object / View / Relation / Datasource / Action entities.

    ``entity_type`` is one of: ``objects``, ``views``, ``relations``, ``datasources``, ``actions``.
    ``code`` is the stable business identifier (e.g. ``"order"``).
    """

    def save(self, entity_type: str, code: str, data: dict[str, Any]) -> None:
        """Write a single entity atomically."""
        ...

    def get(self, entity_type: str, code: str) -> dict[str, Any] | None:
        """Read a single entity by code.  Returns ``None`` when not found."""
        ...

    def delete(self, entity_type: str, code: str) -> None:
        """Delete an entity (idempotent — no error if missing)."""
        ...

    def load_index(self, entity_type: str) -> dict[str, dict[str, Any]]:
        """Load the lightweight index ``{code: {name, shard, …}}``."""
        ...

    def save_index(self, entity_type: str, entries: dict[str, dict[str, Any]]) -> None:
        """Persist the full index (no-op for DB-backed implementations)."""
        ...

    def storage_version(self, entity_type: str) -> str:
        """Opaque version identifier for multi-worker cache-invalidation.

        JSON impl: file mtime string.
        DB impl: ``MAX(updated_at)``.
        """
        ...

    def rebuild_index(self, entity_type: str) -> dict[str, dict[str, Any]]:
        """Full-scan all entities and rebuild the index from scratch.

        Used for fault recovery when the index file is lost or corrupted.
        """
        ...

    def save_batch(
        self, entity_type: str, entities: list[tuple[str, dict[str, Any]]]
    ) -> None:
        """Batch-write many entities in a single transaction (OWL import path)."""
        ...
