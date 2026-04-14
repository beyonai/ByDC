"""MCP tools/call 操作类工具测试。"""

import json

from fastapi.testclient import TestClient

from datacloud_data_sdk.plan.models import QueryExecutionPlan, parse_plan
from datacloud_data_sdk.plan.query_plan_generator import BasePlanGenerator
from tests.datacloud_data_service.mcp_test_utils import parse_sse_response
from datacloud_data_sdk.ontology.loader import OntologyLoader

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

MOCK_QUERY_PLAN = {
    "question": "查商机",
    "can_answer": True,
    "steps": [
        {
            "step_id": "s1",
            "type": "SQL",
            "source_id": "SRC_TEST_DB",
            "datasource_alias": "test_db",
            "sql_template": "SELECT '1' AS bo_id, '项目A' AS bo_name",
            "output_ref": "bo_list",
        }
    ],
    "aggregation": {
        "strategy": "DIRECT",
        "final_step_id": "s1",
        "columns": [
            {"name": "bo_id", "label": "商机ID", "type": "string"},
            {"name": "bo_name", "label": "商机名称", "type": "string"},
        ],
    },
}


class CapturePlanGenerator(BasePlanGenerator):
    def __init__(self) -> None:
        self.captured_knowledge_context: str | None = None

    async def generate(
        self,
        payload,
        question: str,
        knowledge_context: str | None = None,
        validation_errors=None,
        term_loader=None,
    ) -> QueryExecutionPlan:
        self.captured_knowledge_context = knowledge_context
        return parse_plan(MOCK_QUERY_PLAN, question)


def _create_app():
    from datacloud_data_service.api.routes import create_app

    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    return create_app(loader_override=loader)


def _create_query_app(tmp_path):
    from datacloud_data_sdk.sql_executor.models import DataSourceConfig
    from datacloud_data_service.api.routes import create_app

    app = create_app()
    loader = OntologyLoader()
    loader.load_from_content(
        {
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
                        {
                            "field_code": "bo_name",
                            "field_name": "商机名称",
                            "field_type": "STRING",
                        },
                    ],
                    "actions": [],
                }
            ],
            "relations": [],
        }
    )
    generator = CapturePlanGenerator()
    loader.configure(
        plan_generator=generator,
        datasource_configs={
            "test_db": DataSourceConfig(
                alias="test_db", db_type="SQLITE", jdbc_url="jdbc:sqlite::memory:"
            )
        },
        csv_base_dir=str(tmp_path),
    )
    app.state.loader = loader
    app.state.test_loader = loader
    return app, generator


def test_tools_list_includes_action_tools():
    with TestClient(_create_app()) as client:
        headers = {**HEADERS, "X-Tool-List-Mode": "per_object"}
        resp = client.post(
            "/api/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/list",
                "params": {},
            },
            headers=headers,
        )
        data = parse_sse_response(resp)
        tools = data["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "unified_data_query" in names
        assert "query_bo_by_owner" in names
        assert "calc_score" in names


def test_tools_call_script_action():
    with TestClient(_create_app()) as client:
        resp = client.post(
            "/api/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tools/call",
                "params": {"name": "calc_score", "arguments": {"bo_id": "B001"}},
            },
            headers=HEADERS,
        )
        result = parse_sse_response(resp)["result"]
        assert result["isError"] is False
        payload = json.loads(result["content"][0]["text"])
        assert payload["records"] == [{"score": 100}]
        assert payload["total"] == 1


def test_tools_call_unknown_action_returns_error():
    with TestClient(_create_app()) as client:
        resp = client.post(
            "/api/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "3",
                "method": "tools/call",
                "params": {"name": "nonexistent_tool", "arguments": {}},
            },
            headers=HEADERS,
        )
        result = parse_sse_response(resp)["result"]
        content = result.get("content", [])
        text = content[0].get("text", "") if content else ""
        assert result.get("isError") is True or "Unknown tool" in text or "error" in text.lower()


def test_tools_call_unified_query_forwards_knowledge_context(tmp_path) -> None:
    app, generator = _create_query_app(tmp_path)
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.loader = app.state.test_loader
        resp = client.post(
            "/api/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "4",
                "method": "tools/call",
                "params": {
                    "name": "unified_data_query",
                    "arguments": {
                        "question": "查商机",
                        "knowledge_context": "商机金额按含税口径统计",
                    },
                },
            },
            headers=HEADERS,
        )
        result = parse_sse_response(resp)["result"]
        assert result["isError"] is False
        assert generator.captured_knowledge_context == "商机金额按含税口径统计"
