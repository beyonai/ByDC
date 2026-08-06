"""Backend Protocol exports."""

from __future__ import annotations

from datacloud_platform.backends._contracts import (
    _HasBasePath,
    _HasExecutionBackend,
    _HasDocumentLibraryBackend,
    _HasOntologyBackend,
    _HasStorageBackend,
    _HasTermBackend,
)
from datacloud_platform.backends.execution import ExecutionBackend
from datacloud_platform.backends.document_library import DocumentLibraryBackend
from datacloud_platform.backends.ontology import OntologyBackend, OntologyQueryable
from datacloud_platform.backends.storage import StorageBackend
from datacloud_platform.backends.term import TermBackend

__all__ = [
    "ExecutionBackend",
    "DocumentLibraryBackend",
    "OntologyBackend",
    "OntologyQueryable",
    "StorageBackend",
    "TermBackend",
    "_HasBasePath",
    "_HasExecutionBackend",
    "_HasDocumentLibraryBackend",
    "_HasOntologyBackend",
    "_HasStorageBackend",
    "_HasTermBackend",
]
