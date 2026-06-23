"""datacloud-platform — unified ontology/knowledge/execution/storage backend abstraction.

Usage::

    from datacloud_platform import DatacloudPlatform, OntologyBaseRegistry

    registry = OntologyBaseRegistry()
    registry.register(OntologyBaseEntry(base_id="my-base", display_name="My Base"))
    platform = DatacloudPlatform(_base_registry=registry)
    results = platform.search("my-base", "sales")
"""

from __future__ import annotations

from datacloud_platform.backends import (
    ExecutionBackend,
    KnowledgeBackend,
    OntologyBackend,
    OntologyQueryable,
    StorageBackend,
    _HasExecutionBackend,
    _HasKnowledgeBackend,
    _HasOntologyBackend,
    _HasStorageBackend,
)
from datacloud_platform.backends.presets import register_preset
from datacloud_platform.backends.registry import (
    BackendFactory,
    ExecutionBackendFactory,
    KnowledgeBackendFactory,
    OntologyBackendFactory,
    StorageBackendFactory,
    get_backend_factory,
    get_execution_backend,
    get_knowledge_backend,
    get_ontology_backend,
    get_storage_backend,
    register_backend_type,
    register_execution_backend,
    register_implementation,
    register_knowledge_backend,
    register_ontology_backend,
    register_storage_backend,
    verify_backend_registration,
)
from datacloud_platform.backends.resolution import resolve_backend_names
from datacloud_platform.base_entry import (
    OntologyBaseEntry,
    OntologyBaseRegistry,
    generate_snowflake,
    validate_base_id,
)
from datacloud_platform.models.base_entry import (
    OntologyBaseCreate,
    OntologyBaseUpdate,
)
from datacloud_platform.models.shared import (
    DimensionProperty,
    EmbeddingHit,
    MatchCandidate,
    MatchResult,
    ObjectSummary,
    ParsedOwlContent,
    ReferenceProperty,
    RelationSummary,
    ScoreUpdateRecord,
    StoredFile,
    ViewSummary,
)
from datacloud_platform.platform import DatacloudPlatform

__all__ = [
    "BackendFactory",
    "DatacloudPlatform",
    "DimensionProperty",
    "EmbeddingHit",
    "ExecutionBackend",
    "ExecutionBackendFactory",
    "KnowledgeBackend",
    "KnowledgeBackendFactory",
    "MatchCandidate",
    "MatchResult",
    "ObjectSummary",
    "OntologyBackend",
    "OntologyBackendFactory",
    "OntologyBaseCreate",
    "OntologyBaseEntry",
    "OntologyBaseRegistry",
    "OntologyBaseUpdate",
    "OntologyQueryable",
    "ParsedOwlContent",
    "ReferenceProperty",
    "RelationSummary",
    "ScoreUpdateRecord",
    "StorageBackend",
    "StorageBackendFactory",
    "StoredFile",
    "ViewSummary",
    "_HasExecutionBackend",
    "_HasKnowledgeBackend",
    "_HasOntologyBackend",
    "_HasStorageBackend",
    "generate_snowflake",
    "get_backend_factory",
    "get_execution_backend",
    "get_knowledge_backend",
    "get_ontology_backend",
    "get_platform",
    "get_storage_backend",
    "register_backend_type",
    "register_execution_backend",
    "register_implementation",
    "register_knowledge_backend",
    "register_ontology_backend",
    "register_preset",
    "register_storage_backend",
    "resolve_backend_names",
    "validate_base_id",
    "verify_backend_registration",
]

_platform: DatacloudPlatform | None = None


def get_platform() -> DatacloudPlatform:
    """Return the module-level DatacloudPlatform singleton, lazily initialised."""
    global _platform  # noqa: PLW0603
    if _platform is None:
        _platform = DatacloudPlatform(_base_registry=OntologyBaseRegistry())
    return _platform
