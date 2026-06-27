"""Mixin extension contracts — Protocols for DatacloudPlatform Mixin type validation.

Each Protocol declares the routing methods a Mixin requires from the host
DatacloudPlatform instance. Mixins annotate ``self`` with the relevant Protocol
so mypy can verify that the host provides the expected interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from datacloud_platform.ontology_store import CacheMode, OntologyStore

if TYPE_CHECKING:
    from datacloud_platform.backends.execution import ExecutionBackend
    from datacloud_platform.backends.knowledge import KnowledgeBackend
    from datacloud_platform.backends.ontology import OntologyBackend, OntologyQueryable
    from datacloud_platform.backends.storage import StorageBackend


class _HasOntologyBackend(Protocol):
    """Requires ``_ontology_for(base_id)`` and ``_load_ontology_cached`` routing."""

    def _ontology_for(self, base_id: str) -> OntologyBackend: ...
    def _load_ontology_cached(
        self, base_id: str, cache_mode: CacheMode = CacheMode.REALTIME
    ) -> OntologyQueryable: ...
    @property
    def _ontology_store(self) -> OntologyStore | None: ...


class _HasKnowledgeBackend(Protocol):
    """Requires ``_knowledge_for(base_id)`` routing."""

    def _knowledge_for(self, base_id: str) -> KnowledgeBackend: ...


class _HasExecutionBackend(Protocol):
    """Requires ``_execution_for(base_id)`` routing."""

    def _execution_for(self, base_id: str) -> ExecutionBackend | None: ...


class _HasStorageBackend(Protocol):
    """Requires ``_storage_for(base_id)`` routing."""

    def _storage_for(self, base_id: str) -> StorageBackend | None: ...


class _HasBasePath(Protocol):
    """Requires ``_base_path_for(base_id)`` routing — used by orchestration mixins."""

    def _base_path_for(self, base_id: str) -> Path: ...
