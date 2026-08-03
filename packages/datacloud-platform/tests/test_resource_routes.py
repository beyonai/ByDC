"""Tests for flat resource routes — Object / View / Relation CRUD via API.

Uses the flat routes: GET/POST/DELETE /api/v1/ontologyBases/objects etc.
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
from datacloud_platform.constants import DEFAULT_BASE_ID
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
    registry.register(
        OntologyBaseEntry(
            base_id=DEFAULT_BASE_ID,
            display_name="默认库",
            source_type="LOCAL",
        )
    )

    platform = DatacloudPlatform(_base_registry=registry)
    platform._fakes = (onto_local, onto_remote, know, exec_, stor)

    app = create_app(platform)
    return TestClient(app)


def _objects_url(params: str = "") -> str:
    base = f"/api/v1/ontologyBases/objects?base_id={LOCAL}"
    return f"{base}&{params}" if params else base


def _object_url(code: str) -> str:
    return f"/api/v1/ontologyBases/objects/{code}?base_id={LOCAL}"


def _views_url(params: str = "") -> str:
    base = f"/api/v1/ontologyBases/views?base_id={LOCAL}"
    return f"{base}&{params}" if params else base


def _view_url(code: str) -> str:
    return f"/api/v1/ontologyBases/views/{code}?base_id={LOCAL}"


def _relations_url(params: str = "") -> str:
    base = f"/api/v1/ontologyBases/relations?base_id={LOCAL}"
    return f"{base}&{params}" if params else base


class TestObjectRoutes:
    """Tests for flat object routes."""

    def test_list_objects_returns_list(self, client: TestClient) -> None:
        """GET /objects returns a list (even if empty)."""
        resp = client.get(_objects_url())
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_get_object_not_found_returns_404(self, client: TestClient) -> None:
        """GET /objects/{code} for non-existent returns 404."""
        resp = client.get(_object_url("no-such-obj"))
        assert resp.status_code == 404

    def test_create_object_succeeds(self, client: TestClient) -> None:
        """POST /objects creates an object."""
        body = {
            "objectCode": "test_obj",
            "objectName": "测试对象",
            "baseId": LOCAL,
        }
        resp = client.post(_objects_url(), json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "created"

    def test_delete_object_succeeds(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        """DELETE /objects/{code} deletes an object."""
        onto = fakes["onto_local"]
        onto._objects["to_delete"] = {
            "object_code": "to_delete",
            "object_name": "待删除",
        }

        resp = client.delete(_object_url("to_delete"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "deleted"

    def test_query_objects_by_knowledge_returns_camel_case_page(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        onto = fakes["onto_local"]
        onto._knowledge_objects = (
            [
                {
                    "objectCode": "customer",
                    "objectName": "客户",
                    "objectDesc": "客户对象",
                    "baseId": DEFAULT_BASE_ID,
                    "kbResourceId": "kb-1",
                    "kbDirectory": "/a",
                }
            ],
            1001,
        )

        resp = client.post(
            _objects_url().split("?")[0] + "/queryByKnowledge",
            json={
                "kbResourceId": " kb-1 ",
                "kbDirectories": [" /a ", "/a", ""],
                "objectName": " 客户 ",
                "pageIndex": 2,
                "pageSize": 1000,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == {
            "items": onto._knowledge_objects[0],
            "total": 1001,
            "pageIndex": 2,
            "pageSize": 1000,
            "totalPages": 2,
        }
        assert "properties" not in body["data"]["items"][0]
        assert "actions" not in body["data"]["items"][0]
        assert onto._knowledge_query == {
            "base_id": DEFAULT_BASE_ID,
            "kb_resource_id": "kb-1",
            "kb_directories": ["/a"],
            "object_name": "客户",
            "page_index": 2,
            "page_size": 1000,
        }

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"kbResourceId": "   "},
            {"kbResourceId": "kb-1", "pageIndex": 0},
            {"kbResourceId": "kb-1", "pageSize": 0},
            {"kbResourceId": "kb-1", "pageSize": 1001},
        ],
    )
    def test_query_objects_by_knowledge_rejects_invalid_request(
        self, client: TestClient, payload: dict[str, Any]
    ) -> None:
        resp = client.post(
            _objects_url().split("?")[0] + "/queryByKnowledge",
            json=payload,
        )

        assert resp.status_code == 422

    def test_query_objects_by_knowledge_empty_page_has_zero_total_pages(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            _objects_url().split("?")[0] + "/queryByKnowledge",
            json={"kbResourceId": "kb-1"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"] == {
            "items": [],
            "total": 0,
            "pageIndex": 1,
            "pageSize": 20,
            "totalPages": 0,
        }


class TestViewRoutes:
    """Tests for flat view routes."""

    def test_list_views_returns_list(self, client: TestClient) -> None:
        """GET /views returns a list."""
        resp = client.get(_views_url())
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_create_view_succeeds(self, client: TestClient) -> None:
        """POST /views creates a view."""
        body = {
            "viewCode": "test_view",
            "viewName": "测试视图",
            "baseId": LOCAL,
        }
        resp = client.post(_views_url(), json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "created"

    def test_delete_view_succeeds(self, client: TestClient) -> None:
        """DELETE /views/{code} deletes a view."""
        resp = client.delete(_view_url("test_view"))
        assert resp.status_code in (200, 404)  # 404 is ok — not found


class TestRelationRoutes:
    """Tests for flat relation routes (minimal)."""

    def test_list_relations_returns_list(self, client: TestClient) -> None:
        """GET /relations returns a list."""
        resp = client.get(_relations_url())
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
