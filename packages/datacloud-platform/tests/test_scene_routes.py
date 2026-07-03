"""Scene CRUD + member management API endpoint tests.

Covers: POST/PUT/DELETE /scenes, POST/DELETE /scenes/{id}/members,
and getSceneDetails filtering behaviour via the test client.
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
    make_action,
    make_ds,
    make_object,
    make_relation,
    make_view,
)

LOCAL = "local-base"

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Reset all backend registries before each test to ensure isolation."""
    from datacloud_platform.backends import registry as _registry

    _registry._BACKEND_DEFAULTS.clear()
    _registry._IMPLEMENTATIONS.clear()
    from datacloud_platform.backends import presets as _presets

    _presets._PRESETS.clear()


@pytest.fixture
def fakes() -> dict[str, Any]:
    """Create fake backend instances."""
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
    """Build a TestClient backed entirely by fake backends."""
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
        OntologyBaseEntry(
            base_id=LOCAL,
            display_name="本地库",
            source_type="LOCAL",
        )
    )

    platform = DatacloudPlatform(_base_registry=registry)
    platform._fakes = (onto_local, onto_remote, know, exec_, stor)

    app = create_app(platform)
    return TestClient(app)


# ── URL helpers ───────────────────────────────────────────────────────────────


def _scenes_url(base_id: str = LOCAL) -> str:
    return f"/api/v1/ontologyBases/{base_id}/scenes"


def _scene_url(scene_id: str, base_id: str = LOCAL) -> str:
    return f"{_scenes_url(base_id)}/{scene_id}"


def _members_url(scene_id: str, base_id: str = LOCAL) -> str:
    return f"{_scene_url(scene_id, base_id)}/members"


# ═══════════════════════════════════════════════════════════════════════════════
# Scene CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestSceneCRUD:
    """Scene create / update / delete endpoints."""

    def test_create_scene(self, client: TestClient) -> None:
        body = {
            "sceneName": "默认场景",
            "sceneCode": "default",
            "sceneDesc": "默认分组",
        }
        resp = client.post(_scenes_url(), json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "created"
        assert data["data"]["scene_name"] == "默认场景"
        assert data["data"]["scene_code"] == "default"

    def test_create_scene_without_code_generates_id(self, client: TestClient) -> None:
        body = {"sceneName": "自动ID场景"}
        resp = client.post(_scenes_url(), json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["scene_code"].startswith("scene_")
        assert len(data["data"]["scene_code"]) > 6

    def test_create_duplicate_scene_returns_400(self, client: TestClient) -> None:
        body = {"sceneName": "重复", "sceneCode": "dup"}
        client.post(_scenes_url(), json=body)
        resp = client.post(_scenes_url(), json=body)
        assert resp.status_code == 400

    def test_create_scene_remote_readonly(
        self, client: TestClient, fakes: dict[str, Any], entity_store: JsonEntityStore
    ) -> None:
        """Remote backend should reject writes."""
        onto = fakes["onto_remote"]
        onto._readonly = True
        # Register a remote base
        registry = OntologyBaseRegistry(entity_store)
        registry.register(
            OntologyBaseEntry(
                base_id="remote", display_name="远程", source_type="REMOTE"
            )
        )
        platform = DatacloudPlatform(_base_registry=registry)
        platform._fakes = (
            onto,
            onto,
            fakes["term"],
            fakes["execution"],
            fakes["storage"],
        )
        app = create_app(platform)
        tc = TestClient(app)

        body = {"sceneName": "远程场景"}
        resp = tc.post("/api/v1/ontologyBases/remote/scenes", json=body)
        assert resp.status_code == 403

    def test_update_scene(self, client: TestClient) -> None:
        # Create first
        client.post(
            _scenes_url(),
            json={"sceneName": "旧名", "sceneCode": "upd"},
        )
        # Update
        resp = client.put(
            _scene_url("upd"),
            json={"sceneName": "新名", "sceneDesc": "新描述"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "updated"
        assert data["data"]["scene_name"] == "新名"
        assert data["data"]["scene_desc"] == "新描述"
        assert data["data"]["scene_code"] == "upd"  # unchanged

    def test_update_nonexistent_scene(self, client: TestClient) -> None:
        resp = client.put(
            _scene_url("no-such"),
            json={"sceneName": "不存在"},
        )
        assert resp.status_code == 404

    def test_delete_scene(self, client: TestClient) -> None:
        client.post(
            _scenes_url(),
            json={"sceneName": "待删", "sceneCode": "del"},
        )
        resp = client.delete(_scene_url("del"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "deleted"

        # Verify it's gone
        resp2 = client.get(_scenes_url())
        codes = [s.get("scene_code") for s in resp2.json()["data"]]
        assert "del" not in codes

    def test_delete_nonexistent_scene_does_not_error(self, client: TestClient) -> None:
        """Delete of non-existent scene is idempotent (no-op)."""
        resp = client.delete(_scene_url("no-such"))
        assert resp.status_code == 200

    def test_list_scenes_after_crud(self, client: TestClient) -> None:
        """Verify scenes appear in list after creation."""
        client.post(
            _scenes_url(),
            json={"sceneName": "A", "sceneCode": "a"},
        )
        client.post(
            _scenes_url(),
            json={"sceneName": "B", "sceneCode": "b"},
        )
        resp = client.get(_scenes_url())
        data = resp.json()
        codes = [s.get("scene_code") for s in data["data"]]
        assert "a" in codes
        assert "b" in codes


# ═══════════════════════════════════════════════════════════════════════════════
# Scene member management
# ═══════════════════════════════════════════════════════════════════════════════


class TestSceneMembers:
    """Scene member add / remove endpoints."""

    SCENE_ID = "members-test"

    @pytest.fixture
    def setup_scene(self, client: TestClient) -> None:
        """Ensure a scene exists before member tests."""
        client.post(
            _scenes_url(),
            json={"sceneName": "成员测试", "sceneCode": self.SCENE_ID},
        )

    def test_add_members(self, client: TestClient, setup_scene: None) -> None:
        resp = client.post(
            _members_url(self.SCENE_ID),
            json={"objectCodes": ["obj1", "obj2"], "viewCodes": ["view1"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "members added"
        assert set(data["data"]["member_object_codes"]) == {"obj1", "obj2"}
        assert "view1" in data["data"]["member_view_codes"]

    def test_add_members_idempotent(
        self, client: TestClient, setup_scene: None
    ) -> None:
        """重复添加不报错，不重复扩容."""
        client.post(
            _members_url(self.SCENE_ID),
            json={"objectCodes": ["obj1"], "viewCodes": []},
        )
        client.post(
            _members_url(self.SCENE_ID),
            json={"objectCodes": ["obj1"], "viewCodes": []},
        )
        # Verify only one entry
        resp = client.get(_scene_url(self.SCENE_ID))
        # The scene dict's member list should have no duplicates
        scene_data = resp.json()["data"]["scene"]
        assert scene_data["member_object_codes"].count("obj1") == 1

    def test_remove_members(self, client: TestClient, setup_scene: None) -> None:
        client.post(
            _members_url(self.SCENE_ID),
            json={"objectCodes": ["obj1", "obj2"], "viewCodes": ["view1"]},
        )
        resp = client.request(
            "DELETE",
            _members_url(self.SCENE_ID),
            json={"objectCodes": ["obj1"], "viewCodes": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "members removed"

        detail = client.get(_scene_url(self.SCENE_ID))
        scene_data = detail.json()["data"]["scene"]
        assert "obj1" not in scene_data["member_object_codes"]
        assert "obj2" in scene_data["member_object_codes"]
        assert "view1" in scene_data["member_view_codes"]  # view untouched

    def test_add_members_nonexistent_scene(self, client: TestClient) -> None:
        resp = client.post(
            _members_url("no-such"),
            json={"objectCodes": ["obj1"], "viewCodes": []},
        )
        assert resp.status_code == 404

    def test_remove_members_nonexistent_scene(self, client: TestClient) -> None:
        resp = client.request(
            "DELETE",
            _members_url("no-such"),
            json={"objectCodes": ["obj1"], "viewCodes": []},
        )
        assert resp.status_code == 404

    def test_add_members_remote_readonly(
        self, client: TestClient, fakes: dict[str, Any], entity_store: JsonEntityStore
    ) -> None:
        """Remote backend rejects member writes."""
        onto = fakes["onto_remote"]
        onto._readonly = True
        registry = OntologyBaseRegistry(entity_store)
        registry.register(
            OntologyBaseEntry(
                base_id="remote2", display_name="远程2", source_type="REMOTE"
            )
        )
        platform = DatacloudPlatform(_base_registry=registry)
        platform._fakes = (
            onto,
            onto,
            fakes["term"],
            fakes["execution"],
            fakes["storage"],
        )
        app = create_app(platform)
        tc = TestClient(app)

        resp = tc.post(
            "/api/v1/ontologyBases/remote2/scenes/x/members",
            json={"objectCodes": ["obj1"], "viewCodes": []},
        )
        assert resp.status_code == 403

    def test_empty_members_request(self, client: TestClient, setup_scene: None) -> None:
        """Empty objectCodes and viewCodes should succeed (no-op)."""
        resp = client.post(
            _members_url(self.SCENE_ID),
            json={"objectCodes": [], "viewCodes": []},
        )
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# getSceneDetails filtering via API
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetSceneDetailsFilteringAPI:
    """getSceneDetails endpoint — 筛选参数行为."""

    SCENE_ID = "filter-test"

    def _setup_data(self, fakes: dict[str, Any]) -> None:
        """Populate the fake backend with objects/views/relations/datasources and a scene."""
        onto = fakes["onto_local"]

        # Full objects
        onto._full_objects["by_cust"] = make_object(
            "by_cust", db_id="ds_1", actions=[make_action("get_cust")]
        )
        onto._full_objects["by_order"] = make_object("by_order", db_id="ds_1")

        # View
        onto._views["__all__"] = [
            make_view("sales_view", object_codes=["by_cust", "by_order"])
        ]

        # Relation
        onto._all_relations_flat.append(
            make_relation("rel_1", source="by_cust", target="by_order")
        )

        # Datasource
        onto._all_dbsources_flat.append(make_ds("ds_1"))

        # Scene
        onto._scenes_dict[self.SCENE_ID] = {
            "scene_id": self.SCENE_ID,
            "scene_name": "筛选测试",
            "scene_code": self.SCENE_ID,
            "scene_desc": None,
            "base_id": LOCAL,
            "member_object_codes": ["by_cust", "by_order"],
            "member_view_codes": ["sales_view"],
        }
        onto._scenes.append(onto._scenes_dict[self.SCENE_ID])

    def test_no_filter_returns_all(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        self._setup_data(fakes)
        resp = client.get(_scene_url(self.SCENE_ID))
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert len(d["objects"]) == 2
        assert len(d["views"]) == 1
        assert len(d["actions"]) == 1
        assert len(d["relations"]) == 1
        assert len(d["dbsources"]["db"]) == 1

    def test_filter_by_view_code(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        self._setup_data(fakes)
        resp = client.get(f"{_scene_url(self.SCENE_ID)}?viewCode=sales_view")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert len(d["views"]) == 1
        assert d["views"][0]["viewCode"] == "sales_view"
        assert len(d["objects"]) == 2

    def test_filter_by_object_code_views_empty(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        self._setup_data(fakes)
        resp = client.get(f"{_scene_url(self.SCENE_ID)}?objectCode=by_cust")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert len(d["views"]) == 0
        assert len(d["objects"]) == 1
        assert d["objects"][0]["objectCode"] == "by_cust"
        assert len(d["actions"]) == 1

    def test_filter_both_union(self, client: TestClient, fakes: dict[str, Any]) -> None:
        self._setup_data(fakes)
        resp = client.get(
            f"{_scene_url(self.SCENE_ID)}?viewCode=sales_view&objectCode=by_order"
        )
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert len(d["views"]) == 1
        assert len(d["objects"]) == 2

    def test_relations_only_both_ends_in_set(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        self._setup_data(fakes)
        resp = client.get(f"{_scene_url(self.SCENE_ID)}?objectCode=by_cust")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert len(d["relations"]) == 0

    def test_dbsources_only_referenced(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        self._setup_data(fakes)
        resp = client.get(f"{_scene_url(self.SCENE_ID)}?objectCode=by_cust")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert len(d["dbsources"]["db"]) == 1

    def test_details_with_csv_params(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        """逗号分隔的 viewCode / objectCode 参数正确解析."""
        self._setup_data(fakes)
        resp = client.get(
            f"{_scene_url(self.SCENE_ID)}?viewCode=sales_view,other&objectCode=by_cust,by_order"
        )
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert len(d["objects"]) == 2  # union of both

    def test_details_empty_params(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        """空 viewCode / objectCode 被视为无参数."""
        self._setup_data(fakes)
        resp = client.get(f"{_scene_url(self.SCENE_ID)}?viewCode=&objectCode=")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert len(d["objects"]) == 2  # all
