from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from datacloud_analysis.tool_hook_plugins.builtin.operation_confirmation_plugin import (
    before_call_back,
    build_batch_operation_form,
    build_operation_form,
    restore_action_params,
)
from datacloud_analysis.tool_hook_plugins.types import ClarificationNeededError, HookContext
from datacloud_data_sdk.executor.kb_cascade_delete.models import (
    CascadeDeleteContext,
    CascadeDeleteItem,
    CascadeDeleteRoot,
)
from datacloud_data_sdk.ontology.term_loader import KbTermLoader
from datacloud_platform.errors import TermAmbiguousError, TermNotFoundError


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
    def __init__(self, action: _Action, term_loader: Any | None = None) -> None:
        self._config = SimpleNamespace(term_loader=term_loader)
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


class _AmbiguousTermLoader:
    def resolve_value(self, *_args: Any, **_kwargs: Any) -> str:
        raise TermAmbiguousError(
            "customer_status.code",
            "张三",
            [
                {"code": "U001", "label": "张三-研发"},
                {"code": "U002", "label": "张三-销售"},
            ],
        )


class _MissingTermLoader:
    def resolve_value(self, *_args: Any, **_kwargs: Any) -> str:
        raise TermNotFoundError("customer_status.code", "不存在的值", available_entries=[])

    def get_entries_page(self, *_args: Any, **_kwargs: Any) -> tuple[list[dict[str, str]], int]:
        return [], 0


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
    action_form = context["operation_form_action"]
    assert action_form["toolCallId"] == ""
    assert action_form["toolName"] == "insert_customer"
    assert "tool_call_id" not in action_form
    assert "tool_name" not in action_form
    status_field = form["rule"][0][1]
    assert status_field["formType"] == "term_select"
    assert status_field["term"]["termSet"] == "customer_status.code"


async def test_delete_kb_interrupt_adds_cascade_form_and_trusted_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = _Action(
        action_code="delete_kb_product",
        action_name="删除产品",
        action_family="delete_kb",
        input_schema={
            "type": "object",
            "properties": {
                "source_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
        },
    )
    action.scope_code = "product"  # type: ignore[attr-defined]
    cascade_context = CascadeDeleteContext.create(
        roots=[CascadeDeleteRoot("product", "/product/a.md", "p1", "fp-root")],
        items=[
            CascadeDeleteItem(
                item_id="cascade-item-1",
                parent_item_id=None,
                depth=1,
                object_code="feature",
                object_name="产品特性",
                source_path="/feature/1.md",
                term_id="f1",
                relation_id="r1",
                relation_code="feature_belongs_to_product",
                owner_term_id="p1",
                file_fingerprint="fp-feature",
            )
        ],
    )

    async def _discover(**_kwargs: Any) -> CascadeDeleteContext:
        from datacloud_data_sdk.context import get_current_context

        request_context = get_current_context()
        assert request_context.user_id == "user-1"
        assert request_context.session_id == "session-1"
        assert request_context.token == "token-1"
        assert request_context.language == "en_US"
        assert request_context.extras == {"request": "cascade-delete"}
        return cascade_context

    monkeypatch.setattr(
        "datacloud_analysis.tool_hook_plugins.builtin.operation_confirmation_plugin."
        "discover_cascade_context",
        _discover,
    )
    ctx: HookContext = {
        "tool_call_id": "call-1",
        "tool_name": "delete_kb_product",
        "tool_params": {"source_paths": ["/product/a.md"]},
        "metadata": {
            "loader": _Loader(action),
            "state": {},
            "gateway_context": SimpleNamespace(
                user_id="user-1",
                session_id="session-1",
                beyond_token="token-1",
                extras={"gateway": "fallback"},
            ),
            "configurable": {
                "locale": "en_US",
                "extras": {"request": "cascade-delete"},
            },
        },
    }

    with pytest.raises(ClarificationNeededError) as exc_info:
        await before_call_back(ctx)

    context = exc_info.value.context
    assert context["operation_form_action"]["formMode"] == "cascade_delete"
    assert context["cascade_context"]["items"][0]["termId"] == "f1"
    assert "termId" not in str(context["operation_form_action"])

    from datacloud_data_sdk.context import get_current_context
    from datacloud_data_sdk.exceptions import DatacloudError

    with pytest.raises(DatacloudError, match="InvocationContext"):
        get_current_context()


def test_operation_form_uses_locale_for_visible_text() -> None:
    action = _Action()

    form = build_operation_form(
        action,
        {"records": [{"customerId": "C001", "status": "TODO"}]},
        locale="en_US",
    )
    batch_form = build_batch_operation_form(
        [
            {
                "operation_form_action": {
                    "toolCallId": "call-1",
                    "toolName": "insert_customer",
                    "actionCode": "insert_customer",
                    "actionName": "Add customer",
                    "title": "Confirm execution: Add customer",
                    "description": "Please confirm the form below.",
                    "rule": [],
                }
            },
            {
                "operation_form_action": {
                    "toolCallId": "call-2",
                    "toolName": "insert_customer",
                    "actionCode": "insert_customer",
                    "actionName": "Add customer",
                    "title": "Confirm execution: Add customer",
                    "description": "Please confirm the form below.",
                    "rule": [],
                }
            },
        ],
        locale="en_US",
    )

    assert form["title"] == "Confirm execution: 新增客户"
    assert form["description"] == (
        "Please confirm the form below. Execution will continue after confirmation."
    )
    assert batch_form["title"] == "Confirm 2 operations"
    assert batch_form["description"] == (
        "Please confirm the form below. Execution will continue after confirmation."
    )


async def test_operation_form_keeps_unique_term_value_without_notice() -> None:
    action = _Action()
    term_loader = KbTermLoader.from_config(
        {
            "mapping": {
                "customer_status.code": [
                    {"code": "TODO", "label": "待处理", "aliases": ["待办"]},
                    {"code": "DONE", "label": "已完成"},
                ]
            }
        }
    )
    ctx: HookContext = {
        "tool_name": "insert_customer",
        "tool_params": {
            "records": [{"customerId": "C001", "status": "待处理"}],
        },
        "metadata": {"loader": _Loader(action, term_loader=term_loader), "state": {}},
    }

    with pytest.raises(ClarificationNeededError) as exc_info:
        await before_call_back(ctx)

    status_field = exc_info.value.context["operation_form_action"]["rule"][0][1]
    assert status_field["fieldValue"] == "待处理"
    assert "termResolveNotice" not in status_field


async def test_operation_form_recommends_first_term_when_value_not_found() -> None:
    action = _Action()
    term_loader = KbTermLoader.from_config(
        {
            "mapping": {
                "customer_status.code": [
                    {"code": "TODO", "label": "待处理"},
                    {"code": "DONE", "label": "已完成"},
                ]
            }
        }
    )
    ctx: HookContext = {
        "tool_name": "insert_customer",
        "tool_params": {
            "records": [{"customerId": "C001", "status": "待办中"}],
        },
        "metadata": {"loader": _Loader(action, term_loader=term_loader), "state": {}},
    }

    with pytest.raises(ClarificationNeededError) as exc_info:
        await before_call_back(ctx)

    status_field = exc_info.value.context["operation_form_action"]["rule"][0][1]
    assert status_field["fieldValue"] == "TODO"
    notice = status_field["termResolveNotice"]
    assert notice["status"] == "recommended"
    assert notice["originalValue"] == "待办中"
    assert notice["recommendedValue"] == "TODO"
    assert notice["recommendedLabel"] == "待处理"


async def test_operation_form_uses_locale_for_term_notice() -> None:
    action = _Action()
    term_loader = KbTermLoader.from_config(
        {
            "mapping": {
                "customer_status.code": [
                    {"code": "TODO", "label": "To do"},
                    {"code": "DONE", "label": "Done"},
                ]
            }
        }
    )
    ctx: HookContext = {
        "tool_name": "insert_customer",
        "tool_params": {
            "records": [{"customerId": "C001", "status": "todo-ish"}],
        },
        "metadata": {
            "loader": _Loader(action, term_loader=term_loader),
            "state": {},
            "configurable": {"locale": "en_US"},
        },
    }

    with pytest.raises(ClarificationNeededError) as exc_info:
        await before_call_back(ctx)

    status_field = exc_info.value.context["operation_form_action"]["rule"][0][1]
    notice = status_field["termResolveNotice"]
    assert status_field["fieldValue"] == "TODO"
    assert notice["message"] == (
        'The model recognized "todo-ish" but did not find an exact match. '
        '"To do" (code: TODO) is recommended. Please confirm or choose again.'
    )


async def test_operation_form_defaults_first_value_when_term_is_ambiguous() -> None:
    action = _Action()
    ctx: HookContext = {
        "tool_name": "insert_customer",
        "tool_params": {
            "records": [{"customerId": "C001", "status": "张三"}],
        },
        "metadata": {"loader": _Loader(action, term_loader=_AmbiguousTermLoader()), "state": {}},
    }

    with pytest.raises(ClarificationNeededError) as exc_info:
        await before_call_back(ctx)

    status_field = exc_info.value.context["operation_form_action"]["rule"][0][1]
    assert status_field["fieldValue"] == "U001"
    notice = status_field["termResolveNotice"]
    assert notice["status"] == "ambiguous_recommended"
    assert notice["originalValue"] == "张三"
    assert notice["recommendedValue"] == "U001"
    assert notice["recommendedLabel"] == "张三-研发"
    assert notice["candidates"] == [
        {"value": "U001", "label": "张三-研发"},
        {"value": "U002", "label": "张三-销售"},
    ]
    assert "请确认或重新选择" in notice["message"]


async def test_operation_form_clears_value_when_term_has_no_recommendation() -> None:
    action = _Action()
    ctx: HookContext = {
        "tool_name": "insert_customer",
        "tool_params": {
            "records": [{"customerId": "C001", "status": "不存在的值"}],
        },
        "metadata": {"loader": _Loader(action, term_loader=_MissingTermLoader()), "state": {}},
    }

    with pytest.raises(ClarificationNeededError) as exc_info:
        await before_call_back(ctx)

    status_field = exc_info.value.context["operation_form_action"]["rule"][0][1]
    assert status_field["fieldValue"] is None
    notice = status_field["termResolveNotice"]
    assert notice["status"] == "not_found"
    assert notice["originalValue"] == "不存在的值"
    assert notice["recommendedValue"] == ""
    assert notice["recommendedLabel"] == ""
    assert "请重新选择" in notice["message"]


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


async def test_operation_before_call_does_not_apply_batch_result_to_unknown_call_id() -> None:
    action = _Action()
    ctx: HookContext = {
        "tool_call_id": "call_2",
        "tool_name": "insert_customer",
        "tool_params": {"records": [{"customerId": "old"}]},
        "metadata": {
            "loader": _Loader(action),
            "state": {
                "clarification_formatted_params": {
                    "interrupt_type": "operation_form",
                    "formId": "form-1",
                    "tool_name": "insert_customer",
                    "confirmed": True,
                    "params_by_tool_call_id": {
                        "call_1": {
                            "tool_call_id": "call_1",
                            "tool_name": "insert_customer",
                            "confirmed": True,
                            "params": {"records": [{"customerId": "C001"}]},
                        }
                    },
                    "actions": [
                        {
                            "tool_call_id": "call_1",
                            "tool_name": "insert_customer",
                            "confirmed": True,
                            "params": {"records": [{"customerId": "C001"}]},
                        }
                    ],
                }
            },
        },
    }

    with pytest.raises(ClarificationNeededError):
        await before_call_back(ctx)


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
            "写入会议纪要知识库文档。支持 records 批量写入；content 必须提供完整正文，"
            "不得摘要、截断、删减或改写。"
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
            "records": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
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
                },
                "description": "待写入文档列表；批量写入时优先使用 records。",
            },
        },
        "anyOf": [{"required": ["source_path", "content"]}, {"required": ["records"]}],
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
    assert "records" not in {field["fieldCode"] for field in fields}
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


def test_build_operation_form_supports_kb_write_batch_records() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "x-dc-action-family": "write",
        "x-dc-scope-type": "object",
        "properties": {
            "source_path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "正文内容"},
            "records": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "labels": {
                            "type": "object",
                            "additionalProperties": False,
                            "description": "知识库属性标签，键必须是对象属性编码；主键字段不在此处填写。",
                            "properties": {
                                "status": {"type": "string", "description": "状态"},
                            },
                        },
                        "source_path": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "正文内容"},
                        "file_description": {"type": "string", "description": "文件描述"},
                    },
                    "required": ["source_path", "content"],
                },
            },
        },
        "anyOf": [{"required": ["source_path", "content"]}, {"required": ["records"]}],
    }
    action = _Action(
        action_code="write_meeting_doc",
        action_name="写入会议纪要",
        action_family="write",
        input_schema=schema,
    )

    form = build_operation_form(
        action,
        {
            "records": [
                {
                    "labels": {"status": "active"},
                    "source_path": "/meeting/a.docx",
                    "content": "正文 A",
                },
                {
                    "labels": {"status": "archived"},
                    "source_path": "/meeting/b.docx",
                    "content": "正文 B",
                    "file_description": "第二份",
                },
            ]
        },
    )

    assert len(form["rule"]) == 2
    first_row = form["rule"][0]
    second_row = form["rule"][1]
    assert [field["fieldCode"] for field in first_row] == [
        "labels",
        "source_path",
        "content",
        "file_description",
    ]
    assert first_row[0]["children"][0][0]["fieldValue"] == "active"
    assert first_row[1]["fieldValue"] == "/meeting/a.docx"
    assert second_row[0]["children"][0][0]["fieldValue"] == "archived"
    assert second_row[3]["fieldValue"] == "第二份"

    assert restore_action_params(form["rule"], action=action, original_params={"records": []}) == {
        "records": [
            {
                "labels": {"status": "active"},
                "source_path": "/meeting/a.docx",
                "content": "正文 A",
                "file_description": None,
            },
            {
                "labels": {"status": "archived"},
                "source_path": "/meeting/b.docx",
                "content": "正文 B",
                "file_description": "第二份",
            },
        ]
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
