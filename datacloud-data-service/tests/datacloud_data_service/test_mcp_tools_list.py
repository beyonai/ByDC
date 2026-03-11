from fastapi.testclient import TestClient

from tests.datacloud_data_service.mcp_test_utils import parse_sse_response

# MCP Streamable HTTP 要求 Accept: application/json, text/event-stream
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def get_client():
    from datacloud_data_service.api.routes import create_app

    return TestClient(create_app())


def test_tools_list_returns_unified_query_tool() -> None:
    with get_client() as client:
        resp = client.post(
            "/api/v1/mcp",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
            headers={
                **MCP_HEADERS,
                "X-Tenant-Id": "t1",
                "X-User-Id": "u1",
                "X-Session-Id": "s1",
                "Authorization": "Bearer tok",
                "X-System-Code": "dc",
            },
        )
        assert resp.status_code == 200
        data = parse_sse_response(resp)
        tools = data["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "unified_data_query" in names


def test_mcp_initialize_returns_capabilities() -> None:
    """MCP 客户端需先调用 initialize 完成握手。"""
    with get_client() as client:
        resp = client.post(
            "/api/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            },
            headers={**MCP_HEADERS, "X-Tenant-Id": "t1"},
        )
        assert resp.status_code == 200
        data = parse_sse_response(resp)
        assert "result" in data
        caps = data["result"].get("capabilities", {})
        assert "tools" in caps
        assert "serverInfo" in data["result"]


def test_tools_list_includes_title() -> None:
    """工具定义包含 title 字段供 MCP 客户端显示。"""
    with get_client() as client:
        resp = client.post(
            "/api/v1/mcp",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
            headers={**MCP_HEADERS, "X-Tenant-Id": "t1"},
        )
        assert resp.status_code == 200
        data = parse_sse_response(resp)
        tools = data["result"]["tools"]
        unified = next((t for t in tools if t["name"] == "unified_data_query"), None)
        assert unified is not None
        assert unified.get("title") == "统一数据查询"


def test_tools_list_with_trailing_slash_works() -> None:
    """MCP 端点兼容带尾斜杠的请求地址 /api/v1/mcp/。"""
    with get_client() as client:
        resp = client.post(
            "/api/v1/mcp/",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
            headers={**MCP_HEADERS, "X-Tenant-Id": "t1"},
        )
        assert resp.status_code == 200
        data = parse_sse_response(resp)
        assert "unified_data_query" in [t["name"] for t in data["result"]["tools"]]


def test_tools_list_missing_tenant_id_returns_200() -> None:
    """MCP SDK 不强制校验 X-Tenant-Id，无 header 时仍返回 200。"""
    with get_client() as client:
        resp = client.post(
            "/api/v1/mcp",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
            headers=MCP_HEADERS,
        )
        assert resp.status_code == 200


def test_tools_call_unknown_tool_returns_error() -> None:
    with get_client() as client:
        resp = client.post(
            "/api/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "3",
                "method": "tools/call",
                "params": {"name": "nonexistent_tool", "arguments": {}},
            },
            headers={**MCP_HEADERS, "X-Tenant-Id": "t1"},
        )
        assert resp.status_code == 200
        data = parse_sse_response(resp)
        result = data["result"]
        content = result.get("content", [])
        text = content[0].get("text", "") if content else ""
        assert result.get("isError") is True or "Unknown tool" in text or "error" in text.lower()
