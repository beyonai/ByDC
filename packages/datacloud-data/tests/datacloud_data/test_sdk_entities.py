import asyncio
import pytest
from unittest.mock import patch
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.exceptions import ActionNotFoundError

REGISTRY = {
    "functions": [
        {
            "function_code": "fn_get_bo",
            "function_type": "API",
            "api_schema": {
                "servers": [{"url": "http://mock:8080"}],
                "paths": {"/api/bo": {"post": {}}},
            },
        }
    ],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "销售商机",
            "description": "商机对象",
            "source_type": "DB",
            "datasource_alias": "crm_db",
            "table_name": "sales_business_opportunity",
            "fields": [
                {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"},
                {
                    "field_code": "bo_name",
                    "field_name": "商机名称",
                    "field_type": "STRING",
                    "aliases": ["项目名称"],
                },
            ],
            "actions": [
                {
                    "action_code": "query_bo_by_owner",
                    "action_name": "按负责人查商机",
                    "description": "通过负责人ID查询商机列表",
                    "params": [
                        {
                            "param_code": "owner_id",
                            "param_name": "负责人ID",
                            "direction": "IN",
                            "param_type": "STRING",
                            "required": True,
                            "mapping_path": "$.requestBody.ownerId",
                        },
                        {
                            "param_code": "bo_list",
                            "param_name": "商机列表",
                            "direction": "OUT",
                            "param_type": "ARRAY",
                            "mapping_path": "$.response.data",
                        },
                    ],
                    "function_refs": ["fn_get_bo"],
                    "action_type": "query",
                },
                {
                    "action_code": "calc_score",
                    "action_name": "计算评分",
                    "description": "计算商机评分",
                    "script": "def execute(params):\n    return {'score': 100}",
                    "function_refs": [],
                    "action_type": "operation",
                    "params": [
                        {
                            "param_code": "score",
                            "param_name": "评分",
                            "direction": "OUT",
                            "param_type": "NUMBER",
                        },
                    ],
                },
            ],
        }
    ],
    "relations": [],
}


def test_object_get_description_contains_fields_and_actions() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    desc = obj.get_description()
    assert "销售商机" in desc
    assert "bo_name" in desc
    assert "项目名称" in desc
    assert "query_bo_by_owner" in desc


def test_action_get_schema_returns_input_output() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    schema = obj.get_action_schema("query_bo_by_owner")
    assert "inputSchema" in schema
    assert "outputSchema" in schema
    assert "name" in schema
    assert "description" in schema
    assert "owner_id" in schema["inputSchema"]["properties"]
    assert schema["inputSchema"]["required"] == ["owner_id"]


def test_list_action_codes_includes_script_action() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    codes = obj.list_action_codes()
    assert "query_bo_by_owner" in codes
    assert "calc_score" in codes


def test_action_get_schema_is_cached() -> None:
    """get_schema 结果缓存，多次调用返回同一对象。"""
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    s1 = obj.get_action_schema("query_bo_by_owner")
    s2 = obj.get_action_schema("query_bo_by_owner")
    assert s1 is s2


def test_unknown_action_raises() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    with pytest.raises(ActionNotFoundError):
        obj.get_action_schema("nonexistent_action")


def test_get_description_shows_script_action() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    obj = loader.get_object("sales_bo")
    desc = obj.get_description()
    assert "calc_score" in desc
    assert "脚本" in desc or "Script" in desc


def test_action_execute_supports_get_query_and_path_params() -> None:
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "functions": [
                {
                    "function_code": "fn_get_user_detail",
                    "function_type": "API",
                    "api_schema": {
                        "openapi": "3.0.3",
                        "info": {"title": "查询人员详情", "version": "1.0.0"},
                        "servers": [{"url": "http://mock:8080"}],
                        "paths": {
                            "/api/v1/users/{userId}": {
                                "get": {
                                    "parameters": [
                                        {
                                            "name": "userId",
                                            "in": "path",
                                            "required": True,
                                            "schema": {"type": "string"},
                                        },
                                        {
                                            "name": "keyword",
                                            "in": "query",
                                            "required": False,
                                            "schema": {"type": "string"},
                                        },
                                    ],
                                    "responses": {"200": {"description": "查询结果"}},
                                }
                            }
                        },
                    },
                }
            ],
            "objects": [
                {
                    "object_code": "po_users",
                    "object_name": "人员",
                    "source_type": "API",
                    "fields": [],
                    "actions": [
                        {
                            "action_code": "query_user_detail",
                            "action_name": "查询人员详情",
                            "description": "按用户ID查询人员详情",
                            "action_type": "query",
                            "function_refs": ["fn_get_user_detail"],
                            "params": [
                                {
                                    "param_code": "user_id",
                                    "param_name": "用户ID",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "mapping_path": "$.path.userId",
                                },
                                {
                                    "param_code": "keyword",
                                    "param_name": "关键字",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "mapping_path": "$.query.keyword",
                                },
                            ],
                        }
                    ],
                }
            ],
            "relations": [],
        }
    )
    obj = loader.get_object("po_users")
    captured: dict[str, object] = {}

    class _MockResponse:
        status_code = 200
        text = "ok"

        @staticmethod
        def json() -> list[dict[str, str]]:
            return [{"userId": "U001"}]

    class _MockAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def __aenter__(self) -> "_MockAsyncClient":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            del exc_type, exc, tb

        async def request(self, method: str, url: str, **kwargs: object) -> _MockResponse:
            captured["method"] = method
            captured["url"] = url
            captured["kwargs"] = kwargs
            return _MockResponse()

    async def _run() -> dict[str, object]:
        with patch("httpx.AsyncClient", _MockAsyncClient):
            return await obj.invoke_action(
                "query_user_detail",
                {"user_id": "U001", "keyword": "alice"},
            )

    result = asyncio.run(_run())

    assert captured["method"] == "GET"
    assert captured["url"] == "http://mock:8080/api/v1/users/U001"
    assert captured["kwargs"] == {
        "headers": {"Content-Type": "application/json"},
        "params": {"keyword": "alice"},
    }
    assert result["records"] == [{"userId": "U001"}]
