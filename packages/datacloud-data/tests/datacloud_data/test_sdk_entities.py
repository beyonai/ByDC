import asyncio
from unittest.mock import patch

import pytest
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.exceptions import ActionNotFoundError
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.term_loader import KbTermLoader
from datacloud_data_sdk.plan.term_resolver import TermResolver

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
    assert "requestBody" in schema["inputSchema"]["properties"]
    assert schema["inputSchema"]["required"] == ["requestBody"]
    request_body_schema = schema["inputSchema"]["properties"]["requestBody"]
    assert request_body_schema["type"] == "object"
    assert request_body_schema["required"] == ["ownerId"]
    assert request_body_schema["properties"]["ownerId"]["type"] == "string"
    assert schema["outputSchema"]["properties"]["bo_list"]["type"] == "array"
    assert schema["outputSchema"]["properties"]["bo_list"]["items"] == {"type": "string"}


def test_action_get_schema_preserves_decimal_and_datetime_hints() -> None:
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "functions": [],
            "objects": [
                {
                    "object_code": "expense",
                    "object_name": "费用",
                    "source_type": "API",
                    "fields": [],
                    "actions": [
                        {
                            "action_code": "apply_expense",
                            "action_name": "申请费用",
                            "action_type": "operation",
                            "function_refs": [],
                            "params": [
                                {
                                    "param_code": "expense_amount",
                                    "param_name": "费用金额",
                                    "direction": "IN",
                                    "param_type": "DECIMAL",
                                },
                                {
                                    "param_code": "apply_time",
                                    "param_name": "申请时间",
                                    "direction": "IN",
                                    "param_type": "DATETIME",
                                },
                            ],
                        }
                    ],
                }
            ],
            "relations": [],
        }
    )
    obj = loader.get_object("expense")
    schema = obj.get_action_schema("apply_expense")
    assert schema["inputSchema"]["required"] == ["userConfirmed"]
    amount_schema = schema["inputSchema"]["properties"]["expense_amount"]
    assert amount_schema["type"] == "number"
    assert amount_schema["format"] == "decimal"
    time_schema = schema["inputSchema"]["properties"]["apply_time"]
    assert time_schema["type"] == "string"
    assert time_schema["format"] == "date-time"
    confirm_schema = schema["inputSchema"]["properties"]["userConfirmed"]
    assert confirm_schema["type"] == "boolean"


def test_action_get_schema_supports_array_and_term_enum() -> None:
    loader = OntologyLoader()
    loader.configure(
        term_loader=KbTermLoader(
            {
                "priority.code": [
                    {"code": "HIGH", "label": "高"},
                    {"code": "LOW", "label": "低"},
                ]
            }
        )
    )
    loader.load_from_content(
        {
            "functions": [],
            "objects": [
                {
                    "object_code": "todo_items",
                    "object_name": "待办",
                    "source_type": "API",
                    "fields": [],
                    "actions": [
                        {
                            "action_code": "create_todo",
                            "action_name": "创建待办",
                            "action_type": "operation",
                            "function_refs": [],
                            "params": [
                                {
                                    "param_code": "handlerIds",
                                    "param_name": "处理人",
                                    "direction": "IN",
                                    "param_type": "ARRAY",
                                    "termMeta": {
                                        "termMasterType": "list",
                                        "termTypeCode": "staffName",
                                        "termField": "code",
                                    },
                                },
                                {
                                    "param_code": "priority",
                                    "param_name": "优先级",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "termMeta": {
                                        "termMasterType": "dict",
                                        "termTypeCode": "priority",
                                        "termField": "code",
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
            "relations": [],
        }
    )

    obj = loader.get_object("todo_items")
    schema = obj.get_action_schema("create_todo")
    assert schema["inputSchema"]["required"] == ["userConfirmed"]

    handler_ids_schema = schema["inputSchema"]["properties"]["handlerIds"]
    assert handler_ids_schema["type"] == "array"
    assert handler_ids_schema["items"] == {"type": "string"}
    assert set(handler_ids_schema) == {"type", "items", "description"}

    priority_schema = schema["inputSchema"]["properties"]["priority"]
    assert priority_schema["type"] == "string"
    assert priority_schema["enum"] == ["HIGH", "LOW"]
    assert set(priority_schema) == {"type", "description", "enum"}


@pytest.mark.asyncio
async def test_invoke_action_returns_execution_steps_in_detail_mode() -> None:
    class _FakeGatewayContext:
        def __init__(self) -> None:
            self.events: list[tuple[str, str]] = []

        async def emit_state(self, content: str, **_: object) -> None:
            self.events.append(("state", content))

        async def emit_chunk(self, content: str, **_: object) -> None:
            self.events.append(("chunk", content))

    loader = OntologyLoader()
    loader.configure(
        term_loader=KbTermLoader(
            {
                "priority.code": [
                    {"code": "HIGH", "label": "高"},
                    {"code": "LOW", "label": "低"},
                ]
            }
        )
    )
    loader.load_from_content(
        {
            "functions": [],
            "objects": [
                {
                    "object_code": "todo_items",
                    "object_name": "待办",
                    "source_type": "API",
                    "fields": [],
                    "actions": [
                        {
                            "action_code": "create_todo",
                            "action_name": "创建待办",
                            "action_type": "operation",
                            "script": (
                                "def execute(params):\n"
                                "    return {'priority': params['priority']}\n"
                            ),
                            "function_refs": [],
                            "params": [
                                {
                                    "param_code": "priority",
                                    "param_name": "优先级",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "termMeta": {
                                        "termMasterType": "dict",
                                        "termTypeCode": "priority",
                                        "termField": "code",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
            "relations": [],
        }
    )

    obj = loader.get_object("todo_items")
    gateway_context = _FakeGatewayContext()
    with InvocationContext(session_id="detail-confirm-cache"):
        first_result = await obj.invoke_action(
            "create_todo",
            {"优先级": "高", "userConfirmed": False},
        )
    with InvocationContext(
        session_id="detail-confirm-cache",
        tool_call_detail=True,
        gateway_context=gateway_context,
    ):
        result = await obj.invoke_action(
            "create_todo",
            {"优先级": "高", "userConfirmed": True},
        )

    assert first_result["result_type"] == "ask_user"
    assert result["records"] == [{"priority": "HIGH"}]
    assert [item["step"] for item in result["execution_steps"]] == [
        "request_received",
        "param_mapping",
        "param_validation",
        "term_resolved",
        "user_confirmation",
        "action_executing",
        "action_completed",
    ]
    assert result["execution_steps"][1]["data"]["params"] == {
        "priority": "高",
        "userConfirmed": True,
    }
    assert result["execution_steps"][2]["data"]["missing_required_params"] == []
    assert result["execution_steps"][3]["data"]["params"] == {"priority": "HIGH"}
    assert result["execution_steps"][4]["data"] == {
        "cache_status": "confirmed",
        "user_confirmed": True,
    }
    assert result["execution_steps"][5]["data"]["mode"] == "script"
    assert gateway_context.events == []


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


def test_action_get_schema_supports_structured_request_body_and_root_array() -> None:
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "functions": [],
            "objects": [
                {
                    "object_code": "todo_items",
                    "object_name": "待办",
                    "source_type": "API",
                    "fields": [],
                    "actions": [
                        {
                            "action_code": "accept_todo",
                            "action_name": "接收待办",
                            "action_type": "operation",
                            "function_refs": [],
                            "params": [
                                {
                                    "param_code": "todoId",
                                    "param_name": "待办ID",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "mapping_path": "$.requestBody.todoId",
                                },
                                {
                                    "param_code": "userId",
                                    "param_name": "用户ID",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "mapping_path": "$.requestBody.user.user_id",
                                },
                                {
                                    "param_code": "orgId",
                                    "param_name": "组织ID",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "mapping_path": "$.requestBody.org[].org_id",
                                },
                            ],
                        },
                        {
                            "action_code": "accept_todo_batch",
                            "action_name": "批量接收待办",
                            "action_type": "operation",
                            "function_refs": [],
                            "params": [
                                {
                                    "param_code": "userCode",
                                    "param_name": "用户编码",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "mapping_path": "$.requestBody.[].user_code",
                                },
                            ],
                        },
                    ],
                }
            ],
            "relations": [],
        }
    )

    obj = loader.get_object("todo_items")
    schema = obj.get_action_schema("accept_todo")
    request_body_schema = schema["inputSchema"]["properties"]["requestBody"]
    batch_schema = obj.get_action_schema("accept_todo_batch")
    batch_request_body_schema = batch_schema["inputSchema"]["properties"]["requestBody"]

    assert schema["inputSchema"]["required"] == ["userConfirmed"]
    assert request_body_schema["type"] == "object"
    assert request_body_schema["properties"]["todoId"]["type"] == "string"
    assert request_body_schema["properties"]["user"]["type"] == "object"
    assert request_body_schema["properties"]["org"]["type"] == "array"
    assert (
        request_body_schema["properties"]["org"]["items"]["properties"]["org_id"]["type"]
        == "string"
    )
    assert "required" not in request_body_schema
    assert "required" not in request_body_schema["properties"]["user"]
    assert batch_schema["inputSchema"]["required"] == ["userConfirmed"]
    assert batch_request_body_schema["type"] == "array"
    assert batch_request_body_schema["items"]["properties"]["user_code"]["type"] == "string"


def test_action_execute_supports_structured_request_body_and_root_array() -> None:
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "functions": [
                {
                    "function_code": "fn_accept_todo",
                    "function_type": "API",
                    "api_schema": {
                        "openapi": "3.0.3",
                        "info": {"title": "接收待办", "version": "1.0.0"},
                        "servers": [{"url": "http://mock:8080"}],
                        "paths": {
                            "/api/v1/todos/accept": {
                                "post": {
                                    "responses": {"200": {"description": "处理成功"}},
                                }
                            }
                        },
                    },
                },
                {
                    "function_code": "fn_accept_todo_batch",
                    "function_type": "API",
                    "api_schema": {
                        "openapi": "3.0.3",
                        "info": {"title": "批量接收待办", "version": "1.0.0"},
                        "servers": [{"url": "http://mock:8080"}],
                        "paths": {
                            "/api/v1/todos/accept/batch": {
                                "post": {
                                    "responses": {"200": {"description": "处理成功"}},
                                }
                            }
                        },
                    },
                },
            ],
            "objects": [
                {
                    "object_code": "todo_items",
                    "object_name": "待办",
                    "source_type": "API",
                    "fields": [],
                    "actions": [
                        {
                            "action_code": "accept_todo",
                            "action_name": "接收待办",
                            "description": "嵌套 body 示例",
                            "action_type": "operation",
                            "function_refs": ["fn_accept_todo"],
                            "params": [
                                {
                                    "param_code": "todoId",
                                    "param_name": "待办ID",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "mapping_path": "$.requestBody.todoId",
                                },
                                {
                                    "param_code": "userId",
                                    "param_name": "用户ID",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "mapping_path": "$.requestBody.user.user_id",
                                },
                                {
                                    "param_code": "userCode",
                                    "param_name": "用户编码",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "mapping_path": "$.requestBody.user.user_code",
                                },
                            ],
                        },
                        {
                            "action_code": "accept_todo_batch",
                            "action_name": "批量接收待办",
                            "description": "根数组 body 示例",
                            "action_type": "operation",
                            "function_refs": ["fn_accept_todo_batch"],
                            "params": [
                                {
                                    "param_code": "userId",
                                    "param_name": "用户ID",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "mapping_path": "$.requestBody.[].user_id",
                                },
                                {
                                    "param_code": "userCode",
                                    "param_name": "用户编码",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "mapping_path": "$.requestBody.[].user_code",
                                },
                            ],
                        },
                    ],
                }
            ],
            "relations": [],
        }
    )
    obj = loader.get_object("todo_items")
    captured: list[dict[str, object]] = []

    class _MockResponse:
        status_code = 200
        text = "ok"

        @staticmethod
        def json() -> list[dict[str, str]]:
            return [{"status": "ok"}]

    class _MockAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def __aenter__(self) -> "_MockAsyncClient":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            del exc_type, exc, tb

        async def request(self, method: str, url: str, **kwargs: object) -> _MockResponse:
            captured.append({"method": method, "url": url, "kwargs": kwargs})
            return _MockResponse()

    async def _run() -> None:
        with patch("httpx.AsyncClient", _MockAsyncClient):
            await obj.invoke_action(
                "accept_todo",
                {
                    "requestBody": {
                        "todoId": "T001",
                        "user": {"user_id": "U001", "user_code": "A001"},
                    },
                    "userConfirmed": False,
                },
            )
            await obj.invoke_action(
                "accept_todo",
                {
                    "requestBody": {
                        "todoId": "T001",
                        "user": {"user_id": "U001", "user_code": "A001"},
                    },
                    "userConfirmed": True,
                },
            )
            await obj.invoke_action(
                "accept_todo_batch",
                {
                    "requestBody": [
                        {"user_id": "U001", "user_code": "A001"},
                        {"user_id": "U002", "user_code": "A002"},
                    ],
                    "userConfirmed": False,
                },
            )
            await obj.invoke_action(
                "accept_todo_batch",
                {
                    "requestBody": [
                        {"user_id": "U001", "user_code": "A001"},
                        {"user_id": "U002", "user_code": "A002"},
                    ],
                    "userConfirmed": True,
                },
            )

    asyncio.run(_run())

    assert len(captured) == 2
    assert captured[0]["kwargs"] == {
        "headers": {"Content-Type": "application/json"},
        "json": {
            "todoId": "T001",
            "user": {"user_id": "U001", "user_code": "A001"},
        },
    }
    assert captured[1]["kwargs"] == {
        "headers": {"Content-Type": "application/json"},
        "json": [
            {"user_id": "U001", "user_code": "A001"},
            {"user_id": "U002", "user_code": "A002"},
        ],
    }


def _build_confirmable_operation_loader() -> OntologyLoader:
    loader = OntologyLoader()
    loader.configure(
        term_loader=KbTermLoader(
            {
                "priority.code": [
                    {"code": "HIGH", "label": "高", "aliases": ["重复优先级"]},
                    {"code": "LOW", "label": "低", "aliases": ["重复优先级"]},
                ],
                "staff.code": [
                    {"code": "U001", "label": "张三", "aliases": ["重复负责人"]},
                    {"code": "U002", "label": "李四", "aliases": ["重复负责人"]},
                ],
            }
        )
    )
    loader.load_from_content(
        {
            "functions": [],
            "objects": [
                {
                    "object_code": "approval_task",
                    "object_name": "审批任务",
                    "source_type": "API",
                    "fields": [],
                    "actions": [
                        {
                            "action_code": "submit_approval",
                            "action_name": "提交审批",
                            "action_type": "operation",
                            "script": (
                                "def execute(params):\n"
                                "    return {'priority': params['priority'], 'owner_id': params['owner_id']}\n"
                            ),
                            "function_refs": [],
                            "params": [
                                {
                                    "param_code": "title",
                                    "param_name": "标题",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                },
                                {
                                    "param_code": "priority",
                                    "param_name": "优先级",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "termMeta": {
                                        "termMasterType": "dict",
                                        "termTypeCode": "priority",
                                        "termField": "code",
                                    },
                                },
                                {
                                    "param_code": "owner_id",
                                    "param_name": "负责人",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "termMeta": {
                                        "termMasterType": "dict",
                                        "termTypeCode": "staff",
                                        "termField": "code",
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
            "relations": [],
        }
    )
    return loader


def _build_confirmable_batch_loader() -> OntologyLoader:
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "functions": [],
            "objects": [
                {
                    "object_code": "batch_task",
                    "object_name": "批量任务",
                    "source_type": "API",
                    "fields": [],
                    "actions": [
                        {
                            "action_code": "submit_batch",
                            "action_name": "提交批量任务",
                            "action_type": "operation",
                            "script": (
                                "def execute(params):\n    return {'userId': params['userId']}\n"
                            ),
                            "function_refs": [],
                            "params": [
                                {
                                    "param_code": "userId",
                                    "param_name": "用户ID",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "mapping_path": "$.requestBody.[].user_id",
                                },
                                {
                                    "param_code": "userCode",
                                    "param_name": "用户编码",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "mapping_path": "$.requestBody.[].user_code",
                                },
                            ],
                        }
                    ],
                }
            ],
            "relations": [],
        }
    )
    return loader


def _build_confirmable_nested_array_term_loader() -> OntologyLoader:
    loader = OntologyLoader()
    loader.configure(
        term_loader=KbTermLoader(
            {
                "staff.code": [
                    {"code": "U001", "label": "胡永春"},
                    {"code": "U002", "label": "李四"},
                ]
            }
        )
    )
    loader.load_from_content(
        {
            "functions": [],
            "objects": [
                {
                    "object_code": "nested_batch_task",
                    "object_name": "嵌套批量任务",
                    "source_type": "API",
                    "fields": [],
                    "actions": [
                        {
                            "action_code": "submit_nested_batch",
                            "action_name": "提交嵌套批量任务",
                            "action_type": "operation",
                            "script": (
                                "def execute(params):\n"
                                "    return {'handlerIds': params['handlerIds']}\n"
                            ),
                            "function_refs": [],
                            "params": [
                                {
                                    "param_code": "title",
                                    "param_name": "标题",
                                    "direction": "IN",
                                    "param_type": "STRING",
                                    "required": True,
                                    "mapping_path": "$.requestBody.[].title",
                                },
                                {
                                    "param_code": "handlerIds",
                                    "param_name": "处理人",
                                    "direction": "IN",
                                    "param_type": "ARRAY",
                                    "required": True,
                                    "mapping_path": "$.requestBody.[].handler_ids[]",
                                    "termMeta": {
                                        "termMasterType": "dict",
                                        "termTypeCode": "staff",
                                        "termField": "code",
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
            "relations": [],
        }
    )
    return loader


def test_operation_schema_only_requires_user_confirmed() -> None:
    loader = _build_confirmable_operation_loader()
    obj = loader.get_object("approval_task")

    schema = obj.get_action_schema("submit_approval")

    assert schema["inputSchema"]["required"] == ["userConfirmed"]
    assert schema["inputSchema"]["properties"]["title"]["type"] == "string"
    assert schema["inputSchema"]["properties"]["priority"]["enum"] == ["HIGH", "LOW"]
    assert schema["inputSchema"]["properties"]["userConfirmed"]["type"] == "boolean"


@pytest.mark.asyncio
async def test_operation_returns_all_missing_required_and_term_errors() -> None:
    loader = _build_confirmable_operation_loader()
    obj = loader.get_object("approval_task")

    result = await obj.invoke_action(
        "submit_approval",
        {
            "priority": "重复优先级",
            "owner_id": "重复负责人",
            "userConfirmed": False,
        },
    )

    assert result["result_type"] == "ask_user"
    assert result["missing_required_params"] == [
        {"param_code": "title", "param_name": "标题"},
    ]
    assert [item["param_code"] for item in result["term_errors"]] == ["priority", "owner_id"]
    assert result["submitted_params"] == {
        "priority": "重复优先级",
        "owner_id": "重复负责人",
        "userConfirmed": False,
    }
    assert result["normalized_params"] == {
        "priority": "重复优先级",
        "owner_id": "重复负责人",
    }
    assert result["confirmation"] == {
        "user_confirmed": False,
        "cache_status": "validation_failed",
    }


@pytest.mark.asyncio
async def test_operation_array_required_param_detects_missing_items() -> None:
    loader = _build_confirmable_batch_loader()
    obj = loader.get_object("batch_task")

    result = await obj.invoke_action(
        "submit_batch",
        {
            "requestBody": [
                {"user_id": "U001", "user_code": "A001"},
                {"user_code": "A002"},
            ],
            "userConfirmed": False,
        },
    )

    assert result["result_type"] == "ask_user"
    assert result["missing_required_params"] == [
        {"param_code": "userId", "param_name": "用户ID"},
    ]
    assert result["normalized_params"] == {
        "userId": ["U001", None],
        "userCode": ["A001", "A002"],
    }
    assert result["confirmation"] == {
        "user_confirmed": False,
        "cache_status": "validation_failed",
    }


@pytest.mark.asyncio
async def test_operation_term_resolution_supports_nested_array_values() -> None:
    loader = _build_confirmable_nested_array_term_loader()
    obj = loader.get_object("nested_batch_task")

    result = await obj.invoke_action(
        "submit_nested_batch",
        {
            "requestBody": [
                {"title": "你好", "handler_ids": ["胡永春"]},
                {"title": "世界", "handler_ids": ["李四"]},
            ],
            "userConfirmed": False,
        },
    )

    assert result["result_type"] == "ask_user"
    assert result["term_errors"] == []
    assert result["normalized_params"] == {
        "title": ["你好", "世界"],
        "handlerIds": [["胡永春"], ["李四"]],
    }
    assert result["resolved_params"] == {
        "title": ["你好", "世界"],
        "handlerIds": [["U001"], ["U002"]],
    }
    assert result["confirmation"] == {
        "user_confirmed": False,
        "cache_status": "cached",
    }


def test_term_resolver_skips_none_and_blank_values_in_nested_arrays() -> None:
    resolver = TermResolver(
        KbTermLoader(
            {
                "staff.code": [
                    {"code": "U001", "label": "胡永春"},
                    {"code": "U002", "label": "李四"},
                ]
            }
        )
    )

    resolved = resolver._resolve_term_value(
        term_set="staff.code",
        term_type=None,
        term_field="code",
        dataset_id=None,
        raw_value=[["胡永春", ""], [None, "  ", "李四"]],
        param_name="处理人",
    )

    assert resolved == [["U001", ""], [None, "  ", "U002"]]


@pytest.mark.asyncio
async def test_operation_false_confirmation_caches_and_asks_user() -> None:
    loader = _build_confirmable_operation_loader()
    obj = loader.get_object("approval_task")

    with InvocationContext(session_id="operation-cache-pending"):
        result = await obj.invoke_action(
            "submit_approval",
            {
                "title": "发起审批",
                "priority": "高",
                "owner_id": "张三",
                "userConfirmed": False,
            },
        )

    assert result["result_type"] == "ask_user"
    assert result["resolved_params"] == {
        "title": "发起审批",
        "priority": "HIGH",
        "owner_id": "U001",
    }
    assert result["confirmation"] == {
        "user_confirmed": False,
        "cache_status": "cached",
    }


@pytest.mark.asyncio
async def test_operation_true_without_cache_returns_for_reconfirmation() -> None:
    loader = _build_confirmable_operation_loader()
    obj = loader.get_object("approval_task")

    with InvocationContext(session_id="operation-no-cache"):
        result = await obj.invoke_action(
            "submit_approval",
            {
                "title": "发起审批",
                "priority": "高",
                "owner_id": "张三",
                "userConfirmed": True,
            },
        )

    assert result["result_type"] == "ask_user"
    assert result["confirmation"] == {
        "user_confirmed": True,
        "cache_status": "confirm_without_cache",
    }
    assert result["resolved_params"] == {
        "title": "发起审批",
        "priority": "HIGH",
        "owner_id": "U001",
    }


@pytest.mark.asyncio
async def test_operation_true_with_mismatched_cache_returns_for_reconfirmation() -> None:
    loader = _build_confirmable_operation_loader()
    obj = loader.get_object("approval_task")

    with InvocationContext(session_id="operation-cache-mismatch"):
        first = await obj.invoke_action(
            "submit_approval",
            {
                "title": "发起审批",
                "priority": "高",
                "owner_id": "张三",
                "userConfirmed": False,
            },
        )
        second = await obj.invoke_action(
            "submit_approval",
            {
                "title": "重新发起审批",
                "priority": "低",
                "owner_id": "李四",
                "userConfirmed": True,
            },
        )

    assert first["confirmation"]["cache_status"] == "cached"
    assert second["result_type"] == "ask_user"
    assert second["confirmation"] == {
        "user_confirmed": True,
        "cache_status": "confirm_mismatch",
    }
    assert second["resolved_params"] == {
        "title": "重新发起审批",
        "priority": "LOW",
        "owner_id": "U002",
    }


@pytest.mark.asyncio
async def test_operation_true_with_matching_cache_executes_and_returns_params() -> None:
    loader = _build_confirmable_operation_loader()
    obj = loader.get_object("approval_task")

    with InvocationContext(session_id="operation-cache-confirmed"):
        first = await obj.invoke_action(
            "submit_approval",
            {
                "title": "发起审批",
                "priority": "高",
                "owner_id": "张三",
                "userConfirmed": False,
            },
        )
        result = await obj.invoke_action(
            "submit_approval",
            {
                "title": "发起审批",
                "priority": "高",
                "owner_id": "张三",
                "userConfirmed": True,
            },
        )

    assert first["result_type"] == "ask_user"
    assert result["result_type"] == "normal"
    assert result["records"] == [{"priority": "HIGH", "owner_id": "U001"}]
    assert result["submitted_params"] == {
        "title": "发起审批",
        "priority": "高",
        "owner_id": "张三",
        "userConfirmed": True,
    }
    assert result["normalized_params"] == {
        "title": "发起审批",
        "priority": "高",
        "owner_id": "张三",
    }
    assert result["resolved_params"] == {
        "title": "发起审批",
        "priority": "HIGH",
        "owner_id": "U001",
    }
    assert result["confirmation"] == {
        "user_confirmed": True,
        "cache_status": "confirmed",
    }
