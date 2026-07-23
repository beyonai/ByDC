"""DataCloudDataBackend — composed from all backend mixins."""

from __future__ import annotations

from datacloud_platform.adapters.data_adapter._ontology import OntologyBackendMixin
from datacloud_platform.adapters.data_adapter._ontology_metadata import (
    OntologyMetadataMixin,
)
from datacloud_platform.adapters.data_adapter._scene import SceneMixin
from datacloud_platform.adapters.data_adapter._storage import StorageBackendMixin
from datacloud_platform.adapters.data_adapter._sync import SyncMixin
from datacloud_platform.adapters.data_adapter._term import TermBackendMixin
from datacloud_platform.adapters.data_adapter._term_entity import TermEntityMixin
from datacloud_platform.adapters.data_adapter._vector import VectorBackendMixin


class DataCloudDataBackend(
    OntologyBackendMixin,
    OntologyMetadataMixin,
    SceneMixin,
    StorageBackendMixin,
    TermBackendMixin,
    TermEntityMixin,
    VectorBackendMixin,
    SyncMixin,
):
    """OntologyBackend + TermBackend + StorageBackend via SDKs.

    Each method imports the concrete SDK class locally so the package
    does not hard-depend on datacloud-data at import time.
    """
