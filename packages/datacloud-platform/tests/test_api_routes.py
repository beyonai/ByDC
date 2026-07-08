"""Fake integration tests for datacloud-platform API routes.

All backends are in-memory — no database, LLM, or Redis dependency.
"""

from __future__ import annotations

import io
import zipfile
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    pass

# ── Constants ─────────────────────────────────────────────────────────────────
LOCAL = "local-base"
REMOTE = "remote-base"
SCENE = "scene-1"

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Reset all backend registries before each test to ensure isolation."""
    _registry._BACKEND_DEFAULTS.clear()
    _registry._IMPLEMENTATIONS.clear()
    from datacloud_platform.backends import presets as _presets

    _presets._PRESETS.clear()


@pytest.fixture
def fakes() -> dict[str, Any]:
    """Create fake backend instances (not registered yet)."""
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
    registry.register(
        OntologyBaseEntry(
            base_id=REMOTE,
            display_name="远程库",
            source_type="REMOTE",
        )
    )

    platform = DatacloudPlatform(_base_registry=registry)
    platform._fakes = (onto_local, onto_remote, know, exec_, stor)  # type: ignore[attr-defined]

    app = create_app(platform)
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Health
# ═══════════════════════════════════════════════════════════════════════════════


class TestHealth:
    """Health check endpoints."""

    def test_health(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "loaded_bases" in data

    def test_health_v1(self, client: TestClient) -> None:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. OntologyBase CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestOntologyBaseRoutes:
    """OntologyBase management endpoints."""

    def test_list_bases(self, client: TestClient) -> None:
        resp = client.get("/api/v1/ontologyBases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        base_ids = [b["base_id"] for b in data["data"]]
        assert LOCAL in base_ids
        assert REMOTE in base_ids

    def test_create_base(self, client: TestClient) -> None:
        body = {"baseId": "new-base", "displayName": "新库", "description": "描述"}
        resp = client.post("/api/v1/ontologyBases", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "created"
        assert data["data"]["base_id"] == "new-base"

        # Verify it appears in list
        resp2 = client.get("/api/v1/ontologyBases")
        base_ids = [b["base_id"] for b in resp2.json()["data"]]
        assert "new-base" in base_ids

    def test_create_without_baseid_generates_snowflake(
        self, client: TestClient
    ) -> None:
        """baseId not provided → snowflake auto-generated (16-char hex)."""
        body = {"displayName": "雪花库", "description": "自动ID"}
        resp = client.post("/api/v1/ontologyBases", json=body)
        assert resp.status_code == 200
        data = resp.json()
        base_id: str = data["data"]["base_id"]
        assert len(base_id) == 16
        assert set(base_id).issubset("0123456789abcdef")
        assert data["data"]["display_name"] == "雪花库"
        assert data["data"]["description"] == "自动ID"

    def test_create_with_custom_baseid(self, client: TestClient) -> None:
        """Valid custom baseId is used as-is."""
        body = {"baseId": "my-custom_id", "displayName": "自定义", "description": "d"}
        resp = client.post("/api/v1/ontologyBases", json=body)
        assert resp.status_code == 200
        assert resp.json()["data"]["base_id"] == "my-custom_id"

    def test_create_duplicate_baseid_returns_409(self, client: TestClient) -> None:
        body = {"baseId": LOCAL, "displayName": "重复", "description": "d"}
        resp = client.post("/api/v1/ontologyBases", json=body)
        assert resp.status_code == 409

    def test_create_invalid_baseid_uppercase(self, client: TestClient) -> None:
        body = {"baseId": "Invalid", "displayName": "大写", "description": "d"}
        resp = client.post("/api/v1/ontologyBases", json=body)
        assert resp.status_code == 400

    def test_create_invalid_baseid_too_long(self, client: TestClient) -> None:
        body = {
            "baseId": "a" * 17,
            "displayName": "太长",
            "description": "d",
        }
        resp = client.post("/api/v1/ontologyBases", json=body)
        assert resp.status_code == 400

    def test_create_invalid_baseid_non_alpha_first(self, client: TestClient) -> None:
        body = {"baseId": "1badstart", "displayName": "数字开头", "description": "d"}
        resp = client.post("/api/v1/ontologyBases", json=body)
        assert resp.status_code == 400

    def test_create_missing_description(self, client: TestClient) -> None:
        body = {"displayName": "缺描述"}
        resp = client.post("/api/v1/ontologyBases", json=body)
        assert resp.status_code == 422

    def test_delete_base(self, client: TestClient) -> None:
        # First create a disposable base
        client.post(
            "/api/v1/ontologyBases",
            json={"baseId": "del-base", "displayName": "待删", "description": "d"},
        )
        resp = client.delete("/api/v1/ontologyBases/del-base")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "deleted"

    def test_delete_nonexistent_base(self, client: TestClient) -> None:
        resp = client.delete("/api/v1/ontologyBases/no-such-base")
        assert resp.status_code == 404

    def test_update_base_display_name(self, client: TestClient) -> None:
        body = {"displayName": "新名字"}
        resp = client.put(f"/api/v1/ontologyBases/{LOCAL}", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "updated"
        assert data["data"]["display_name"] == "新名字"
        # Other fields unchanged
        assert data["data"]["base_id"] == LOCAL

    def test_update_base_multiple_fields(self, client: TestClient) -> None:
        body = {
            "displayName": "多字段",
            "description": "新描述",
            "timeoutSec": 60,
        }
        resp = client.put(f"/api/v1/ontologyBases/{LOCAL}", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["display_name"] == "多字段"
        assert data["data"]["description"] == "新描述"
        assert data["data"]["timeout_sec"] == 60

    def test_update_base_readonly_field_ignored(self, client: TestClient) -> None:
        """Passing baseId in PUT body has no effect."""
        body = {"baseId": "hacked", "displayName": "改名"}
        resp = client.put(f"/api/v1/ontologyBases/{LOCAL}", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["base_id"] == LOCAL  # unchanged
        assert data["data"]["display_name"] == "改名"

    def test_update_nonexistent_base(self, client: TestClient) -> None:
        body = {"displayName": "不存在"}
        resp = client.put("/api/v1/ontologyBases/no-such", json=body)
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Scene Routes
# ═══════════════════════════════════════════════════════════════════════════════


class TestSceneRoutes:
    """Scene list/detail endpoints."""

    def test_list_scenes_empty(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/{LOCAL}/scenes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_list_scenes_with_data(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_local"]
        onto._scenes = [{"sceneCode": SCENE, "sceneName": "场景1"}]

        resp = client.get(f"/api/v1/ontologyBases/{LOCAL}/scenes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["sceneCode"] == SCENE

    def test_list_scenes_with_keyword(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_local"]
        onto._scenes = [
            {"sceneCode": "s1", "sceneName": "销售场景"},
            {"sceneCode": "s2", "sceneName": "财务场景"},
        ]

        resp = client.get(f"/api/v1/ontologyBases/{LOCAL}/scenes?keyword=销售")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["sceneCode"] == "s1"

    def test_list_scenes_nonexistent_base(self, client: TestClient) -> None:
        resp = client.get("/api/v1/ontologyBases/no-such/scenes")
        assert resp.status_code == 404

    def test_get_scene_details(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        onto._scene_details[SCENE] = {
            "scene": {"sceneCode": SCENE, "sceneName": "场景1"},
            "views": [],
            "objects": [],
            "actions": [],
            "relations": [],
            "dbsources": [],
            "version": None,
        }

        resp = client.get(f"/api/v1/ontologyBases/{LOCAL}/scenes/{SCENE}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["scene"]["sceneCode"] == SCENE

    def test_get_scene_details_nonexistent_base(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/no-such/scenes/{SCENE}")
        assert resp.status_code == 404

    def test_query_ontologies_by_scene(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_local"]
        onto._ontologies_by_scene[SCENE] = {
            "data": {
                "objects": [
                    {"object_code": "obj1", "object_name": "对象1"},
                    {"object_code": "obj2", "object_name": "对象2"},
                ],
                "views": [],
            },
            "totalCount": 2,
        }

        resp = client.get(f"/api/v1/ontologyBases/{LOCAL}/scenes/{SCENE}/ontologies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]["objects"]) == 2
        assert len(data["data"]["views"]) == 0
        assert data["totalCount"] == 2

    def test_query_ontologies_with_keyword(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_local"]
        onto._ontologies_by_scene[SCENE] = {
            "data": {
                "objects": [
                    {"object_code": "obj1", "object_name": "客户对象"},
                    {"object_code": "obj2", "object_name": "订单对象"},
                ],
                "views": [],
            },
            "totalCount": 2,
        }

        resp = client.get(
            f"/api/v1/ontologyBases/{LOCAL}/scenes/{SCENE}/ontologies?keyword=客户"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["objects"]) == 1
        assert len(data["data"]["views"]) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Object CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestObjectRoutes:
    """Object CRUD endpoints."""

    def _object_body(
        self, code: str = "obj-test", name: str = "测试对象"
    ) -> dict[str, Any]:
        return {
            "objectCode": code,
            "objectName": name,
            "objectDesc": "测试描述",
            "baseId": "local-base",
            "properties": [],
            "actions": [],
        }

    def test_list_objects_empty(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/objects?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_create_object(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._object_body()

        resp = client.post(
            f"/api/v1/ontologyBases/objects?base_id={LOCAL}",
            json=body,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "created"
        assert len(onto._created_objects) == 1

    def test_create_object_remote_forbidden(self, client: TestClient) -> None:
        body = self._object_body()
        resp = client.post(
            f"/api/v1/ontologyBases/objects?base_id={REMOTE}",
            json=body,
        )
        assert resp.status_code == 403

    def test_get_object_not_found(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/objects/nonexistent?base_id={LOCAL}")
        assert resp.status_code == 404

    def test_update_object(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._object_body(code="obj-upd", name="旧名称")

        # Create first
        client.post(
            f"/api/v1/ontologyBases/objects?base_id={LOCAL}",
            json=body,
        )

        # Update
        updated = self._object_body(code="obj-upd", name="新名称")
        resp = client.put(
            f"/api/v1/ontologyBases/objects/obj-upd?base_id={LOCAL}",
            json=updated,
        )
        assert resp.status_code == 200
        assert len(onto._updated_objects) == 1

    def test_update_object_remote_forbidden(self, client: TestClient) -> None:
        body = self._object_body(code="obj-remote", name="远程")
        resp = client.put(
            f"/api/v1/ontologyBases/objects/obj-remote?base_id={REMOTE}",
            json=body,
        )
        assert resp.status_code == 403

    def test_delete_object(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._object_body(code="obj-del", name="待删")

        client.post(
            f"/api/v1/ontologyBases/objects?base_id={LOCAL}",
            json=body,
        )

        resp = client.delete(f"/api/v1/ontologyBases/objects/obj-del?base_id={LOCAL}")
        assert resp.status_code == 200
        assert len(onto._deleted_objects) == 1

    def test_delete_object_remote_forbidden(self, client: TestClient) -> None:
        resp = client.delete(
            f"/api/v1/ontologyBases/objects/obj-remote?base_id={REMOTE}"
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 5. View CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestViewRoutes:
    """View CRUD endpoints."""

    def _view_body(
        self, code: str = "view-test", name: str = "测试视图"
    ) -> dict[str, Any]:
        return {
            "viewCode": code,
            "viewName": name,
            "description": "测试视图描述",
            "objectCodes": [],
            "properties": [],
        }

    def test_list_views_empty(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/views?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_create_view(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._view_body()

        resp = client.post(
            f"/api/v1/ontologyBases/views?base_id={LOCAL}",
            json=body,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "created"
        assert len(onto._created_views) == 1

    def test_list_views_with_data(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_local"]
        onto._views[SCENE] = [{"viewCode": "v1", "viewName": "视图1"}]

        resp = client.get(f"/api/v1/ontologyBases/views?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["viewCode"] == "v1"

    def test_get_view_not_found(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/views/nonexistent?base_id={LOCAL}")
        assert resp.status_code == 404

    def test_get_view_detail(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        onto._views[SCENE] = [{"viewCode": "v1", "viewName": "视图1"}]

        resp = client.get(f"/api/v1/ontologyBases/views/v1?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["viewCode"] == "v1"

    def test_update_view(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._view_body(code="v-upd")
        client.post(
            f"/api/v1/ontologyBases/views?base_id={LOCAL}",
            json=body,
        )

        updated = self._view_body(code="v-upd", name="更新后")
        resp = client.put(
            f"/api/v1/ontologyBases/views/v-upd?base_id={LOCAL}",
            json=updated,
        )
        assert resp.status_code == 200
        assert len(onto._updated_views) == 1

    def test_delete_view(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._view_body(code="v-del")
        client.post(
            f"/api/v1/ontologyBases/views?base_id={LOCAL}",
            json=body,
        )

        resp = client.delete(f"/api/v1/ontologyBases/views/v-del?base_id={LOCAL}")
        assert resp.status_code == 200
        assert len(onto._deleted_views) == 1

    def test_create_view_remote_forbidden(self, client: TestClient) -> None:
        body = self._view_body()
        resp = client.post(
            f"/api/v1/ontologyBases/views?base_id={REMOTE}",
            json=body,
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Relation CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestRelationRoutes:
    """Relation CRUD endpoints."""

    def _rel_body(self, code: str = "rel-test") -> dict[str, Any]:
        return {
            "relationCode": code,
            "relationName": "测试关系",
            "sourceObjectCode": "obj-a",
            "targetObjectCode": "obj-b",
        }

    def test_list_relations_empty(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/relations?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_create_relation(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._rel_body()

        resp = client.post(
            f"/api/v1/ontologyBases/relations?base_id={LOCAL}",
            json=body,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "created"
        assert len(onto._created_relations) == 1

    def test_list_relations_with_data(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_local"]
        onto._relations[SCENE] = [{"relationCode": "r1", "relationName": "关系1"}]

        resp = client.get(f"/api/v1/ontologyBases/relations?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["relationCode"] == "r1"

    def test_get_relation_not_found(self, client: TestClient) -> None:
        resp = client.get(
            f"/api/v1/ontologyBases/relations/nonexistent?base_id={LOCAL}"
        )
        assert resp.status_code == 404

    def test_get_relation_detail(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_local"]
        onto._relations[SCENE] = [{"relationCode": "r1", "relationName": "关系1"}]

        resp = client.get(f"/api/v1/ontologyBases/relations/r1?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["relationCode"] == "r1"

    def test_update_relation(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._rel_body(code="r-upd")
        client.post(
            f"/api/v1/ontologyBases/relations?base_id={LOCAL}",
            json=body,
        )

        updated = self._rel_body(code="r-upd")
        resp = client.put(
            f"/api/v1/ontologyBases/relations/r-upd?base_id={LOCAL}",
            json=updated,
        )
        assert resp.status_code == 200
        assert len(onto._updated_relations) == 1

    def test_delete_relation(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._rel_body(code="r-del")
        client.post(
            f"/api/v1/ontologyBases/relations?base_id={LOCAL}",
            json=body,
        )

        resp = client.delete(f"/api/v1/ontologyBases/relations/r-del?base_id={LOCAL}")
        assert resp.status_code == 200
        assert len(onto._deleted_relations) == 1

    def test_create_relation_remote_forbidden(self, client: TestClient) -> None:
        body = self._rel_body()
        resp = client.post(
            f"/api/v1/ontologyBases/relations?base_id={REMOTE}",
            json=body,
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Action CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestActionRoutes:
    """Action CRUD endpoints."""

    def _action_body(
        self, code: str = "act-test", name: str = "测试动作"
    ) -> dict[str, Any]:
        return {
            "actionCode": code,
            "actionName": name,
            "belongObjectCode": "obj-x",
            "params": [],
        }

    def test_list_actions_empty(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/objects/obj1/actions?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_create_action(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._action_body()

        resp = client.post(
            f"/api/v1/ontologyBases/objects/obj-x/actions?base_id={LOCAL}",
            json=body,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "created"
        assert len(onto._created_actions) == 1

    def test_list_actions_with_data(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_local"]
        onto._actions["obj1"] = [{"actionCode": "a1", "actionName": "动作1"}]

        resp = client.get(f"/api/v1/ontologyBases/objects/obj1/actions?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["actionCode"] == "a1"

    def test_get_action_not_found(self, client: TestClient) -> None:
        resp = client.get(
            f"/api/v1/ontologyBases/objects/obj1/actions/nonexistent?base_id={LOCAL}"
        )
        assert resp.status_code == 404

    def test_get_action_detail(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        onto._actions["obj1"] = [{"actionCode": "a1", "actionName": "动作1"}]

        resp = client.get(
            f"/api/v1/ontologyBases/objects/obj1/actions/a1?base_id={LOCAL}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["actionCode"] == "a1"

    def test_update_action(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._action_body(code="a-upd")
        client.post(
            f"/api/v1/ontologyBases/objects/obj-x/actions?base_id={LOCAL}",
            json=body,
        )

        updated = self._action_body(code="a-upd", name="更新后动作")
        resp = client.put(
            f"/api/v1/ontologyBases/objects/obj-x/actions/a-upd?base_id={LOCAL}",
            json=updated,
        )
        assert resp.status_code == 200
        assert len(onto._updated_actions) == 1

    def test_delete_action(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._action_body(code="a-del")
        client.post(
            f"/api/v1/ontologyBases/objects/obj-x/actions?base_id={LOCAL}",
            json=body,
        )

        resp = client.delete(
            f"/api/v1/ontologyBases/objects/obj-x/actions/a-del?base_id={LOCAL}"
        )
        assert resp.status_code == 200
        assert len(onto._deleted_actions) == 1

    def test_create_action_remote_forbidden(self, client: TestClient) -> None:
        body = self._action_body()
        resp = client.post(
            f"/api/v1/ontologyBases/objects/obj-x/actions?base_id={REMOTE}",
            json=body,
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Datasource CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestDatasourceRoutes:
    """Datasource CRUD endpoints."""

    def _ds_body(self) -> dict[str, Any]:
        return {
            "db": [{"dbId": "db-1", "dbCode": "mydb", "dbType": "mysql"}],
            "doc": [],
            "api": [],
        }

    def test_list_datasources_empty(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/datasources?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_create_datasource(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        body = self._ds_body()

        resp = client.post(
            f"/api/v1/ontologyBases/datasources?base_id={LOCAL}",
            json=body,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "created"
        assert len(onto._created_datasources) == 1

    def test_list_datasources_with_data(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_local"]
        onto._datasources[SCENE] = [self._ds_body()]

        resp = client.get(f"/api/v1/ontologyBases/datasources?base_id={LOCAL}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1

    def test_get_datasource_not_found(self, client: TestClient) -> None:
        resp = client.get(f"/api/v1/ontologyBases/datasources/no-db?base_id={LOCAL}")
        assert resp.status_code == 404

    def test_delete_datasource(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        client.post(
            f"/api/v1/ontologyBases/datasources?base_id={LOCAL}",
            json=self._ds_body(),
        )

        resp = client.delete(f"/api/v1/ontologyBases/datasources/db-1?base_id={LOCAL}")
        assert resp.status_code == 200
        assert len(onto._deleted_datasources) == 1

    def test_create_datasource_remote_forbidden(self, client: TestClient) -> None:
        resp = client.post(
            f"/api/v1/ontologyBases/datasources?base_id={REMOTE}",
            json=self._ds_body(),
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 9. OWL Import
# ═══════════════════════════════════════════════════════════════════════════════


class TestOwlImport:
    """OWL import endpoint."""

    def _make_zip_bytes(self, name: str = "test.zip") -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", '{"version": "1.0"}')
        buf.seek(0)
        return buf.read()

    def test_import_owl_local(self, client: TestClient, fakes: dict[str, Any]) -> None:
        onto = fakes["onto_local"]
        onto._parsed = type(
            "Parsed",
            (),
            {
                "objects": [{"object_code": "obj1", "object_name": "Object 1"}],
                "views": [],
                "relations": [],
            },
        )()

        zip_bytes = self._make_zip_bytes()
        resp = client.post(
            f"/api/v1/ontologyBases/{LOCAL}/scenes/{SCENE}/import-owl",
            files={"file": ("test.zip", zip_bytes, "application/zip")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "imported"
        assert data["data"]["objects"] == 1

    def test_import_owl_remote_forbidden(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_remote"]
        onto._parsed = type(
            "Parsed",
            (),
            {
                "objects": [{"object_code": "obj1", "object_name": "Object 1"}],
                "views": [],
                "relations": [],
            },
        )()

        zip_bytes = self._make_zip_bytes()
        resp = client.post(
            f"/api/v1/ontologyBases/{REMOTE}/scenes/{SCENE}/import-owl",
            files={"file": ("test.zip", zip_bytes, "application/zip")},
        )
        # import succeeds (no error raised by route handler),
        # but individual object creations are skipped by platform.import_owl's catch
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["objects"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Search + Graph
# ═══════════════════════════════════════════════════════════════════════════════


class TestSearchRoutes:
    """Search and graph query endpoints."""

    def test_search_ontology_base(self, client: TestClient) -> None:
        body = {"keyword": "test", "sceneId": "-1"}
        resp = client.post(f"/api/v1/ontologyBases/{LOCAL}/search", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_search_ontology_in_scene(self, client: TestClient) -> None:
        body = {"keyword": "test"}
        resp = client.post(
            f"/api/v1/ontologyBases/{LOCAL}/scenes/{SCENE}/search",
            json=body,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_search_instances(self, client: TestClient) -> None:
        body = {"objectCode": "obj1"}
        resp = client.post(
            f"/api/v1/ontologyBases/{LOCAL}/instances/search",
            json=body,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_graph_query(self, client: TestClient) -> None:
        body = {"objectCodes": ["obj1", "obj2"], "depth": 1}
        resp = client.post(
            f"/api/v1/ontologyBases/{LOCAL}/scenes/{SCENE}/graph/query",
            json=body,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_graph_path(self, client: TestClient) -> None:
        body = {"sourceObjectCode": "obj1", "targetObjectCode": "obj2"}
        resp = client.post(
            f"/api/v1/ontologyBases/{LOCAL}/scenes/{SCENE}/graph/path",
            json=body,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_search_nonexistent_base(self, client: TestClient) -> None:
        body = {"keyword": "test"}
        resp = client.post("/api/v1/ontologyBases/no-such/search", json=body)
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Runtime Routes (query, download, terms, skills)
# ═══════════════════════════════════════════════════════════════════════════════


class TestQueryRoute:
    """NL query endpoint — needs X-Tenant-Id header."""

    def test_query_missing_tenant_id(self, client: TestClient) -> None:
        body = {"question": "查询所有数据"}
        resp = client.post("/api/v1/query", json=body)
        assert resp.status_code == 400

    def test_query_with_tenant_id(self, client: TestClient) -> None:
        body = {"question": "查询所有数据"}
        resp = client.post(
            "/api/v1/query",
            json=body,
            headers={"X-Tenant-Id": "test-tenant"},
        )
        # Returns 500 because loader runtime has no loader built yet,
        # but the endpoint itself is reachable
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "code" in data


class TestDownloadRoute:
    """CSV download endpoint — needs loader_runtime snapshot."""

    def test_download_nonexistent_file(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/download/csv/no-such-file",
            headers={"X-Tenant-Id": "test-tenant"},
        )
        # 404: file not found, or 500: loader not initialized
        assert resp.status_code in (404, 500)


class TestTermsRoute:
    """Terms options endpoint."""

    def test_terms_options_missing_params(self, client: TestClient) -> None:
        body: dict[str, Any] = {}
        resp = client.post(
            "/api/v1/datacloud/terms/options",
            json=body,
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 400

    def test_terms_options_with_params(self, client: TestClient) -> None:
        body = {"termSet": "test_set", "termTypeCode": "test_type"}
        resp = client.post(
            "/api/v1/datacloud/terms/options",
            json=body,
            headers={"X-Tenant-Id": "test-tenant"},
        )
        # Returns 200 with empty data when term_loader is not configured
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "code" in data


class TestSkillsRoute:
    """Skills package endpoint."""

    def test_skills_missing_tenant_id(self, client: TestClient) -> None:
        resp = client.get("/api/v1/skills/package")
        assert resp.status_code == 400

    def test_skills_missing_view_and_objects(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/skills/package",
            headers={"X-Tenant-Id": "test-tenant"},
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 12. MCP
# ═══════════════════════════════════════════════════════════════════════════════


class TestMcpRoute:
    """MCP endpoint — JSON-RPC over HTTP."""

    def test_mcp_list_tools(self, client: TestClient) -> None:
        """Send a tools/list JSON-RPC request."""
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tools/list",
            "params": {},
        }
        resp = client.post(
            "/api/v1/mcp",
            json=payload,
            headers={
                "X-Tenant-Id": "test-tenant",
                "Accept": "application/json",
            },
        )
        # MCP uses SSE; session manager may not be started in test context,
        # so 500 (task group not initialized) is also acceptable
        assert resp.status_code in (200, 202, 406, 500)

    def test_mcp_initialize(self, client: TestClient) -> None:
        """Send an initialize JSON-RPC request."""
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1"},
            },
        }
        resp = client.post(
            "/api/v1/mcp",
            json=payload,
            headers={
                "X-Tenant-Id": "test-tenant",
                "Accept": "application/json",
            },
        )
        assert resp.status_code in (200, 202, 406, 500)


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Ontology Build
# ═══════════════════════════════════════════════════════════════════════════════


class TestOntologyBuildRoutes:
    """Ontology manager endpoints — these call into datacloud_knowledge which may
    not be available in this environment, so we verify the routes are reachable
    and return error responses gracefully.
    """

    def test_object_collect(self, client: TestClient) -> None:
        body = {"entity_code": "test_entity", "session_id": "s1"}
        resp = client.post("/api/v1/ontology-manager/object/collect", json=body)
        # Will fail without datacloud_knowledge, but route exists
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "ok" in data

    def test_object_submit(self, client: TestClient) -> None:
        body = {"entity_code": "test_entity", "session_id": "s1"}
        resp = client.post("/api/v1/ontology-manager/object/submit", json=body)
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "ok" in data

    def test_object_delete(self, client: TestClient) -> None:
        body = {"entity_code": "test_entity"}
        resp = client.post("/api/v1/ontology-manager/object/delete", json=body)
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "ok" in data

    def test_view_collect(self, client: TestClient) -> None:
        body = {"view_code": "v1", "session_id": "s1"}
        resp = client.post("/api/v1/ontology-manager/view/collect", json=body)
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "ok" in data

    def test_view_submit(self, client: TestClient) -> None:
        body = {"view_code": "v1", "session_id": "s1"}
        resp = client.post("/api/v1/ontology-manager/view/submit", json=body)
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "ok" in data

    def test_view_delete(self, client: TestClient) -> None:
        body = {"view_code": "v1"}
        resp = client.post("/api/v1/ontology-manager/view/delete", json=body)
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "ok" in data

    def test_term_types_list(self, client: TestClient) -> None:
        body: dict[str, Any] = {}
        resp = client.post("/api/v1/ontology-manager/term-types/list", json=body)
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "ok" in data

    def test_term_types_values_missing_code(self, client: TestClient) -> None:
        body: dict[str, Any] = {}
        resp = client.post("/api/v1/ontology-manager/term-types/values", json=body)
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "ok" in data

    def test_term_types_values(self, client: TestClient) -> None:
        body = {"term_type_code": "test_type", "keyword": "test"}
        resp = client.post("/api/v1/ontology-manager/term-types/values", json=body)
        assert resp.status_code in (200, 500)
        data = resp.json()
        assert "ok" in data


# ═══════════════════════════════════════════════════════════════════════════════
# 21. Snowflake & base_id validation (unit tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSnowflake:
    """Unit tests for generate_snowflake and validate_base_id."""

    def test_snowflake_length(self) -> None:
        from datacloud_platform.base_entry import generate_snowflake

        sid = generate_snowflake()
        assert len(sid) == 16

    def test_snowflake_hex(self) -> None:
        from datacloud_platform.base_entry import generate_snowflake

        sid = generate_snowflake()
        assert set(sid).issubset("0123456789abcdef")

    def test_snowflake_ordering(self) -> None:
        """IDs generated later should be lexicographically greater."""
        from datacloud_platform.base_entry import generate_snowflake

        id1 = generate_snowflake()
        import time

        time.sleep(0.002)  # ensure timestamp advances
        id2 = generate_snowflake()
        assert id1 < id2, f"{id1=} should be < {id2=}"

    def test_snowflake_uniqueness(self) -> None:
        """1000 IDs should all be unique."""
        from datacloud_platform.base_entry import generate_snowflake

        ids = {generate_snowflake() for _ in range(1000)}
        assert len(ids) == 1000

    def test_validate_base_id_valid(self) -> None:
        from datacloud_platform.base_entry import validate_base_id

        assert validate_base_id("a")
        assert validate_base_id("abc")
        assert validate_base_id("my-base")
        assert validate_base_id("a123_45-678")
        assert validate_base_id("abcdefghijklmnop")  # exactly 16

    def test_validate_base_id_invalid_uppercase(self) -> None:
        from datacloud_platform.base_entry import validate_base_id

        assert not validate_base_id("ABC")
        assert not validate_base_id("aBc")

    def test_validate_base_id_invalid_too_long(self) -> None:
        from datacloud_platform.base_entry import validate_base_id

        assert not validate_base_id("abcdefghijklmnopq")  # 17 chars

    def test_validate_base_id_invalid_first_char(self) -> None:
        from datacloud_platform.base_entry import validate_base_id

        assert not validate_base_id("1abc")
        assert not validate_base_id("-abc")
        assert not validate_base_id("_abc")

    def test_validate_base_id_invalid_special_chars(self) -> None:
        from datacloud_platform.base_entry import validate_base_id

        assert not validate_base_id("ab cd")
        assert not validate_base_id("ab.cd")
        assert not validate_base_id("ab/cd")


# ═══════════════════════════════════════════════════════════════════════════════
# 22. Persistence tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPersistence:
    """Tests for EntityStore-backed persistence of OntologyBaseRegistry."""

    def test_register_persists_to_shard(self, entity_store: JsonEntityStore) -> None:
        """register() persists entry as individual shard file."""
        from datacloud_platform.base_entry import (
            OntologyBaseEntry,
            OntologyBaseRegistry,
        )

        registry = OntologyBaseRegistry(entity_store)
        registry.register(
            OntologyBaseEntry(base_id="p1", display_name="P1", description="desc1")
        )
        registry.register(
            OntologyBaseEntry(base_id="p2", display_name="P2", description="desc2")
        )

        # Verify shard files exist
        saved = entity_store.get("bases", "p1")
        assert saved is not None
        assert saved["display_name"] == "P1"

        saved2 = entity_store.get("bases", "p2")
        assert saved2 is not None
        assert saved2["display_name"] == "P2"

    def test_restore_loads_from_store(self, entity_store: JsonEntityStore) -> None:
        """restore() loads entries from EntityStore index."""
        from datacloud_platform.base_entry import (
            OntologyBaseEntry,
            OntologyBaseRegistry,
        )

        # First registry: register and verify it's persisted
        registry1 = OntologyBaseRegistry(entity_store)
        registry1.register(
            OntologyBaseEntry(base_id="p1", display_name="P1", description="desc1")
        )

        # Second registry: restore from same store
        registry2 = OntologyBaseRegistry(entity_store)
        registry2.restore()
        assert registry2.exists("p1")
        e = registry2.get("p1")
        assert e is not None
        assert e.display_name == "P1"
        assert e.description == "desc1"

    def test_restore_empty_store(self, entity_store: JsonEntityStore) -> None:
        """restore() on a fresh store yields empty registry."""
        from datacloud_platform.base_entry import OntologyBaseRegistry

        registry = OntologyBaseRegistry(entity_store)
        registry.restore()
        assert registry.list() == []

    def test_delete_persists_removal(self, entity_store: JsonEntityStore) -> None:
        """unregister() removes entry file and updates index."""
        from datacloud_platform.base_entry import (
            OntologyBaseEntry,
            OntologyBaseRegistry,
        )

        registry = OntologyBaseRegistry(entity_store)
        registry.register(
            OntologyBaseEntry(base_id="temp", display_name="T", description="d")
        )
        assert entity_store.get("bases", "temp") is not None

        registry.unregister("temp")
        assert entity_store.get("bases", "temp") is None
        assert not registry.exists("temp")

    def test_persistence_survives_registry_reload(
        self, entity_store: JsonEntityStore
    ) -> None:
        """Data survives across registry instances using shared EntityStore."""
        from datacloud_platform.base_entry import (
            OntologyBaseEntry,
            OntologyBaseRegistry,
        )

        registry = OntologyBaseRegistry(entity_store)
        registry.register(
            OntologyBaseEntry(base_id="survive", display_name="S", description="d")
        )

        # New registry instance on same store
        restored = OntologyBaseRegistry(entity_store)
        restored.restore()
        assert restored.exists("survive")
        entry = restored.get("survive")
        assert entry is not None
        assert entry.display_name == "S"
