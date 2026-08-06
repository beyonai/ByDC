"""DataCloud adapter implementations.

These adapters bridge the datacloud-platform Backend Protocols to the
concrete datacloud-data, datacloud-knowledge, and datacloud-server SDKs.
Import them here so that callers can register them in the backend registry.
"""

from __future__ import annotations

from datacloud_platform.adapters.data_adapter._composite import DataCloudDataBackend
from datacloud_platform.adapters.local_execution_adapter import LocalExecutionBackend
from datacloud_platform.adapters.document_library_adapter import (
    ServiceDiscoveryDocumentLibraryBackend,
)
from datacloud_platform.adapters.none_adapters import (
    _NoopExecutionBackend,
    _NoopDocumentLibraryBackend,
    _NoopOntologyBackend,
    _NoopStorageBackend,
    _NoopTermBackend,
)
from datacloud_platform.adapters.remote_adapter import (
    RemoteOntologyBackend,
    RemoteTermBackend,
)

__all__ = [
    "DataCloudDataBackend",
    "LocalExecutionBackend",
    "ServiceDiscoveryDocumentLibraryBackend",
    "RemoteOntologyBackend",
    "RemoteTermBackend",
    "_NoopExecutionBackend",
    "_NoopDocumentLibraryBackend",
    "_NoopOntologyBackend",
    "_NoopStorageBackend",
    "_NoopTermBackend",
]
