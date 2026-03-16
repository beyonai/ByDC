"""MCP tools/call 操作类工具测试。"""

from fastapi.testclient import TestClient

from tests.datacloud_data_service.mcp_test_utils import parse_sse_response
from datacloud_data.ontology.loader import OntologyLoader

# MCP Streamable HTTP 要求 Accept: application/json, text/event-stream
HEADERS = {
    "Accept": "application/json, text/event-stream",
    "X-Tenant-Id": "t1",
    "X-User-Id": "u1",
    "Authorization": "Bearer tok",
}

REGISTRY = {
    "functions": [
        {
            "function_code": "fn_query_bo",
            "api_schema": {
                "servers": [{"url": "http://mock-api:8080"}],
                "paths": {"/api/bo/query": {}},
            },
        }
    ],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "商机",
            "source_type": "API",
            "fields": [],
            "actions": [
                {
                    "action_code": "query_bo_by_owner",
                    "action_name": "按负责人查商机",
                    "description": "通过负责人ID查询商机列表",
                    "action_type": "query",
                    "function_refs": ["fn_query_bo"],
                    "params": [
                        {
                            "param_code": "owner_id",
                            "param_name": "负责人ID",
                            "param_type": "STRING",
                            "direction": "IN",
                            "required": True,
                        },
                    ],
                },
                {
                    "action_code": "calc_score",
                    "action_name": "计算评分",
                    "script": "def execute(params):\n    return {'score': 100}",
                    "action_type": "operation",
                    "function_refs": [],
                    "params": [
                        {"param_code": "bo_id", "param_type": "STRING", "direction": "IN"},
                        {"param_code": "score", "param_type": "NUMBER", "direction": "OUT"},
                    ],
                },
            ],
        }
    ],
    "relations": [],
}


def _create_app():
    from datacloud_data_service.api.routes import create_app

    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    return create_app(loader_override=loader)


def test_tools_list_includes_action_tools():
    with TestClient(_create_app()) as client:
        headers = {**HEADERS, "X-Tool-List-Mode": "per_object"}
        resp = client.post("/api/v1/mcp", json={
            "jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {},
        }, headers=headers)
        data = parse_sse_response(resp)
        tools = data["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "unified_data_query" in names
        assert "query_bo_by_owner" in names
        assert "calc_score" in names


def test_tools_call_script_action():
    with TestClient(_create_app()) as client:
        resp = client.post("/api/v1/mcp", json={
        "jsonrpc": "2.0", "id": "2", "method": "tools/call",
            "params": {"name": "calc_score", "arguments": {"bo_id": "B001"}},
        }, headers=HEADERS)
        result = parse_sse_response(resp)["result"]
        assert result["isError"] is False
        assert "100" in result["content"][0]["text"]


def test_tools_call_unknown_action_returns_error():
    with TestClient(_create_app()) as client:
        resp = client.post("/api/v1/mcp", json={
        "jsonrpc": "2.0", "id": "3", "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }, headers=HEADERS)
        result = parse_sse_response(resp)["result"]
        content = result.get("content", [])
        text = content[0].get("text", "") if content else ""
        assert result.get("isError") is True or "Unknown tool" in text or "error" in text.lower()
