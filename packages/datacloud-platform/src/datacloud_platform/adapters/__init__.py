"""DataCloud adapter implementations.

These adapters bridge the datacloud-platform Backend Protocols to the
concrete datacloud-data, datacloud-knowledge, and datacloud-server SDKs.
Import them here so that callers can register them in the backend registry.
"""

from __future__ import annotations

from datacloud_platform.adapters.data_adapter import DataCloudDataBackend
from datacloud_platform.adapters.knowledge_adapter import DataCloudKnowledgeBackend
from datacloud_platform.adapters.none_adapters import (
    _NoopExecutionBackend,
    _NoopKnowledgeBackend,
    _NoopOntologyBackend,
    _NoopStorageBackend,
)
from datacloud_platform.adapters.remote_adapter import (
    RemoteKnowledgeBackend,
    RemoteOntologyBackend,
)
from datacloud_platform.adapters.server_adapter import LocalExecutionBackend

__all__ = [
    "DataCloudDataBackend",
    "DataCloudKnowledgeBackend",
    "LocalExecutionBackend",
    "RemoteKnowledgeBackend",
    "RemoteOntologyBackend",
    "_NoopExecutionBackend",
    "_NoopKnowledgeBackend",
    "_NoopOntologyBackend",
    "_NoopStorageBackend",
]
