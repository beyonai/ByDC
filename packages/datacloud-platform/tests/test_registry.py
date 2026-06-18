"""Tests for backend registry: register, get, verify."""

from __future__ import annotations

import pytest
from datacloud_platform.backends.registry import (
    get_ontology_backend,
    register_execution_backend,
    register_knowledge_backend,
    register_ontology_backend,
    register_storage_backend,
    verify_backend_registration,
)
from fakes import (
    FakeExecutionBackend,
    FakeKnowledgeBackend,
    FakeOntologyBackend,
    FakeStorageBackend,
)


def test_register_and_get() -> None:
    """Register a backend factory then get returns a new instance."""
    register_ontology_backend("test-data", FakeOntologyBackend)
    instance = get_ontology_backend("test-data")
    assert isinstance(instance, FakeOntologyBackend)


def test_get_missing_backend_raises_keyerror() -> None:
    """Getting an unregistered backend name raises KeyError."""
    with pytest.raises(KeyError, match="not registered"):
        get_ontology_backend("nonexistent")


def test_duplicate_registration_raises() -> None:
    """Registering the same name twice raises ValueError."""
    register_knowledge_backend("dup-know", FakeKnowledgeBackend)
    with pytest.raises(ValueError, match="already registered"):
        register_knowledge_backend("dup-know", FakeKnowledgeBackend)


def test_verify_all_registered() -> None:
    """verify_backend_registration succeeds when all 4 backends are registered."""
    register_ontology_backend("d1", FakeOntologyBackend)
    register_knowledge_backend("d2", FakeKnowledgeBackend)
    register_execution_backend("d3", FakeExecutionBackend)
    register_storage_backend("d4", FakeStorageBackend)
    # Should not raise
    verify_backend_registration()


def test_verify_missing_backend_raises() -> None:
    """verify_backend_registration raises RuntimeError when any dimension
    has zero implementations."""
    from datacloud_platform.backends.registry import (
        register_backend_type,
        register_implementation,
    )

    register_backend_type("ontology", "datacloud-data")
    register_implementation("ontology", "datacloud-data", FakeOntologyBackend)
    register_backend_type("knowledge", "datacloud-knowledge")
    register_implementation("knowledge", "datacloud-knowledge", FakeKnowledgeBackend)
    register_backend_type("execution", "datacloud-server")
    register_implementation("execution", "datacloud-server", FakeExecutionBackend)
    # Register storage dimension but NO implementation
    register_backend_type("storage", "datacloud-data")

    with pytest.raises(RuntimeError, match="No implementations registered"):
        verify_backend_registration()
