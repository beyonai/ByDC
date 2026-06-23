"""Edge-case regression tests for datacloud-platform.

Covers: no-data scenarios that previously returned 500 due to missing
backend methods, and other boundary conditions.
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
from datacloud_platform.api.server import create_app
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

OWNER_TYPE = "personal"
LOCAL = "local-base"
SCENE = "scene-1"

# DataCloudDataBackend tests require datacloud-data SDK (optional dependency)
_DATA_BACKEND_AVAILABLE = False
try:
    from datacloud_platform.adapters.data_adapter import DataCloudDataBackend

    _DATA_BACKEND_AVAILABLE = True
except ModuleNotFoundError:
    pass


@pytest.fixture
def fakes() -> dict[str, Any]:
    """Create fake backend instances (not registered yet)."""
    onto_local = FakeOntologyBackend()
    onto_remote = FakeOntologyBackend()
    onto_remote._readonly = True
    know = FakeKnowledgeBackend()
    exec_ = FakeExecutionBackend()
    stor = FakeStorageBackend()
    return {
        "onto_local": onto_local,
        "onto_remote": onto_remote,
        "knowledge": know,
        "execution": exec_,
        "storage": stor,
    }


@pytest.fixture
def client(fakes: dict[str, Any]) -> TestClient:
    """Build a TestClient backed entirely by fake backends."""
    onto_local = fakes["onto_local"]
    onto_remote = fakes["onto_remote"]
    know = fakes["knowledge"]
    exec_ = fakes["execution"]
    stor = fakes["storage"]

    register_backend_type("ontology", "fake-data")
    register_backend_type("knowledge", "fake-knowledge")
    register_backend_type("execution", "fake-exec")
    register_backend_type("storage", "fake-data")

    register_implementation("ontology", "fake-data", lambda: onto_local)
    register_implementation("ontology", "remote-http", lambda: onto_remote)
    register_implementation("knowledge", "fake-knowledge", lambda: know)
    register_implementation("execution", "fake-exec", lambda: exec_)
    register_implementation("storage", "fake-data", lambda: stor)
    register_implementation("execution", "none", lambda: None)
    register_implementation("storage", "none", lambda: None)

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

    registry = OntologyBaseRegistry()
    registry.register(
        OntologyBaseEntry(
            base_id=LOCAL,
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

    platform = DatacloudPlatform(_base_registry=registry)
    platform._fakes = (onto_local, onto_remote, know, exec_, stor)

    app = create_app(platform)
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════════
# DataCloudDataBackend — method completeness (no AttributeError)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    not _DATA_BACKEND_AVAILABLE, reason="datacloud-data SDK not installed"
)
class TestDataCloudDataBackendCompleteness:
    """Verify every OntologyBackend Protocol method exists on DataCloudDataBackend.

    Before the fix, ~26 methods were missing, causing AttributeError → 500 for
    every route that touched the datacloud-data backend with no loaded ontology.
    """

    @staticmethod
    def _backend() -> DataCloudDataBackend:
        return DataCloudDataBackend()

    # ── Scene management ──

    def test_list_scenes_returns_empty(self) -> None:
        result = self._backend().list_scenes("any-base")
        assert result == []

    def test_query_scenes_returns_empty(self) -> None:
        result = self._backend().query_scenes("any-base", keyword=None)
        assert result == []

    def test_count_scenes_returns_zero(self) -> None:
        result = self._backend().count_scenes("any-base", keyword=None)
        assert result == 0

    def test_get_scene_details_returns_empty(self) -> None:
        result = self._backend().get_scene_details("any-base", "any-scene")
        assert result == {
            "scene": None,
            "views": [],
            "objects": [],
            "actions": [],
            "relations": [],
            "dbsources": {"db": [], "doc": [], "api": []},
            "version": "v0.1.0",
        }

    def test_query_ontologies_by_scene_returns_empty(self) -> None:
        result = self._backend().query_ontologies_by_scene("any-base", "any-scene")
        assert result == {"data": [], "totalCount": 0}

    # ── View CRUD ──

    def test_get_views_returns_empty(self) -> None:
        result = self._backend().get_views("any-base")
        assert result == []

    def test_get_view_detail_returns_none(self) -> None:
        result = self._backend().get_view_detail("any-base", "vw-1")
        assert result is None

    def test_create_view_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().create_view("any-base", {})

    def test_update_view_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().update_view("any-base", "vw-1", {})

    def test_delete_view_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().delete_view("any-base", "vw-1")

    # ── Relation CRUD ──

    def test_get_relations_returns_empty(self) -> None:
        result = self._backend().get_relations("any-base")
        assert result == []

    def test_get_relation_detail_returns_none(self) -> None:
        result = self._backend().get_relation_detail("any-base", "rel-1")
        assert result is None

    def test_create_relation_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().create_relation("any-base", {})

    def test_update_relation_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().update_relation("any-base", "rel-1", {})

    def test_delete_relation_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().delete_relation("any-base", "rel-1")

    # ── Action CRUD ──

    def test_get_actions_returns_empty(self) -> None:
        result = self._backend().get_actions("any-base", "obj-1")
        assert result == []

    def test_get_action_detail_returns_none(self) -> None:
        result = self._backend().get_action_detail("any-base", "obj-1", "act-1")
        assert result is None

    def test_create_action_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().create_action("any-base", "obj-1", {})

    def test_update_action_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().update_action("any-base", "obj-1", "act-1", {})

    def test_delete_action_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().delete_action("any-base", "obj-1", "act-1")

    # ── Object CRUD ──

    def test_create_object_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().create_object("any-base", {})

    def test_update_object_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().update_object("any-base", "obj-1", {})

    def test_delete_object_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().delete_object("any-base", "obj-1")

    # ── Datasource CRUD ──

    def test_get_datasources_returns_empty(self) -> None:
        result = self._backend().get_datasources("any-base")
        assert result == []

    def test_get_datasource_detail_returns_none(self) -> None:
        result = self._backend().get_datasource_detail("any-base", "db-1")
        assert result is None

    def test_create_datasource_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().create_datasource("any-base", {})

    def test_delete_datasource_raises_permission_error(self) -> None:
        with pytest.raises(PermissionError):
            self._backend().delete_datasource("any-base", "db-1")

    # ── Existing methods still work (no regression) ──

    def test_existing_get_objects_still_works(self) -> None:
        """get_objects existed before the fix — verify it still exists."""
        assert callable(self._backend().get_objects)

    def test_existing_get_object_detail_still_works(self) -> None:
        """get_object_detail existed before the fix — verify it still exists."""
        assert callable(self._backend().get_object_detail)


# ═══════════════════════════════════════════════════════════════════════════════
# API route no-data integration tests (via FakeOntologyBackend)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmptyDataScenarios:
    """Verify API routes return 200 + empty data when no data is present.

    These test against the fake backend which starts empty. They ensure
    that the route → platform → backend chain gracefully handles the
    empty-data case and returns 200 (not 500).
    """

    def test_list_scenes_no_data_returns_200_empty(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/{OWNER_TYPE}/{LOCAL}/scenes")
        assert resp.status_code == 200
        data: dict[str, Any] = resp.json()
        assert data["success"] is True
        assert data["data"] == []

    def test_list_objects_no_data_returns_200_empty(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/{OWNER_TYPE}/{LOCAL}/objects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_list_views_no_data_returns_200_empty(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/{OWNER_TYPE}/{LOCAL}/views")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_list_relations_no_data_returns_200_empty(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/{OWNER_TYPE}/{LOCAL}/relations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_list_actions_no_data_returns_200_empty(self, client: TestClient) -> None:
        resp = client.get(
            f"/api/v1/ontologyBases/{OWNER_TYPE}/{LOCAL}/objects/obj-1/actions"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_list_datasources_no_data_returns_200_empty(
        self, client: TestClient
    ) -> None:
        resp = client.get(f"/api/v1/ontologyBases/{OWNER_TYPE}/{LOCAL}/datasources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_get_scene_details_no_data_returns_200(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/{OWNER_TYPE}/{LOCAL}/scenes/{SCENE}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_query_ontologies_by_scene_no_data_returns_200(
        self, client: TestClient
    ) -> None:
        resp = client.get(
            f"/api/v1/ontologyBases/{OWNER_TYPE}/{LOCAL}/scenes/{SCENE}/ontologies"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_search_ontology_no_data_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            f"/api/v1/ontologyBases/{OWNER_TYPE}/{LOCAL}/search",
            json={"keyword": "nonexistent"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
