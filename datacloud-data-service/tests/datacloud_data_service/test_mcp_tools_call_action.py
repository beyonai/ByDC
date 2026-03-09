"""MCP tools/call 操作类工具测试。"""
from fastapi.testclient import TestClient
from datacloud_data_sdk.ontology.loader import OntologyLoader

HEADERS = {
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
                    "function_refs": ["fn_query_bo"],
                    "params": [
                        {"param_code": "owner_id", "param_name": "负责人ID",
                         "param_type": "STRING", "direction": "IN", "required": True},
                    ],
                },
                {
                    "action_code": "calc_score",
                    "action_name": "计算评分",
                    "script": "def execute(params):\n    return {'score': 100}",
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
    from fastapi import FastAPI
    from datacloud_data_service.api.mcp_handler import router as mcp_router

    app = FastAPI()
    app.include_router(mcp_router, prefix="/api/v1")
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    app.state.loader = loader
    return app


def test_tools_list_includes_action_tools():
    client = TestClient(_create_app())
    resp = client.post("/api/v1/mcp", json={
        "jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {},
    }, headers=HEADERS)
    tools = resp.json()["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "unified_data_query" in names
    assert "query_bo_by_owner" in names
    assert "calc_score" in names


def test_tools_call_script_action():
    client = TestClient(_create_app())
    resp = client.post("/api/v1/mcp", json={
        "jsonrpc": "2.0", "id": "2", "method": "tools/call",
        "params": {"name": "calc_score", "arguments": {"bo_id": "B001"}},
    }, headers=HEADERS)
    result = resp.json()["result"]
    assert result["isError"] is False
    assert "100" in result["content"][0]["text"]


def test_tools_call_unknown_action_returns_error():
    client = TestClient(_create_app())
    resp = client.post("/api/v1/mcp", json={
        "jsonrpc": "2.0", "id": "3", "method": "tools/call",
        "params": {"name": "nonexistent_tool", "arguments": {}},
    }, headers=HEADERS)
    result = resp.json()["result"]
    assert result["isError"] is True
