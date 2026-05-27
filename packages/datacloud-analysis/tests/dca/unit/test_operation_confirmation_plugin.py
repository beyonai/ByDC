from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import pytest
from datacloud_analysis.tool_hook_plugins.builtin.operation_confirmation_plugin import (
    before_call_back,
    build_operation_form,
    restore_action_params,
)
from datacloud_analysis.tool_hook_plugins.types import ClarificationNeededError, HookContext


@dataclass
class _Field:
    field_code: str
    field_name: str
    field_type: str = "STRING"
    term_set: str | None = None
    term_type: str | None = None
    term_field: str | None = None
    dataset_id: int | None = None


@dataclass
class _Action:
    action_code: str = "insert_customer"
    action_name: str = "新增客户"
    action_type: str = "operation"
    action_family: str = "insert"
    is_virtual: bool = True
    params: list[Any] = field(default_factory=list)
    legacy_aliases: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] | None = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "records": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "customerId": {"type": "string", "description": "客户 ID"},
                            "status": {"type": "string", "description": "状态"},
                        },
                        "required": ["customerId"],
                    },
                }
            },
            "required": ["records"],
        }
    )


@dataclass
class _Param:
    param_code: str
    param_name: str
    direction: str = "IN"
    param_type: str = "STRING"
    required: bool = False
    default_value: Any = None
    mapping_path: str = ""
    term_set: str | None = None
    term_type: str | None = None
    term_field: str | None = None
    dataset_id: int | None = None


@dataclass
class _Class:
    actions: list[Any]
    fields: list[Any]


class _Loader:
    def __init__(self, action: _Action) -> None:
        self._class = _Class(
            actions=[action],
            fields=[
                _Field("customerId", "客户 ID"),
                _Field(
                    "status",
                    "状态",
                    term_set="customer_status.code",
                    term_type="lookup",
                    term_field="code",
                    dataset_id=100,
                ),
            ],
        )

    def get_ontology_classes(self) -> list[_Class]:
        return [self._class]

    def get_views(self) -> list[Any]:
        return []


async def test_operation_before_call_raises_form_interrupt() -> None:
    action = _Action()
    ctx: HookContext = {
        "tool_name": "insert_customer",
        "tool_params": {
            "records": [{"customerId": "C001", "status": "TODO"}],
        },
        "metadata": {"loader": _Loader(action), "state": {}},
    }

    with pytest.raises(ClarificationNeededError) as exc_info:
        await before_call_back(ctx)

    context = exc_info.value.context
    assert context["interrupt_type"] == "operation_form"
    form = context["operation_form"]
    assert form["actionCode"] == "insert_customer"
    assert form["rule"][0][0]["itemId"]
    status_field = form["rule"][0][1]
    assert status_field["formType"] == "term_select"
    assert status_field["term"]["termSet"] == "customer_status.code"


async def test_operation_form_keeps_action_param_term_metadata() -> None:
    action = _Action(
        action_code="assign_task",
        action_name="分配任务",
        action_family="operation",
        input_schema=None,
        params=[
            _Param("assignee", "负责人", required=True),
            _Param(
                "status",
                "状态",
                term_set="task_status.code",
                term_type="lookup",
                term_field="code",
                dataset_id=200,
            ),
        ],
    )
    ctx: HookContext = {
        "tool_name": "assign_task",
        "tool_params": {"assignee": "U001", "status": "TODO"},
        "metadata": {"loader": _Loader(action), "state": {}},
    }

    with pytest.raises(ClarificationNeededError) as exc_info:
        await before_call_back(ctx)

    fields = exc_info.value.context["operation_form"]["rule"][0]
    status_field = next(field for field in fields if field["fieldCode"] == "status")
    assert status_field["formType"] == "term_select"
    assert status_field["term"] == {
        "termSet": "task_status.code",
        "termTypeCode": "task_status",
        "termField": "code",
        "datasetId": 200,
    }


async def test_operation_before_call_patches_confirmed_params() -> None:
    action = _Action()
    rule = [
        [
            {
                "itemId": "item-1",
                "fieldCode": "customerId",
                "fieldType": "string",
                "fieldValue": "C001",
            },
            {"fieldCode": "status", "fieldType": "string", "fieldValue": "DONE"},
        ]
    ]
    ctx: HookContext = {
        "tool_name": "insert_customer",
        "tool_params": {"records": [{"customerId": "old"}]},
        "metadata": {
            "loader": _Loader(action),
            "state": {
                "clarification_formatted_params": {
                    "tool_name": "insert_customer",
                    "interrupt_type": "operation_form",
                    "formId": "form-1",
                    "confirmed": True,
                    "rule": rule,
                    "params": restore_action_params(rule, action=action),
                }
            },
        },
    }

    decision = await before_call_back(ctx)

    assert decision is not None
    assert decision["action"] == "patch"
    params = decision["patch"]["tool_params"]
    assert params["records"] == [{"customerId": "C001", "status": "DONE"}]
    assert params["userConfirmed"] is True
    assert params["_operationConfirm"]["confirmed"] is True


def test_restore_action_params_handles_object_array_field_value() -> None:
    rule = [
        [
            {
                "itemId": "item-1",
                "fieldCode": "contacts",
                "fieldType": "array",
                "children": [
                    [
                        {
                            "itemId": "contact-1",
                            "fieldCode": "name",
                            "fieldType": "string",
                            "fieldValue": "张三",
                        }
                    ],
                    [
                        {
                            "itemId": "contact-2",
                            "fieldCode": "name",
                            "fieldType": "string",
                            "fieldValue": "李四",
                        }
                    ],
                ],
            }
        ]
    ]

    params = restore_action_params(rule)

    assert params["contacts"] == [{"name": "张三"}, {"name": "李四"}]


def test_build_operation_form_uses_children_for_object_fields() -> None:
    action = _Action(
        action_code="update_customer",
        action_name="修改客户",
        action_family="operation",
        input_schema={
            "type": "object",
            "properties": {
                "customer": {
                    "type": "object",
                    "properties": {
                        "customerId": {"type": "string", "description": "客户 ID"},
                        "status": {"type": "string", "description": "状态"},
                    },
                },
                "contacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "联系人姓名"},
                        },
                    },
                },
            },
        },
    )

    form = build_operation_form(
        action,
        {
            "customer": {"customerId": "C001", "status": "TODO"},
            "contacts": [{"name": "张三"}],
        },
    )

    fields = form["rule"][0]
    customer_field = next(field for field in fields if field["fieldCode"] == "customer")
    contacts_field = next(field for field in fields if field["fieldCode"] == "contacts")
    assert customer_field["fieldType"] == "object"
    assert customer_field["formType"] == "object"
    assert contacts_field["fieldType"] == "array<object>"
    assert contacts_field["formType"] == "array"
    assert "fieldValue" not in customer_field
    assert "fieldValue" not in contacts_field
    assert customer_field["children"][0][0]["fieldValue"] == "C001"
    assert contacts_field["children"][0][0]["fieldValue"] == "张三"


def test_restore_action_params_keeps_legacy_object_array_field_value_compatibility() -> None:
    rule = [
        [
            {
                "itemId": "item-1",
                "fieldCode": "contacts",
                "fieldType": "array",
                "fieldValue": [
                    [
                        {
                            "itemId": "contact-1",
                            "fieldCode": "name",
                            "fieldType": "string",
                            "fieldValue": "张三",
                        }
                    ]
                ],
            }
        ]
    ]

    params = restore_action_params(rule)

    assert params["contacts"] == [{"name": "张三"}]


def test_build_operation_form_keeps_array_object_from_mapping_path_as_children() -> None:
    action = _Action(
        action_code="create_by_rd_task",
        action_name="新增研发任务",
        action_family="operation",
        input_schema=None,
        params=[
            _Param(
                "taskName",
                "任务名称",
                mapping_path="$.requestBody.taskName",
            ),
            _Param(
                "fileName",
                "附件文件名",
                mapping_path="$.requestBody.files[].fileName",
            ),
            _Param(
                "filePath",
                "附件文件路径",
                mapping_path="$.requestBody.files[].filePath",
            ),
        ],
    )

    form = build_operation_form(
        action,
        {
            "requestBody": {
                "taskName": "研发任务",
                "files": [{"fileName": "需求文档.docx", "filePath": "/tmp/需求文档.docx"}],
            }
        },
    )

    fields = form["rule"][0]
    assert [field["fieldCode"] for field in fields] == ["taskName", "files"]
    files_field = fields[1]
    assert files_field["fieldType"] == "array<object>"
    assert files_field["formType"] == "array"
    assert "fieldValue" not in files_field
    assert files_field["fieldPath"] == "requestBody.files"
    assert [field["fieldCode"] for field in files_field["children"][0]] == [
        "fileName",
        "filePath",
    ]
    assert files_field["children"][0][0]["fieldValue"] == "需求文档.docx"


def test_build_operation_form_keeps_kb_write_schema_and_uses_field_description() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "description": (
            "写入会议纪要知识库文档。content 必须提供完整正文，不得摘要、截断、删减或改写。"
        ),
        "x-dc-action-family": "write",
        "x-dc-scope-type": "object",
        "properties": {
            "labels": {
                "type": "object",
                "additionalProperties": False,
                "description": "知识库属性标签，键必须是对象属性编码；主键字段不在此处填写。",
                "properties": {
                    "status": {"type": "string", "description": "状态"},
                    "owner": {"type": "string", "description": "负责人"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标签",
                    },
                },
            },
            "source_path": {
                "type": "string",
                "description": "上传到知识库后的文件全路径，以 / 开头，不包括知识库名称。",
            },
            "content": {
                "type": "string",
                "description": "源文件完整正文文本，必须包含原文全部内容，不得摘要、截断、删减或改写。",
            },
            "file_description": {"type": "string", "description": "文件描述。"},
        },
        "required": ["source_path", "content"],
    }
    original_schema = deepcopy(schema)
    action = _Action(
        action_code="write_meeting_doc",
        action_name="写入会议纪要",
        action_family="write",
        input_schema=schema,
    )

    form = build_operation_form(
        action,
        {
            "labels": {"status": "active", "owner": "张三", "tags": ["重点", "外部"]},
            "source_path": "/meeting/a.docx",
            "content": "正文",
            "file_description": "描述",
        },
    )

    assert schema == original_schema
    fields = form["rule"][0]
    labels_field = next(field for field in fields if field["fieldCode"] == "labels")
    source_path_field = next(field for field in fields if field["fieldCode"] == "source_path")
    content_field = next(field for field in fields if field["fieldCode"] == "content")
    assert labels_field["fieldName"] == "知识库属性标签"
    assert (
        labels_field["description"]
        == "知识库属性标签，键必须是对象属性编码；主键字段不在此处填写。"
    )
    assert "fieldValue" not in labels_field
    assert labels_field["children"][0][0]["fieldName"] == "状态"
    assert labels_field["children"][0][0]["description"] == "状态"
    tags_field = next(
        field for field in labels_field["children"][0] if field["fieldCode"] == "tags"
    )
    assert tags_field["fieldType"] == "array<string>"
    assert tags_field["formType"] == "input"
    assert tags_field["fieldValue"] == ["重点", "外部"]
    assert source_path_field["fieldName"] == "文件路径"
    assert source_path_field["description"].startswith("上传到知识库后的文件全路径")
    assert content_field["fieldName"] == "正文内容"

    params = restore_action_params(form["rule"], action=action)
    assert params == {
        "labels": {"status": "active", "owner": "张三", "tags": ["重点", "外部"]},
        "source_path": "/meeting/a.docx",
        "content": "正文",
        "file_description": "描述",
    }


def test_build_operation_form_uses_children_for_dynamic_update_filters() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "description": "按 filters 修改动态表产品记录。必须提供 filters。",
        "x-dc-action-family": "update",
        "x-dc-scope-type": "object",
        "properties": {
            "values": {
                "type": "object",
                "additionalProperties": False,
                "description": "需要修改的字段值，字段统一填写对象属性编码。",
                "properties": {
                    "product_name": {"type": "string", "description": "产品名称"},
                    "product_price": {"type": "number", "description": "产品价格"},
                    "category": {"type": "string", "description": "产品分类"},
                },
            },
            "filters": {
                "type": "array",
                "description": "过滤条件列表，field 统一填写属性编码",
                "items": {
                    "oneOf": [
                        {
                            "type": "object",
                            "description": "产品名称（product_name）过滤条件",
                            "properties": {
                                "field": {
                                    "type": "string",
                                    "enum": ["product_name"],
                                    "description": "属性编码，固定为 `product_name`（产品名称）",
                                },
                                "op": {
                                    "type": "string",
                                    "enum": ["eq", "like", "in", "is_null", "is_not_null"],
                                    "description": "过滤操作符",
                                },
                                "value": {
                                    "oneOf": [
                                        {"type": "string"},
                                        {"type": "array", "items": {"type": "string"}},
                                    ],
                                    "description": "eq/in 填字符串或数组；is_null/is_not_null 不需要",
                                },
                            },
                            "required": ["field", "op"],
                        },
                        {
                            "type": "object",
                            "description": "产品价格（product_price）过滤条件",
                            "properties": {
                                "field": {
                                    "type": "string",
                                    "enum": ["product_price"],
                                    "description": "属性编码，固定为 `product_price`（产品价格）",
                                },
                                "op": {
                                    "type": "string",
                                    "enum": ["eq", "gte", "lte", "is_null", "is_not_null"],
                                    "description": "过滤操作符",
                                },
                                "value": {"type": "number", "description": "数值"},
                            },
                            "required": ["field", "op"],
                        },
                    ]
                },
            },
            "filter_relation": {
                "type": "string",
                "enum": ["AND", "OR"],
                "default": "AND",
                "description": "过滤条件连接方式",
            },
        },
        "required": ["values", "filters"],
    }
    original_schema = deepcopy(schema)
    action = _Action(
        action_code="update_product",
        action_name="修改产品",
        action_family="update",
        input_schema=schema,
    )

    form = build_operation_form(
        action,
        {
            "values": {"product_price": 7000},
            "filters": [
                {"field": "product_name", "op": "eq", "value": "iPhone 15"},
                {"field": "product_name", "op": "in", "value": ["iPhone 15", "iPhone 16"]},
                {"field": "product_price", "op": "is_null"},
            ],
            "filter_relation": "AND",
        },
    )

    assert schema == original_schema
    fields = form["rule"][0]
    values_field = next(field for field in fields if field["fieldCode"] == "values")
    filters_field = next(field for field in fields if field["fieldCode"] == "filters")
    relation_field = next(field for field in fields if field["fieldCode"] == "filter_relation")
    assert values_field["fieldType"] == "object"
    assert values_field["formType"] == "object"
    assert values_field["fieldName"] == "修改字段"
    assert filters_field["fieldType"] == "array<object>"
    assert filters_field["formType"] == "array"
    assert filters_field["fieldName"] == "过滤条件"
    assert relation_field["fieldName"] == "过滤条件连接方式"
    assert "fieldValue" not in filters_field
    assert filters_field["filterOptions"] == [
        {
            "fieldCode": "product_name",
            "fieldName": "产品名称",
            "operators": ["eq", "like", "in", "is_null", "is_not_null"],
        },
        {
            "fieldCode": "product_price",
            "fieldName": "产品价格",
            "operators": ["eq", "gte", "lte", "is_null", "is_not_null"],
        },
    ]
    eq_filter_row = filters_field["children"][0]
    in_filter_row = filters_field["children"][1]
    null_filter_row = filters_field["children"][2]
    values_row = values_field["children"][0]
    price_field = next(field for field in values_row if field["fieldCode"] == "product_price")
    assert price_field["fieldType"] == "number"
    assert price_field["formType"] == "number"
    assert [field["fieldCode"] for field in eq_filter_row] == [
        "field",
        "op",
        "value",
    ]
    assert eq_filter_row[0]["fieldValue"] == "product_name"
    assert eq_filter_row[0]["fieldName"] == "字段"
    assert eq_filter_row[0]["optional"] == ["product_name"]
    assert eq_filter_row[0]["formType"] == "select"
    assert eq_filter_row[0]["readonly"] is True
    assert eq_filter_row[1]["fieldValue"] == "eq"
    assert eq_filter_row[1]["fieldName"] == "操作符"
    assert eq_filter_row[1]["optional"] == ["eq", "like", "in", "is_null", "is_not_null"]
    assert eq_filter_row[1]["formType"] == "select"
    assert eq_filter_row[1]["readonly"] is True
    assert eq_filter_row[2]["fieldValue"] == "iPhone 15"
    assert eq_filter_row[2]["fieldName"] == "过滤值"
    assert eq_filter_row[2]["fieldType"] == "string"
    assert in_filter_row[2]["fieldValue"] == ["iPhone 15", "iPhone 16"]
    assert in_filter_row[2]["fieldType"] == "array<string>"
    assert in_filter_row[2]["formType"] == "input"
    assert [field["fieldCode"] for field in null_filter_row] == ["field", "op"]
    assert relation_field["optional"] == ["AND", "OR"]
    assert relation_field["formType"] == "select"

    params = restore_action_params(form["rule"], action=action)
    assert params == {
        "values": {
            "product_name": None,
            "product_price": 7000,
            "category": None,
        },
        "filters": [
            {"field": "product_name", "op": "eq", "value": "iPhone 15"},
            {"field": "product_name", "op": "in", "value": ["iPhone 15", "iPhone 16"]},
            {"field": "product_price", "op": "is_null"},
        ],
        "filter_relation": "AND",
    }


def test_restore_action_params_uses_field_path_for_wrapper_values() -> None:
    rule = [
        [
            {
                "itemId": "item-1",
                "fieldCode": "taskName",
                "fieldPath": "requestBody.taskName",
                "fieldType": "string",
                "fieldValue": "研发任务",
            },
            {
                "fieldCode": "files",
                "fieldPath": "requestBody.files",
                "fieldType": "array",
                "children": [
                    [
                        {
                            "itemId": "file-1",
                            "fieldCode": "fileName",
                            "fieldPath": "requestBody.files.fileName",
                            "fieldType": "string",
                            "fieldValue": "需求文档.docx",
                        },
                        {
                            "fieldCode": "filePath",
                            "fieldPath": "requestBody.files.filePath",
                            "fieldType": "string",
                            "fieldValue": "/tmp/需求文档.docx",
                        },
                    ]
                ],
            },
        ]
    ]

    params = restore_action_params(rule)

    assert params == {
        "requestBody": {
            "taskName": "研发任务",
            "files": [{"fileName": "需求文档.docx", "filePath": "/tmp/需求文档.docx"}],
        }
    }
