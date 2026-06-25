"""Shared test fixtures for datacloud_platform tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from datacloud_platform import (
    DatacloudPlatform,
    OntologyBaseEntry,
    OntologyBaseRegistry,
)
from datacloud_platform.adapters.json_entity_store import JsonEntityStore
from datacloud_platform.backends import registry as _registry
from datacloud_platform.backends.presets import register_preset
from datacloud_platform.backends.registry import (
    register_backend_type,
    register_implementation,
)
from fakes import (
    FakeExecutionBackend,
    FakeKnowledgeBackend,
    FakeOntologyBackend,
    FakeStorageBackend,
)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Reset all backend registries before each test to ensure isolation."""
    _registry._BACKEND_DEFAULTS.clear()
    _registry._IMPLEMENTATIONS.clear()
    from datacloud_platform.backends import presets as _presets

    _presets._PRESETS.clear()


@pytest.fixture
def entity_store():
    """Provide a temporary JsonEntityStore for tests."""
    with tempfile.TemporaryDirectory() as d:
        yield JsonEntityStore(Path(d))


@pytest.fixture
def platform(entity_store: JsonEntityStore) -> DatacloudPlatform:
    """Build a multi-base DatacloudPlatform backed entirely by Fake backends.

    Registers one LOCAL base and one REMOTE base.
    All backends are in-memory; no external system is contacted.
    The ``_fakes`` attribute gives direct access to the fake instances
    for test setup/assertions: ``(onto_local, onto_remote, know, exec_, stor)``.
    """
    onto_local = FakeOntologyBackend()
    onto_remote = FakeOntologyBackend()
    onto_remote._readonly = True
    know = FakeKnowledgeBackend()
    exec_ = FakeExecutionBackend()
    stor = FakeStorageBackend()

    # Register dimensions
    register_backend_type("ontology", "fake-data")
    register_backend_type("knowledge", "fake-knowledge")
    register_backend_type("execution", "fake-exec")
    register_backend_type("storage", "fake-data")

    # Register implementations
    register_implementation("ontology", "fake-data", lambda: onto_local)
    register_implementation("ontology", "remote-http", lambda: onto_remote)
    register_implementation("knowledge", "fake-knowledge", lambda: know)
    register_implementation("execution", "fake-exec", lambda: exec_)
    register_implementation("storage", "fake-data", lambda: stor)
    register_implementation("execution", "none", lambda: None)  # type: ignore[arg-type,return-value]
    register_implementation("storage", "none", lambda: None)  # type: ignore[arg-type,return-value]

    # Presets
    register_preset("LOCAL", {})
    register_preset(
        "REMOTE",
        {
            "ontology": "remote-http",
            "knowledge": "fake-knowledge",
            "execution": "none",
            "storage": "none",
        },
    )

    # Registry with one LOCAL and one REMOTE base
    registry = OntologyBaseRegistry(entity_store)
    registry.register(
        OntologyBaseEntry(
            base_id="local-base",
            display_name="本地库",
            source_type="LOCAL",
        )
    )
    registry.register(
        OntologyBaseEntry(
            base_id="remote-base",
            display_name="远程库",
            source_type="REMOTE",
        )
    )

    p = DatacloudPlatform(_base_registry=registry, _entity_store=entity_store)
    p._fakes = (onto_local, onto_remote, know, exec_, stor)  # type: ignore[attr-defined]
    return p
