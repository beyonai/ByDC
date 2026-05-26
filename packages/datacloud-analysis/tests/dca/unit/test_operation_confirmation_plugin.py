from __future__ import annotations

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
    assert files_field["fieldType"] == "array"
    assert "fieldValue" not in files_field
    assert files_field["fieldPath"] == "requestBody.files"
    assert [field["fieldCode"] for field in files_field["children"][0]] == [
        "fileName",
        "filePath",
    ]
    assert files_field["children"][0][0]["fieldValue"] == "需求文档.docx"


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
