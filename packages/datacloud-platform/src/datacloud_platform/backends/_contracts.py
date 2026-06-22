"""Mixin extension contracts — pre-built Protocols for future Mixin mypy validation.

DatacloudPlatform is currently ~60 lines, no Mixin split needed.
Split threshold: when a domain has 3+ orchestration methods spanning 2+ Backends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datacloud_platform.backends.execution import ExecutionBackend
    from datacloud_platform.backends.knowledge import KnowledgeBackend
    from datacloud_platform.backends.ontology import OntologyBackend
    from datacloud_platform.backends.storage import StorageBackend


class _HasOntologyBackend(Protocol):
    _ontology: OntologyBackend


class _HasKnowledgeBackend(Protocol):
    _knowledge: KnowledgeBackend


class _HasExecutionBackend(Protocol):
    _execution: ExecutionBackend


class _HasStorageBackend(Protocol):
    _storage: StorageBackend
