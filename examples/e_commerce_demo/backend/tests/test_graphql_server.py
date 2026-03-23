"""GraphQL 服务端与 HTTP 端点测试。"""

from pathlib import Path

import pytest


def test_graphql_introspection_via_http() -> None:
    """POST /graphql 可响应 introspection 查询 { __schema { types { name } } }。"""
    from fastapi.testclient import TestClient

    from datacloud_data_service.api.routes import create_app

    # 确保 crm_demo_graphql 存在（tests/ 的 parent 为 datacloud-data）
    graphql_registry = Path(__file__).resolve().parents[2] / "resources" / "ontology" / "crm_demo_graphql" / "objects_registry.json"
    if not graphql_registry.exists():
        pytest.skip("crm_demo_graphql ontology not found")

    app = create_app()
    client = TestClient(app)
    resp = client.post("/graphql", json={"query": "{ __schema { types { name } } }"})
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["data"] is not None
    types = data["data"]["__schema"]["types"]
    assert isinstance(types, list)
    type_names = [t["name"] for t in types]
    assert "Query" in type_names
