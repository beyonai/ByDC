"""Skills API 单元测试：GET /api/v1/skills/package。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from datacloud_data_sdk.ontology.loader import OntologyLoader

HEADERS = {
    "X-Tenant-Id": "t1",
}

REGISTRY = {
    "functions": [],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "销售商机",
            "description": "商机对象",
            "source_type": "DB",
            "source_config": {
                "alias": "test_db",
                "db_type": "SQLITE",
                "jdbc_url": "jdbc:sqlite::memory:",
            },
            "datasource_alias": "test_db",
            "table_name": "sales_bo",
            "fields": [
                {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"},
                {"field_code": "bo_name", "field_name": "商机名称", "field_type": "STRING"},
            ],
            "actions": [],
        }
    ],
    "relations": [],
}

SCENE = {
    "view_id": "test_view",
    "view_name": "测试视图",
    "object_ids": ["sales_bo"],
}


def _create_test_app():
    """创建带 OntologyLoader 的测试 app（最小 app，避免 lifespan 覆盖 loader）。"""
    from fastapi import FastAPI

    from datacloud_data_service.api.skills import router as skills_router
    from datacloud_data_service.tools.virtual_action_injector import inject_virtual_actions

    app = FastAPI()
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.load_scene(SCENE)
    inject_virtual_actions(loader)
    app.state.loader = loader
    app.include_router(skills_router, prefix="/api/v1/skills")
    return app


def test_skills_package_view_id_returns_200_with_tools_and_examples() -> None:
    """GET /api/v1/skills/package?view_id=xxx 返回 200，响应含 tools 数组、examples 字段。"""
    app = _create_test_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        "/api/v1/skills/package",
        params={"view_id": "test_view"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    assert isinstance(data["tools"], list)
    assert len(data["tools"]) >= 1
    # 至少一个 tool 含 examples 字段
    tools_with_examples = [t for t in data["tools"] if "examples" in t]
    assert len(tools_with_examples) >= 1


def test_skills_package_object_ids_returns_200_with_tools() -> None:
    """GET /api/v1/skills/package?object_ids=a,b 返回 200，含 tools。"""
    app = _create_test_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        "/api/v1/skills/package",
        params={"object_ids": "sales_bo"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    assert isinstance(data["tools"], list)
    assert len(data["tools"]) >= 1


def test_skills_package_missing_tenant_returns_400() -> None:
    """缺少 X-Tenant-Id 返回 400。"""
    app = _create_test_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        "/api/v1/skills/package",
        params={"view_id": "test_view"},
    )
    assert resp.status_code == 400


def test_skills_package_missing_params_returns_400() -> None:
    """未传 view_id 且未传 object_ids 返回 400。"""
    app = _create_test_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        "/api/v1/skills/package",
        headers=HEADERS,
    )
    assert resp.status_code == 400


def test_skills_package_respects_x_tool_list_mode() -> None:
    """X-Tool-List-Mode: unified 仅返回 operation；per_object 返回全部+虚拟动作。"""
    app = _create_test_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp_unified = client.get(
        "/api/v1/skills/package",
        params={"object_ids": "sales_bo"},
        headers={**HEADERS, "X-Tool-List-Mode": "unified"},
    )
    resp_per = client.get(
        "/api/v1/skills/package",
        params={"object_ids": "sales_bo"},
        headers={**HEADERS, "X-Tool-List-Mode": "per_object"},
    )
    assert resp_unified.status_code == 200
    assert resp_per.status_code == 200
    tools_unified = resp_unified.json().get("tools", [])
    tools_per = resp_per.json().get("tools", [])
    names_unified = [t["name"] for t in tools_unified]
    names_per = [t["name"] for t in tools_per]
    assert "unified_data_query" in names_unified
    assert "query_sales_bo" not in names_unified
    assert "query_sales_bo" in names_per
