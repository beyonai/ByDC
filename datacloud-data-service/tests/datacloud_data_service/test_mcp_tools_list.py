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


def test_tool_list_mode_unified_returns_only_operation_and_unified() -> None:
    """tool_list_mode=unified 时仅返回 unified_query + operation 类动作。"""
    from datacloud_data_sdk.ontology.loader import OntologyLoader
    from datacloud_data_service.tools.registry import ToolRegistry

    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    registry = ToolRegistry(loader)
    tools = registry.list_tools(tool_list_mode="unified", object_ids=["po_users", "todo_items"])
    names = [t["name"] for t in tools]
    assert "unified_data_query" in names
    for t in tools:
        if t["name"] != "unified_data_query":
            assert t.get("_meta", {}).get("action_type") == "operation"
    assert "create_todo" in names
    assert "query_todo_list" not in names


def test_tool_list_mode_per_object_returns_all_ontology_actions() -> None:
    """tool_list_mode=per_object 时返回本体动作（含 query + operation）+ DB/KB 虚拟动作。"""
    from datacloud_data_sdk.ontology.loader import OntologyLoader
    from datacloud_data_service.tools.registry import ToolRegistry
    from datacloud_data_service.tools.virtual_action_injector import inject_virtual_actions

    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    inject_virtual_actions(loader)
    registry = ToolRegistry(loader)
    tools = registry.list_tools(
        tool_list_mode="per_object",
        object_ids=["po_users", "todo_items", "sales_business_opportunity"],
    )
    names = [t["name"] for t in tools]
    assert "unified_data_query" in names
    assert "query_todo_list" in names
    assert "create_todo" in names
    assert "query_sales_business_opportunity" in names


def test_action_tool_includes_action_type() -> None:
    """生成的工具 _meta 含 action_type。"""
    from datacloud_data_sdk.ontology.loader import OntologyLoader
    from datacloud_data_service.tools.registry import ToolRegistry

    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    registry = ToolRegistry(loader)
    tools = registry.list_tools(object_ids=["po_users"], tool_list_mode="per_object")
    action_tools = [t for t in tools if t.get("name") != "unified_data_query"]
    assert len(action_tools) > 0
    for t in action_tools:
        meta = t.get("_meta", {})
        assert "action_type" in meta
        assert meta["action_type"] in ("query", "operation")


def test_mcp_tools_list_respects_x_tool_list_mode_header() -> None:
    """X-Tool-List-Mode: unified 仅返回 operation；per_object 返回全部+虚拟动作。"""
    from datacloud_data_sdk.ontology.loader import OntologyLoader
    from datacloud_data_service.api.routes import create_app

    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    app = create_app(loader_override=loader)
    with TestClient(app) as client:
        headers = {**MCP_HEADERS, "X-Tenant-Id": "t1"}
        resp_unified = client.post(
            "/api/v1/mcp",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
            headers={**headers, "X-Tool-List-Mode": "unified"},
        )
        resp_per = client.post(
            "/api/v1/mcp",
            json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
            headers={**headers, "X-Tool-List-Mode": "per_object"},
        )
        tools_unified = parse_sse_response(resp_unified)["result"]["tools"]
        tools_per = parse_sse_response(resp_per)["result"]["tools"]
        names_unified = [t["name"] for t in tools_unified]
        names_per = [t["name"] for t in tools_per]
        assert "unified_data_query" in names_unified
        assert "query_sales_business_opportunity" not in names_unified
        assert "query_sales_business_opportunity" in names_per


def test_tools_call_query_object_returns_records(tmp_path) -> None:
    """调用 query_{object_code} 返回 records 格式。"""
    import asyncio
    import json

    from datacloud_data_sdk.ontology.loader import OntologyLoader
    from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
    from datacloud_data_sdk.sql_executor.models import DataSourceConfig
    from datacloud_data_service.api.routes import create_app

    db_path = str(tmp_path / "test.db")
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    sqlite_config = DataSourceConfig(
        alias="ds_crm",
        db_type="SQLITE",
        jdbc_url=f"jdbc:sqlite:{db_path}",
        user="",
        password="",
    )
    app = create_app(loader_override=loader, datasource_configs={"ds_crm": sqlite_config})
    with TestClient(app) as client:
        client.get("/health")
        ds_manager = DataSourceManager(loader._config.datasource_configs)
        connector = ds_manager.get_connector("ds_crm")

        async def init_table() -> None:
            await connector.execute(
                "CREATE TABLE sales_business_opportunity (id INTEGER, bo_name TEXT)"
            )
            await connector.execute(
                "INSERT INTO sales_business_opportunity VALUES (1, 'test')"
            )

        asyncio.run(init_table())

        resp = client.post(
            "/api/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {
                    "name": "query_sales_business_opportunity",
                    "arguments": {"filters": {}},
                },
            },
            headers={**MCP_HEADERS, "X-Tenant-Id": "t1"},
        )
        data = parse_sse_response(resp)
        result = data.get("result", {})
        assert result.get("isError") is False
        text = result.get("content", [{}])[0].get("text", "{}")
        parsed = json.loads(text)
        assert "records" in parsed
        assert "total" in parsed


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
