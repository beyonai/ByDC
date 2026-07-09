"""EntityStore Protocol — swappable CRUD abstraction for million-scale ontology entities.

Supports pluggable backends: JSON file store → PostgreSQL / OpenGauss → MongoDB.
"""

from __future__ import annotations

from typing import Any, Protocol


class EntityStore(Protocol):
    """Storage abstraction for Object / View / Relation / Datasource / Action entities.

    ``entity_type`` is one of: ``bases``, ``scenes``, ``objects``, ``views``,
    ``relations``, ``datasources``, ``actions``.
    ``code`` is the stable business identifier (e.g. ``"order"``).

    All CRUD methods accept an optional ``base_id`` keyword-only argument
    for per-base namespace isolation.  Implementations that do not support
    per-base isolation ignore the parameter.
    """

    def save(
        self,
        entity_type: str,
        code: str,
        data: dict[str, Any],
        *,
        base_id: str = "",
    ) -> None:
        """Write a single entity atomically.

        Implementations MUST bump the storage version so downstream caches
        (OntologyStore, SceneMixin, etc.) detect the change on next read.
        """
        ...

    def get(
        self,
        entity_type: str,
        code: str,
        *,
        base_id: str = "",
    ) -> dict[str, Any] | None:
        """Read a single entity by code.  Returns ``None`` when not found."""
        ...

    def delete(
        self,
        entity_type: str,
        code: str,
        *,
        base_id: str = "",
    ) -> None:
        """Delete an entity (idempotent — no error if missing).

        Implementations MUST bump the storage version.
        """
        ...

    def load_index(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> dict[str, dict[str, Any]]:
        """Load the lightweight index — ``{code: {code, name, ...}}``.

        Return value is backend-independent.  Mandatory keys: ``code``, ``name``.
        Implementations MAY add extra keys (e.g. ``field_count``) but MUST NOT
        leak implementation details such as ``shard``.
        """
        ...

    def save_index(
        self,
        entity_type: str,
        entries: dict[str, dict[str, Any]],
        *,
        base_id: str = "",
    ) -> None:
        """Persist the full index.

        Implementations MUST bump the storage version so that
        ``storage_version()`` returns a new value after this call.

        For DB-backed implementations this may be a no-op if the index is
        derived from table data — but the version bump must still occur.
        """
        ...

    def storage_version(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> str:
        """Return a monotonically increasing version string.

        JSON impl: version counter stored in ``_version.json``.
        DB impl: ``MAX(version)`` from the entity table.

        Consumers compare this string with a cached version to detect
        external modifications.  The string's content is opaque — only
        ``==`` comparison is meaningful.
        """
        ...

    def rebuild_index(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> dict[str, dict[str, Any]]:
        """Full-scan all entities and rebuild the index from scratch.

        Used for fault recovery when the index is lost or corrupted.
        For DB-backed implementations this is equivalent to ``load_index()``
        since the table data is always complete.
        """
        ...

    def save_batch(
        self,
        entity_type: str,
        entities: list[tuple[str, dict[str, Any]]],
        *,
        base_id: str = "",
    ) -> None:
        """Batch-write many entities in a single scope.

        Implementations should bump the storage version ONCE at the end,
        not per-entity.

        For transactional backends the entire batch should be atomic.
        """
        ...

    def sub_store(self, namespace: str) -> EntityStore:
        """Return a lightweight view with *namespace* as the default ``base_id``.

        The returned object shares the underlying connection / filesystem
        with the parent store and does NOT create new resources.

        All CRUD methods delegate to the parent store with
        ``base_id=base_id or namespace``.

        JsonEntityStore:   sub_store("my_base") → base_id defaults to "my_base"
        OpenGaussEntityStore: sub_store("my_base") → WHERE base_id='my_base'
        """
        ...

    def list_all(
        self,
        entity_type: str,
        *,
        base_id: str = "",
    ) -> list[dict[str, Any]]:
        """Return all entity data dicts for *entity_type* under *base_id* in one query."""
        ...

    def search(
        self,
        entity_type: str,
        *,
        base_id: str = "",
        keyword: str | None = None,
        codes: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Paginated search with keyword and code-set filtering.

        Args:
            entity_type: One of ``objects``, ``views``, ``relations``, ``actions``,
                ``datasources``.
            base_id: Per-base namespace isolation.
            keyword: Optional case-insensitive substring filter on entity name.
            codes: Optional code whitelist. ``None`` means no filter;
                ``[]`` means match nothing (empty result).
            page: 1-based page number.
            page_size: Maximum items per page.

        Returns:
            ``(items, total)`` where *items* is the current page of entity data dicts
            and *total* is the total number of matching entities (before pagination).
        """
        ...
