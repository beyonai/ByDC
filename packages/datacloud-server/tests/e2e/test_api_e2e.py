"""End-to-end tests for the ontology server API.

Tests the full HTTP stack: FastAPI routes -> OntologyService -> Registry -> Adapter.
"""
from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest
from datacloud_server.adapters.local_adapter import LocalOntologyAdapter
from datacloud_server.api.app import create_app
from datacloud_server.registry.registry import OntologyBaseRegistry
from datacloud_server.storage.json_writer import JSONWriter
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create a FastAPI TestClient with real routes and in-memory registry."""
    registry = OntologyBaseRegistry()
    writer = JSONWriter()
    local = LocalOntologyAdapter(str(tmp_path), writer)

    app = create_app(registry=registry, local_adapter=local)
    return TestClient(app)


class TestOntologyBaseAPI:
    """OntologyBase CRUD API."""

    def test_create_local_base(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/ontologyBases",
            json={
                "baseId": "my_base",
                "displayName": "My Base",
                "ownerType": "personal",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["success"] is True
        assert body["data"]["sourceType"] == "LOCAL"

    def test_create_remote_base(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/ontologyBases",
            json={
                "baseId": "remote_base",
                "displayName": "Remote Base",
                "ownerType": "enterprise",
                "sourceUrl": "https://example.com/api",
                "authType": "bearer",
                "authConfig": {"token": "secret"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["sourceType"] == "REMOTE"

    def test_create_duplicate_base_returns_400(self, client: TestClient) -> None:
        client.post(
            "/api/v1/ontologyBases",
            json={"baseId": "dup", "displayName": "Dup"},
        )
        resp = client.post(
            "/api/v1/ontologyBases",
            json={"baseId": "dup", "displayName": "Dup2"},
        )
        assert resp.status_code == 400

    def test_list_bases(self, client: TestClient) -> None:
        client.post("/api/v1/ontologyBases", json={"baseId": "b1", "displayName": "B1"})
        client.post("/api/v1/ontologyBases", json={"baseId": "b2", "displayName": "B2"})
        resp = client.get("/api/v1/ontologyBases")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_delete_base(self, client: TestClient) -> None:
        client.post(
            "/api/v1/ontologyBases",
            json={"baseId": "to_delete", "displayName": "Delete Me"},
        )
        resp = client.delete("/api/v1/ontologyBases/to_delete")
        assert resp.status_code == 200
        resp2 = client.get("/api/v1/ontologyBases")
        assert len(resp2.json()["data"]) == 0

    def test_get_nonexistent_base_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/ontologyBases/nope/scenes")
        assert resp.status_code == 404


class TestObjectAPI:
    """Object CRUD API."""

    @pytest.fixture
    def base_client(self, client: TestClient) -> TestClient:
        """Client with a pre-created LOCAL base."""
        client.post(
            "/api/v1/ontologyBases",
            json={"baseId": "local_base", "displayName": "Local Base"},
        )
        return client

    def test_create_and_get_object(self, base_client: TestClient) -> None:
        resp = base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/objects",
            json={
                "objectCode": "customer",
                "objectName": "Customer",
                "fields": [{"fieldCode": "name", "fieldName": "Name", "fieldType": "STRING"}],
            },
        )
        assert resp.status_code == 200

        resp2 = base_client.get(
            "/api/v1/ontologyBases/local_base/scenes/default/objects"
        )
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]) == 1

        resp3 = base_client.get(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/customer"
        )
        assert resp3.status_code == 200
        assert resp3.json()["data"]["objectCode"] == "customer"

    def test_delete_object(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/objects",
            json={"objectCode": "temp", "objectName": "Temp"},
        )
        resp = base_client.delete(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/temp"
        )
        assert resp.status_code == 200

        resp2 = base_client.get(
            "/api/v1/ontologyBases/local_base/scenes/default/objects"
        )
        assert len(resp2.json()["data"]) == 0

    def test_create_object_nonexistent_base_returns_404(
        self, base_client: TestClient
    ) -> None:
        resp = base_client.post(
            "/api/v1/ontologyBases/nope/scenes/default/objects",
            json={"objectCode": "x", "objectName": "X"},
        )
        assert resp.status_code == 404

    def test_list_scenes(self, base_client: TestClient) -> None:
        resp = base_client.get("/api/v1/ontologyBases/local_base/scenes")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)
