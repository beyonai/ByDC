"""Backend Protocol exports."""

from __future__ import annotations

from datacloud_platform.backends._contracts import (
    _HasBasePath,
    _HasExecutionBackend,
    _HasKnowledgeBackend,
    _HasOntologyBackend,
    _HasStorageBackend,
)
from datacloud_platform.backends.execution import ExecutionBackend
from datacloud_platform.backends.knowledge import KnowledgeBackend
from datacloud_platform.backends.ontology import OntologyBackend, OntologyQueryable
from datacloud_platform.backends.storage import StorageBackend

__all__ = [
    "ExecutionBackend",
    "KnowledgeBackend",
    "OntologyBackend",
    "OntologyQueryable",
    "StorageBackend",
    "_HasBasePath",
    "_HasExecutionBackend",
    "_HasKnowledgeBackend",
    "_HasOntologyBackend",
    "_HasStorageBackend",
]
