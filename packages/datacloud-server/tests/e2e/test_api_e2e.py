"""End-to-end tests for the ontology server API.

Tests the full HTTP stack: FastAPI routes -> OntologyService -> Registry -> Adapter.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

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

        resp2 = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/objects")
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]) == 1

        resp3 = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/objects/customer")
        assert resp3.status_code == 200
        assert resp3.json()["data"]["objectCode"] == "customer"

    def test_delete_object(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/objects",
            json={"objectCode": "temp", "objectName": "Temp"},
        )
        resp = base_client.delete("/api/v1/ontologyBases/local_base/scenes/default/objects/temp")
        assert resp.status_code == 200

        resp2 = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/objects")
        assert len(resp2.json()["data"]) == 0

    def test_create_object_nonexistent_base_returns_404(self, base_client: TestClient) -> None:
        resp = base_client.post(
            "/api/v1/ontologyBases/nope/scenes/default/objects",
            json={"objectCode": "x", "objectName": "X"},
        )
        assert resp.status_code == 404

    def test_list_scenes(self, base_client: TestClient) -> None:
        resp = base_client.get("/api/v1/ontologyBases/local_base/scenes")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


class TestViewAPI:
    """View CRUD API."""

    @pytest.fixture
    def base_client(self, client: TestClient) -> TestClient:
        """Client with a pre-created LOCAL base."""
        client.post(
            "/api/v1/ontologyBases",
            json={"baseId": "local_base", "displayName": "Local Base"},
        )
        return client

    def test_create_and_list_views(self, base_client: TestClient) -> None:
        resp = base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/views",
            json={
                "viewCode": "sales_view",
                "viewName": "Sales View",
                "objectCodes": ["customer", "order"],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["viewCode"] == "sales_view"

        resp2 = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/views")
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]) == 1

    def test_get_view_detail(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/views",
            json={"viewCode": "detail_view", "viewName": "Detail View"},
        )
        resp = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/views/detail_view")
        assert resp.status_code == 200
        assert resp.json()["data"]["viewCode"] == "detail_view"

    def test_get_nonexistent_view_returns_404(self, base_client: TestClient) -> None:
        resp = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/views/no_such")
        assert resp.status_code == 404

    def test_delete_view(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/views",
            json={"viewCode": "to_delete", "viewName": "Delete Me"},
        )
        resp = base_client.delete("/api/v1/ontologyBases/local_base/scenes/default/views/to_delete")
        assert resp.status_code == 200
        resp2 = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/views")
        assert len(resp2.json()["data"]) == 0

    def test_create_view_on_remote_returns_403(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases",
            json={
                "baseId": "remote_base",
                "displayName": "Remote Base",
                "sourceUrl": "https://example.com/api",
            },
        )
        resp = base_client.post(
            "/api/v1/ontologyBases/remote_base/scenes/default/views",
            json={"viewCode": "v1", "viewName": "V1"},
        )
        assert resp.status_code == 403

    def test_create_duplicate_view_returns_400(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/views",
            json={"viewCode": "dup_view", "viewName": "First"},
        )
        resp = base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/views",
            json={"viewCode": "dup_view", "viewName": "Second"},
        )
        assert resp.status_code == 400


class TestRelationAPI:
    """Relation CRUD API."""

    @pytest.fixture
    def base_client(self, client: TestClient) -> TestClient:
        """Client with a pre-created LOCAL base."""
        client.post(
            "/api/v1/ontologyBases",
            json={"baseId": "local_base", "displayName": "Local Base"},
        )
        return client

    def test_create_and_list_relations(self, base_client: TestClient) -> None:
        resp = base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/relations",
            json={
                "relationCode": "has_order",
                "relationName": "Has Order",
                "sourceClass": "customer",
                "targetClass": "order",
                "relationType": "ONE_TO_MANY",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["relationCode"] == "has_order"

        resp2 = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/relations")
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]) == 1

    def test_get_relation_detail(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/relations",
            json={"relationCode": "detail_rel", "relationName": "Detail Rel"},
        )
        resp = base_client.get(
            "/api/v1/ontologyBases/local_base/scenes/default/relations/detail_rel"
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["relationCode"] == "detail_rel"

    def test_delete_relation(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/relations",
            json={"relationCode": "to_delete", "relationName": "Delete Me"},
        )
        resp = base_client.delete(
            "/api/v1/ontologyBases/local_base/scenes/default/relations/to_delete"
        )
        assert resp.status_code == 200
        resp2 = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/relations")
        assert len(resp2.json()["data"]) == 0

    def test_create_relation_on_remote_returns_403(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases",
            json={
                "baseId": "remote_base",
                "displayName": "Remote Base",
                "sourceUrl": "https://example.com/api",
            },
        )
        resp = base_client.post(
            "/api/v1/ontologyBases/remote_base/scenes/default/relations",
            json={"relationCode": "r1", "relationName": "R1"},
        )
        assert resp.status_code == 403

    def test_create_duplicate_relation_returns_400(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/relations",
            json={"relationCode": "dup_rel", "relationName": "First"},
        )
        resp = base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/relations",
            json={"relationCode": "dup_rel", "relationName": "Second"},
        )
        assert resp.status_code == 400


# ─── OWL import ZIP path ───────────────────────

OWL_EXAMPLE_DIR = Path("/workspace/projects/ontology_server/owl_example")


class TestDatasourceAPI:
    """Datasource CRUD API."""

    @pytest.fixture
    def base_client(self, client: TestClient) -> TestClient:
        """Client with a pre-created LOCAL base."""
        client.post(
            "/api/v1/ontologyBases",
            json={"baseId": "local_base", "displayName": "Local Base"},
        )
        return client

    def test_create_and_list_datasources(self, base_client: TestClient) -> None:
        resp = base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/datasources",
            json={
                "dbId": "pg_main",
                "dbName": "Main PostgreSQL",
                "dbType": "opengauss",
                "host": "10.10.168.200",
                "port": 5432,
                "database": "postgres",
                "schema": "byai",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["dbId"] == "pg_main"

        resp2 = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/datasources")
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]) == 1

    def test_get_datasource_detail(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/datasources",
            json={"dbId": "detail_db", "dbName": "Detail DB"},
        )
        resp = base_client.get(
            "/api/v1/ontologyBases/local_base/scenes/default/datasources/detail_db"
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["dbId"] == "detail_db"

    def test_delete_datasource(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/datasources",
            json={"dbId": "to_delete", "dbName": "Delete Me"},
        )
        resp = base_client.delete(
            "/api/v1/ontologyBases/local_base/scenes/default/datasources/to_delete"
        )
        assert resp.status_code == 200
        resp2 = base_client.get("/api/v1/ontologyBases/local_base/scenes/default/datasources")
        assert len(resp2.json()["data"]) == 0

    def test_create_datasource_on_remote_returns_403(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases",
            json={
                "baseId": "remote_base",
                "displayName": "Remote Base",
                "sourceUrl": "https://example.com/api",
            },
        )
        resp = base_client.post(
            "/api/v1/ontologyBases/remote_base/scenes/default/datasources",
            json={"dbId": "ds1", "dbName": "DS1"},
        )
        assert resp.status_code == 403

    def test_create_duplicate_datasource_returns_400(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/datasources",
            json={"dbId": "dup_db", "dbName": "First"},
        )
        resp = base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/datasources",
            json={"dbId": "dup_db", "dbName": "Second"},
        )
        assert resp.status_code == 400


# ─── OWL import ZIP path ───────────────────────

OWL_EXAMPLE_DIR = Path("/workspace/projects/ontology_server/owl_example")


class TestActionAPI:
    """Action CRUD API (nested under objects)."""

    @pytest.fixture
    def base_client(self, client: TestClient) -> TestClient:
        """Client with a pre-created LOCAL base and object."""
        client.post(
            "/api/v1/ontologyBases",
            json={"baseId": "local_base", "displayName": "Local Base"},
        )
        client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/objects",
            json={
                "objectCode": "customer",
                "objectName": "Customer",
                "fields": [{"fieldCode": "name", "fieldName": "Name", "fieldType": "STRING"}],
            },
        )
        return client

    def test_create_and_list_actions(self, base_client: TestClient) -> None:
        resp = base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/customer/actions",
            json={
                "actionCode": "search_customers",
                "actionName": "Search Customers",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["actionCode"] == "search_customers"

        resp2 = base_client.get(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/customer/actions"
        )
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]) == 1

    def test_get_action_detail(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/customer/actions",
            json={"actionCode": "detail_action", "actionName": "Detail Action"},
        )
        resp = base_client.get(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/customer/actions/detail_action"
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["actionCode"] == "detail_action"

    def test_delete_action(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/customer/actions",
            json={"actionCode": "to_delete", "actionName": "Delete Me"},
        )
        resp = base_client.delete(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/customer/actions/to_delete"
        )
        assert resp.status_code == 200
        resp2 = base_client.get(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/customer/actions"
        )
        assert len(resp2.json()["data"]) == 0

    def test_create_action_on_remote_returns_403(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases",
            json={
                "baseId": "remote_base",
                "displayName": "Remote Base",
                "sourceUrl": "https://example.com/api",
            },
        )
        resp = base_client.post(
            "/api/v1/ontologyBases/remote_base/scenes/default/objects/customer/actions",
            json={"actionCode": "a1", "actionName": "A1"},
        )
        assert resp.status_code == 403

    def test_create_duplicate_action_returns_400(self, base_client: TestClient) -> None:
        base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/customer/actions",
            json={"actionCode": "dup_action", "actionName": "First"},
        )
        resp = base_client.post(
            "/api/v1/ontologyBases/local_base/scenes/default/objects/customer/actions",
            json={"actionCode": "dup_action", "actionName": "Second"},
        )
        assert resp.status_code == 400


class TestImportOWLAPI:
    """OWL ZIP import API."""

    @pytest.fixture
    def base_client(self, client: TestClient) -> TestClient:
        """Client with a pre-created LOCAL base."""
        client.post(
            "/api/v1/ontologyBases",
            json={"baseId": "local_base", "displayName": "Local Base"},
        )
        return client

    @staticmethod
    def _make_owl_zip(zip_path: Path, source_dir: Path) -> Path:
        """Create a ZIP from the OWL resource directory."""
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in sorted(source_dir.rglob("*")):
                if fpath.is_file():
                    arcname = fpath.relative_to(source_dir)
                    zf.write(fpath, arcname)
        return zip_path

    def test_import_owl_succeeds(self, base_client: TestClient, tmp_path: Path) -> None:
        """Upload OWL ZIP -> parsed and written to data dir."""
        zip_path = tmp_path / "owl_import.zip"
        self._make_owl_zip(zip_path, OWL_EXAMPLE_DIR)

        with zip_path.open("rb") as f:
            resp = base_client.post(
                "/api/v1/ontologyBases/local_base/scenes/default/import-owl",
                files={"file": ("owl_import.zip", f, "application/zip")},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["success"] is True
        data = body.get("data", {})
        assert data.get("objects", 0) > 0
        assert data.get("views", 0) > 0
        assert data.get("relations", 0) >= 0

    def test_import_owl_on_remote_returns_403(
        self, base_client: TestClient, tmp_path: Path
    ) -> None:
        """REMOTE base rejects OWL import."""
        base_client.post(
            "/api/v1/ontologyBases",
            json={
                "baseId": "remote_base",
                "displayName": "Remote Base",
                "sourceUrl": "https://example.com/api",
            },
        )
        zip_path = tmp_path / "owl_import.zip"
        self._make_owl_zip(zip_path, OWL_EXAMPLE_DIR)

        with zip_path.open("rb") as f:
            resp = base_client.post(
                "/api/v1/ontologyBases/remote_base/scenes/default/import-owl",
                files={"file": ("owl_import.zip", f, "application/zip")},
            )

        assert resp.status_code == 403

    def test_import_owl_nonexistent_base_returns_404(
        self, base_client: TestClient, tmp_path: Path
    ) -> None:
        """Nonexistent base returns 404."""
        zip_path = tmp_path / "owl_import.zip"
        self._make_owl_zip(zip_path, OWL_EXAMPLE_DIR)

        with zip_path.open("rb") as f:
            resp = base_client.post(
                "/api/v1/ontologyBases/nope/scenes/default/import-owl",
                files={"file": ("owl_import.zip", f, "application/zip")},
            )

        assert resp.status_code == 404
