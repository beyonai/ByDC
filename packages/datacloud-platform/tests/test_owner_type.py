"""Tests for owner_type filtering on flat resource routes.

ownerType is an optional query param that filters resources by ownership scope.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from datacloud_platform import (
    DatacloudPlatform,
    OntologyBaseEntry,
    OntologyBaseRegistry,
)
from datacloud_platform.adapters.json_entity_store import JsonEntityStore
from datacloud_platform.api.server import create_app
from datacloud_platform.backends import registry as _registry
from datacloud_platform.backends.presets import register_preset
from datacloud_platform.backends.registry import (
    register_backend_type,
    register_implementation,
)
from fakes import (
    FakeExecutionBackend,
    FakeOntologyBackend,
    FakeStorageBackend,
    FakeTermBackend,
)

LOCAL = "local-base"


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    _registry._BACKEND_DEFAULTS.clear()
    _registry._IMPLEMENTATIONS.clear()
    from datacloud_platform.backends import presets as _presets

    _presets._PRESETS.clear()


@pytest.fixture
def fakes() -> dict[str, Any]:
    onto_local = FakeOntologyBackend()
    onto_remote = FakeOntologyBackend()
    onto_remote._readonly = True
    know = FakeTermBackend()
    exec_ = FakeExecutionBackend()
    stor = FakeStorageBackend()
    return {
        "onto_local": onto_local,
        "onto_remote": onto_remote,
        "term": know,
        "execution": exec_,
        "storage": stor,
    }


@pytest.fixture
def client(fakes: dict[str, Any], entity_store: JsonEntityStore) -> TestClient:
    onto_local = fakes["onto_local"]
    onto_remote = fakes["onto_remote"]
    know = fakes["term"]
    exec_ = fakes["execution"]
    stor = fakes["storage"]

    register_backend_type("ontology", "fake-data")
    register_backend_type("term", "fake-knowledge")
    register_backend_type("execution", "fake-exec")
    register_backend_type("storage", "fake-data")

    register_implementation("ontology", "fake-data", lambda: onto_local)
    register_implementation("ontology", "remote-http", lambda: onto_remote)
    register_implementation("term", "fake-knowledge", lambda: know)
    register_implementation("execution", "fake-exec", lambda: exec_)
    register_implementation("storage", "fake-data", lambda: stor)
    register_implementation("execution", "none", lambda: None)
    register_implementation("storage", "none", lambda: None)

    register_preset("LOCAL", {})
    register_preset(
        "REMOTE",
        {
            "ontology": "remote-http",
            "term": "fake-knowledge",
            "execution": "none",
            "storage": "none",
        },
    )

    registry = OntologyBaseRegistry(entity_store)
    registry.register(
        OntologyBaseEntry(base_id=LOCAL, display_name="本地库", source_type="LOCAL")
    )

    platform = DatacloudPlatform(_base_registry=registry)
    platform._fakes = (onto_local, onto_remote, know, exec_, stor)

    app = create_app(platform)
    return TestClient(app)


class TestOwnerType:
    """Tests for owner_type query parameter behaviour."""

    def test_default_owner_type_is_enterprise(self) -> None:
        """Verify that ObjectType model defaults owner_type to 'enterprise'."""
        from datacloud_platform.models.object_type import ObjectType

        obj = ObjectType(objectCode="test", objectName="测试", baseId=LOCAL)
        assert obj.owner_type == "enterprise"

    def test_owner_type_personal_ignores_user_code(self, client: TestClient) -> None:
        """ownerType=personal with userCode is accepted by the API."""
        resp = client.get(
            f"/api/v1/ontologyBases/objects?base_id={LOCAL}"
            f"&ownerType=personal&userCode=user123"
        )
        assert resp.status_code == 200

    def test_owner_type_enterprise_accepted(self, client: TestClient) -> None:
        """ownerType=enterprise without userCode is valid."""
        resp = client.get(
            f"/api/v1/ontologyBases/objects?base_id={LOCAL}&ownerType=enterprise"
        )
        assert resp.status_code == 200

    def test_invalid_owner_type_still_processed(self, client: TestClient) -> None:
        """Invalid ownerType values are passed through (backend handles validation)."""
        resp = client.get(
            f"/api/v1/ontologyBases/objects?base_id={LOCAL}&ownerType=invalid_value"
        )
        # Route doesn't validate ownerType — it's passed as a string query param
        assert resp.status_code == 200

    def test_owner_type_views_route(self, client: TestClient) -> None:
        """ownerType param on views route works."""
        resp = client.get(
            f"/api/v1/ontologyBases/views?base_id={LOCAL}&ownerType=enterprise"
        )
        assert resp.status_code == 200

    def test_owner_type_relations_route(self, client: TestClient) -> None:
        """ownerType param on relations route works."""
        resp = client.get(
            f"/api/v1/ontologyBases/relations?base_id={LOCAL}&ownerType=enterprise"
        )
        assert resp.status_code == 200
