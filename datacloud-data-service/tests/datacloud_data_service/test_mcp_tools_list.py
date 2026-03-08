from fastapi.testclient import TestClient


def get_client():
    from datacloud_data_service.api.routes import create_app
    return TestClient(create_app())


def test_tools_list_returns_unified_query_tool() -> None:
    client = get_client()
    resp = client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
        headers={
            "X-Tenant-Id": "t1",
            "X-User-Id": "u1",
            "X-Session-Id": "s1",
            "Authorization": "Bearer tok",
            "X-System-Code": "dc",
        },
    )
    assert resp.status_code == 200
    tools = resp.json()["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "unified_data_query" in names


def test_tools_list_missing_tenant_id_returns_400() -> None:
    client = get_client()
    resp = client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
    )
    assert resp.status_code == 400


def test_tools_call_unknown_tool_returns_error() -> None:
    client = get_client()
    resp = client.post(
        "/api/v1/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "3",
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        },
        headers={"X-Tenant-Id": "t1"},
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["isError"] is True
