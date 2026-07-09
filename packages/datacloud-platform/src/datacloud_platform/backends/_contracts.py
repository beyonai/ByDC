"""Mixin extension contracts — Protocols for DatacloudPlatform Mixin type validation.

Each Protocol declares the routing methods a Mixin requires from the host
DatacloudPlatform instance. Mixins annotate ``self`` with the relevant Protocol
so mypy can verify that the host provides the expected interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from datacloud_platform.ontology_store import OntologyStore

if TYPE_CHECKING:
    from datacloud_platform.backends.execution import ExecutionBackend
    from datacloud_platform.backends.ontology import OntologyBackend, OntologyQueryable
    from datacloud_platform.backends.storage import StorageBackend
    from datacloud_platform.backends.term import TermBackend


class _HasOntologyBackend(Protocol):
    """Requires ``_ontology_for(base_id)`` and ``_load_ontology_cached`` routing."""

    def _ontology_for(self, base_id: str) -> OntologyBackend: ...
    def _load_ontology_cached(
        self, base_id: str, **_kwargs: Any
    ) -> OntologyQueryable: ...
    @property
    def _ontology_store(self) -> OntologyStore | None: ...


class _HasTermBackend(Protocol):
    """Requires ``_term_for(base_id)`` routing."""

    def _term_for(self, base_id: str) -> TermBackend: ...


class _HasExecutionBackend(Protocol):
    """Requires ``_execution_for(base_id)`` routing."""

    def _execution_for(self, base_id: str) -> ExecutionBackend | None: ...


class _HasStorageBackend(Protocol):
    """Requires ``_storage_for(base_id)`` routing."""

    def _storage_for(self, base_id: str) -> StorageBackend | None: ...


class _HasOntologyAndTermBackend(_HasOntologyBackend, _HasTermBackend, Protocol):
    """Requires both OntologyBackend and TermBackend routing.

    Combined protocol for KnowledgeMixin methods that orchestrate across both domains.
    """


class _HasBasePath(Protocol):
    """Requires ``_base_path_for(base_id)`` routing — used by orchestration mixins."""

    def _base_path_for(self, base_id: str) -> Path: ...
