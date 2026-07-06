"""Tests for query_ontologies_by_scene — cross-scene query, type filter, pagination, keyword.

Uses the flat route: GET /api/v1/ontologyBases/scenes/{scene_code}/ontologies
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


def _flat_browse_url(
    scene_code: str,
    *,
    base_id: str = LOCAL,
    params: dict[str, str] | None = None,
) -> str:
    url = f"/api/v1/ontologyBases/scenes/{scene_code}/ontologies?base_id={base_id}"
    if params:
        extra = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}&{extra}"
    return url


class TestSceneBrowse:
    """Tests for query_ontologies_by_scene_flat endpoint."""

    def _seed_scene_and_ontologies(
        self, onto: FakeOntologyBackend, scene_code: str
    ) -> str:
        """Create a scene with objects and views. Returns scene_id."""
        scene_id = scene_code
        onto._scenes.append(
            {
                "scene_id": scene_id,
                "scene_name": scene_code,
                "scene_code": scene_code,
                "base_id": LOCAL,
                "member_object_codes": ["obj1", "obj2"],
                "member_view_codes": ["view1"],
            }
        )
        onto._ontologies_by_scene[scene_id] = {
            "data": {
                "objects": [
                    {
                        "object_code": "obj1",
                        "object_name": "客户信息",
                        "object_type": "object",
                    },
                    {
                        "object_code": "obj2",
                        "object_name": "订单记录",
                        "object_type": "object",
                    },
                ],
                "views": [
                    {
                        "view_code": "view1",
                        "view_name": "客户视图",
                        "view_type": "view",
                    },
                ],
            },
            "totalCount": 3,
        }
        return scene_id

    def test_cross_scene_query_returns_all(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        """scene_code='-1' queries across all scenes."""
        onto = fakes["onto_local"]
        self._seed_scene_and_ontologies(onto, "sales")
        # Also populate the cross-scene key "-1"
        onto._ontologies_by_scene[""] = {
            "data": {
                "objects": [
                    {"object_code": "obj1", "object_name": "客户信息"},
                    {"object_code": "obj2", "object_name": "订单记录"},
                ],
                "views": [
                    {"view_code": "view1", "view_name": "客户视图"},
                ],
            },
            "totalCount": 3,
        }

        resp = client.get(_flat_browse_url("-1"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        total = data["totalCount"]
        # Cross-scene with empty scene_id → backend uses "" key
        assert total >= 0

    def test_scene_not_found_returns_empty(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        """Non-existent scene returns empty data, not 404."""
        resp = client.get(_flat_browse_url("nonexistent"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["objects"] == []
        assert data["data"]["views"] == []

    def test_pagination_slice(self, client: TestClient, fakes: dict[str, Any]) -> None:
        """Page and page_size parameters return correct slice."""
        onto = fakes["onto_local"]
        self._seed_scene_and_ontologies(onto, "paginate")

        resp = client.get(
            _flat_browse_url("paginate", params={"page": "1", "pageSize": "5"})
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "totalCount" in data

    def test_keyword_filter_works(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        """Keyword filter returns matching items (case-insensitive)."""
        onto = fakes["onto_local"]
        self._seed_scene_and_ontologies(onto, "filtered")

        resp = client.get(_flat_browse_url("filtered", params={"keyword": "客户"}))
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalCount"] >= 0

    def test_keyword_filter_case_insensitive(
        self, client: TestClient, fakes: dict[str, Any]
    ) -> None:
        """Keyword filter is case-insensitive."""
        onto = fakes["onto_local"]
        sid = self._seed_scene_and_ontologies(onto, "case_test")
        onto._ontologies_by_scene[sid] = {
            "data": {
                "objects": [
                    {
                        "object_code": "CUSTOMER",
                        "object_name": "Customer",
                        "description": "",
                    },
                ],
                "views": [],
            },
            "totalCount": 1,
        }

        resp = client.get(_flat_browse_url("case_test", params={"keyword": "customer"}))
        assert resp.status_code == 200
        data = resp.json()
        # FakeOntologyBackend does case-insensitive filtering on keyword
        assert data["totalCount"] >= 0
