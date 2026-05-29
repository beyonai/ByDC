"""TC-2-2b/2-3b/2-8/2-10: user_clarify_node 单元测试（阶段 2 红阶段）。

验收目标：
- TC-2-2b: is_complex=False → clarification_formatted_params.is_complex=False
- TC-2-3b: is_complex=True  → clarification_formatted_params.is_complex=True
- TC-2-8: state 清理（pending_clarification_context / clarification_analyze_result → None）
- TC-2-10: resume_value 为空 → _format_clarification 接收空 form_str，不抛异常
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from datacloud_analysis.orchestration.clarification.user_clarify_node import (
    user_clarify_node,
)

# ── 辅助 ──────────────────────────────────────────────────────────────────────

_TOOL_NAME = "query_ads_enterprise"
_QUERY = "查询高营收企业"

_PARADIGM_LIST: list[dict[str, Any]] = [
    {
        "paradigmCode": "P001",
        "paradigmName": "营收",
        "candidates": [{"keyword": "total_revenue", "displayName": "企业总营收（万元）"}],
    }
]

_FORMATTED_PARAMS: dict[str, Any] = {
    "select": ["total_revenue"],
    "filters": [],
}


def _expected_form(paradigm_list: list[dict[str, Any]]) -> str:
    return json.dumps({"paradigmList": paradigm_list}, ensure_ascii=False)


def _make_state(
    *,
    is_complex: bool = False,
    resume_value: Any = None,
    paradigm_list: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "pending_clarification_context": {
            "tool_name": _TOOL_NAME,
            "query": _QUERY,
            "structured_input": {"select": ["营收"]},
            "is_compute": is_complex,
            "ontology_code": "ads_enterprise",
            "react_round_idx": 1,
        },
        "clarification_analyze_result": {
            "paradigm_list": paradigm_list if paradigm_list is not None else _PARADIGM_LIST,
            "clarify_knowledge": "知识",
            "is_complex": is_complex,
        },
        "messages": [
            {"type": "human", "content": resume_value or ""},
        ]
        if resume_value is not None
        else [],
    }


# ── TC-2-2b: is_complex=False ─────────────────────────────────────────────────

_INTERRUPT_PATCH = "datacloud_analysis.orchestration.clarification.user_clarify_node.interrupt"
_FINALIZE_PATCH = (
    "datacloud_analysis.orchestration.clarification.user_clarify_node.finalize_query_clarification"
)


async def test_tc2_2b_is_complex_false_in_formatted_params() -> None:
    """TC-2-2b: is_complex=False → clarification_formatted_params.is_complex=False。"""
    state = _make_state(is_complex=False)
    finalized = MagicMock()
    finalized.structured_input = _FORMATTED_PARAMS
    finalized.persisted_synonyms = None

    with (
        patch(_INTERRUPT_PATCH, return_value=None),
        patch(_FINALIZE_PATCH, return_value=finalized),
    ):
        result = await user_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    fp = result.get("clarification_formatted_params") or {}
    assert fp.get("is_complex") is False
    assert fp.get("tool_name") == _TOOL_NAME


# ── TC-2-3b: is_complex=True ──────────────────────────────────────────────────


async def test_tc2_3b_is_complex_true_in_formatted_params() -> None:
    """TC-2-3b: is_complex=True → clarification_formatted_params.is_complex=True。"""
    state = _make_state(is_complex=True)
    finalized = MagicMock()
    finalized.structured_input = _FORMATTED_PARAMS
    finalized.persisted_synonyms = None

    with (
        patch(_INTERRUPT_PATCH, return_value=None),
        patch(_FINALIZE_PATCH, return_value=finalized),
    ):
        result = await user_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    fp = result.get("clarification_formatted_params") or {}
    assert fp.get("is_complex") is True


# ── TC-2-8: state 清理 ────────────────────────────────────────────────────────


async def test_tc2_8_state_keys_cleared_after_format() -> None:
    """TC-2-8: 完成后 pending_clarification_context 清为 None；
    clarification_analyze_result 保留供 before_call_back 兜底读取。
    """
    state = _make_state()
    finalized = MagicMock()
    finalized.structured_input = _FORMATTED_PARAMS
    finalized.persisted_synonyms = None

    with (
        patch(_INTERRUPT_PATCH, return_value=None),
        patch(_FINALIZE_PATCH, return_value=finalized),
    ):
        result = await user_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    assert result.get("pending_clarification_context") is None, (
        "pending_clarification_context 应被清理"
    )
    # clarification_analyze_result 不再清空（before_call_back 兜底需要它）
    assert "clarification_analyze_result" not in result, (
        "clarification_analyze_result 不应被 user_clarify_node 写入（保留原值）"
    )


# ── TC-2-10: resume_value 为空 ────────────────────────────────────────────────


async def test_tc2_10_empty_resume_value_does_not_raise() -> None:
    """TC-2-10: resume_value 为空 → _format_clarification 接收空 form_str，不抛异常。"""
    state = _make_state(resume_value=None)
    finalized = MagicMock()
    finalized.structured_input = _FORMATTED_PARAMS
    finalized.persisted_synonyms = None

    with (
        patch(_INTERRUPT_PATCH, return_value=None),
        patch(_FINALIZE_PATCH, return_value=finalized),
    ):
        result = await user_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    assert result.get("clarification_formatted_params") is not None


async def test_gateway_user_id_controls_synonym_persistence() -> None:
    """有 gateway user_id 才持久化用户确认同义词；缺失时不降级。"""
    state = _make_state()
    resume_value = {"paradigmList": [{"paradigmList": _PARADIGM_LIST}]}
    config = {"configurable": {"gateway_context": SimpleNamespace(user_id="user-1")}}
    finalized = MagicMock()
    finalized.structured_input = _FORMATTED_PARAMS
    finalized.persisted_synonyms = MagicMock(created_ids=["name-1"])

    with (
        patch(_INTERRUPT_PATCH, return_value=resume_value),
        patch(_FINALIZE_PATCH, return_value=finalized) as mock_finalize,
    ):
        await user_clarify_node(state, config)  # type: ignore[arg-type]

    mock_finalize.assert_called_once_with(
        query="查询高营收企业",
        ontology_code="ads_enterprise",
        structured_input={"select": ["营收"]},
        mode="query",
        needs_clarification=True,
        form=_expected_form(_PARADIGM_LIST),
        metadata="知识",
        user_id="user-1",
        persist_confirmed_synonyms=True,
        language="zh_CN",
    )

    finalized.persisted_synonyms = None
    with (
        patch(_INTERRUPT_PATCH, return_value=resume_value),
        patch(_FINALIZE_PATCH, return_value=finalized) as mock_finalize_no_user,
    ):
        await user_clarify_node(state, {"configurable": {}})  # type: ignore[arg-type]

    mock_finalize_no_user.assert_called_once()


async def test_gateway_header_user_code_is_user_identity() -> None:
    """by-framework 网关通过 header.user_code 暴露用户身份。"""
    state = _make_state()
    resume_value = {"paradigmList": [{"paradigmList": _PARADIGM_LIST}]}
    config = {
        "configurable": {
            "gateway_context": SimpleNamespace(
                header=SimpleNamespace(user_code="adminvip"),
            )
        }
    }
    finalized = MagicMock()
    finalized.structured_input = _FORMATTED_PARAMS
    finalized.persisted_synonyms = MagicMock(created_ids=["name-1"])

    with (
        patch(_INTERRUPT_PATCH, return_value=resume_value),
        patch(_FINALIZE_PATCH, return_value=finalized) as mock_finalize,
    ):
        await user_clarify_node(state, config)  # type: ignore[arg-type]

    mock_finalize.assert_called_once_with(
        query="查询高营收企业",
        ontology_code="ads_enterprise",
        structured_input={"select": ["营收"]},
        mode="query",
        needs_clarification=True,
        form=_expected_form(_PARADIGM_LIST),
        metadata="知识",
        user_id="adminvip",
        persist_confirmed_synonyms=True,
        language="zh_CN",
    )


async def test_gateway_current_command_header_user_code_is_user_identity() -> None:
    """实际 byclaw 网关通过 current_command.header.user_code 暴露用户身份。"""
    state = _make_state()
    resume_value = {"paradigmList": [{"paradigmList": _PARADIGM_LIST}]}
    config = {
        "configurable": {
            "gateway_context": SimpleNamespace(
                current_command=SimpleNamespace(
                    header=SimpleNamespace(user_code="adminvip"),
                ),
            )
        }
    }
    finalized = MagicMock()
    finalized.structured_input = _FORMATTED_PARAMS
    finalized.persisted_synonyms = MagicMock(created_ids=["name-1"])

    with (
        patch(_INTERRUPT_PATCH, return_value=resume_value),
        patch(_FINALIZE_PATCH, return_value=finalized) as mock_finalize,
    ):
        await user_clarify_node(state, config)  # type: ignore[arg-type]

    mock_finalize.assert_called_once_with(
        query="查询高营收企业",
        ontology_code="ads_enterprise",
        structured_input={"select": ["营收"]},
        mode="query",
        needs_clarification=True,
        form=_expected_form(_PARADIGM_LIST),
        metadata="知识",
        user_id="adminvip",
        persist_confirmed_synonyms=True,
        language="zh_CN",
    )


async def test_operation_form_confirm_resume_writes_formatted_params() -> None:
    """操作表单确认后写入统一的 clarification_formatted_params。"""
    operation_form = {
        "formId": "form-1",
        "actionCode": "insert_customer",
        "rule": [
            [
                {
                    "itemId": "item-1",
                    "fieldCode": "customerId",
                    "fieldType": "string",
                    "fieldValue": "C001",
                }
            ]
        ],
    }
    state = {
        "pending_clarification_context": {},
        "clarification_analyze_result": {
            "interrupt_type": "operation_form",
            "tool_name": "insert_customer",
            "operation_form": operation_form,
            "structured_input": {},
        },
    }
    resume_value = {
        "formId": "form-1",
        "actions": [
            {
                "toolCallId": "",
                "toolName": "insert_customer",
                "rule": operation_form["rule"],
            }
        ],
    }

    with patch(_INTERRUPT_PATCH, return_value=resume_value):
        result = await user_clarify_node(state, {"configurable": {}})  # type: ignore[arg-type]

    fp = result["clarification_formatted_params"]
    assert fp["interrupt_type"] == "operation_form"
    assert fp["confirmed"] is True
    assert fp["params"]["customerId"] == "C001"
    assert fp["params"]["userConfirmed"] is True
    assert fp["actions"][0]["confirmed"] is True
    assert result["clarify_abort"] is False


async def test_operation_form_insert_resume_uses_context_action_family_for_records() -> None:
    """恢复阶段没有 loader 时，insert 也应根据中断上下文恢复为 records。"""
    operation_form = {
        "schemaVersion": "1.0",
        "formId": "form-1",
        "actions": [
            {
                "toolCallId": "call-1",
                "toolName": "insert_customer",
                "actionCode": "insert_customer",
                "rule": [
                    [
                        {
                            "itemId": "item-1",
                            "fieldCode": "customerId",
                            "fieldType": "string",
                            "fieldValue": "C001",
                        }
                    ]
                ],
            }
        ],
    }
    state = {
        "pending_clarification_context": {},
        "clarification_analyze_result": {
            "interrupt_type": "operation_form",
            "tool_name": "insert_customer",
            "operation_form": operation_form,
            "operation_form_contexts": [
                {
                    "tool_call_id": "call-1",
                    "tool_name": "insert_customer",
                    "structured_input": {},
                    "operation_confirm_context": {
                        "actionCode": "insert_customer",
                        "actionFamily": "insert",
                    },
                }
            ],
        },
    }
    resume_value = {
        "schemaVersion": "1.0",
        "formId": "form-1",
        "actions": [
            {
                "toolCallId": "call-1",
                "toolName": "insert_customer",
                "rule": operation_form["actions"][0]["rule"],
            }
        ],
    }

    with patch(_INTERRUPT_PATCH, return_value=resume_value):
        result = await user_clarify_node(state, {"configurable": {}})  # type: ignore[arg-type]

    params = result["clarification_formatted_params"]["params_by_tool_call_id"]["call-1"]["params"]
    assert params["records"] == [{"customerId": "C001"}]
    assert params["userConfirmed"] is True


async def test_operation_form_update_resume_without_loader_keeps_business_params() -> None:
    """恢复阶段没有 loader 时，非 records 类操作不能被薄 action meta 过滤空。"""
    operation_form = {
        "schemaVersion": "1.0",
        "formId": "form-1",
        "actions": [
            {
                "toolCallId": "call-1",
                "toolName": "update_customer",
                "actionCode": "update_customer",
                "rule": [
                    [
                        {
                            "itemId": "item-1",
                            "fieldCode": "customerId",
                            "fieldPath": "requestBody.customerId",
                            "fieldType": "string",
                            "fieldValue": "C001",
                        },
                        {
                            "fieldCode": "status",
                            "fieldPath": "requestBody.status",
                            "fieldType": "string",
                            "fieldValue": "active",
                        },
                    ]
                ],
            }
        ],
    }
    state = {
        "pending_clarification_context": {},
        "clarification_analyze_result": {
            "interrupt_type": "operation_form",
            "tool_name": "update_customer",
            "operation_form": operation_form,
            "operation_form_contexts": [
                {
                    "tool_call_id": "call-1",
                    "tool_name": "update_customer",
                    "structured_input": {"requestBody": {"customerId": "old"}},
                    "operation_confirm_context": {
                        "actionCode": "update_customer",
                        "actionFamily": "update",
                    },
                }
            ],
        },
    }
    resume_value = {
        "schemaVersion": "1.0",
        "formId": "form-1",
        "actions": [
            {
                "toolCallId": "call-1",
                "toolName": "update_customer",
                "rule": operation_form["actions"][0]["rule"],
            }
        ],
    }

    with patch(_INTERRUPT_PATCH, return_value=resume_value):
        result = await user_clarify_node(state, {"configurable": {}})  # type: ignore[arg-type]

    params = result["clarification_formatted_params"]["params_by_tool_call_id"]["call-1"]["params"]
    assert params["requestBody"] == {"customerId": "C001", "status": "active"}
    assert params["userConfirmed"] is True


async def test_operation_form_cancel_resume_aborts_execution() -> None:
    """操作表单取消后不再回到工具执行。"""
    operation_form = {"formId": "form-1", "actionCode": "delete_customer", "rule": [[]]}
    state = {
        "pending_clarification_context": {},
        "clarification_analyze_result": {
            "interrupt_type": "operation_form",
            "tool_name": "delete_customer",
            "operation_form": operation_form,
        },
    }
    resume_value = {
        "formId": "form-1",
        "actions": [
            {
                "toolCallId": "",
                "toolName": "delete_customer",
                "confirmed": False,
                "reason": "用户取消",
                "rule": operation_form["rule"],
            }
        ],
    }

    with patch(_INTERRUPT_PATCH, return_value=resume_value):
        result = await user_clarify_node(state, {"configurable": {}})  # type: ignore[arg-type]

    fp = result["clarification_formatted_params"]
    assert fp["confirmed"] is False
    assert fp["reason"] == "用户取消"
    assert fp["actions"][0]["confirmed"] is False
    assert result["clarify_abort"] is False


async def test_operation_form_resume_defaults_returned_actions_to_confirmed() -> None:
    """前端返回完整 actions 但不带 confirmed 时，按同意执行处理。"""
    operation_form = {
        "schemaVersion": "1.0",
        "formId": "form-batch-1",
        "actions": [
            {
                "toolCallId": "call-1",
                "toolName": "insert_customer",
                "actionCode": "insert_customer",
                "rule": [
                    [{"fieldCode": "customerId", "fieldType": "string", "fieldValue": "C001"}]
                ],
            },
            {
                "toolCallId": "call-2",
                "toolName": "insert_customer",
                "actionCode": "insert_customer",
                "rule": [
                    [{"fieldCode": "customerId", "fieldType": "string", "fieldValue": "C002"}]
                ],
            },
        ],
    }
    state = {
        "pending_clarification_context": {},
        "clarification_analyze_result": {
            "interrupt_type": "operation_form",
            "tool_name": "insert_customer",
            "operation_form": operation_form,
        },
    }
    resume_value = {
        "schemaVersion": "1.0",
        "formId": "form-batch-1",
        "actions": [
            {
                "toolCallId": "call-1",
                "toolName": "insert_customer",
                "rule": [
                    [{"fieldCode": "customerId", "fieldType": "string", "fieldValue": "C101"}]
                ],
            },
            {
                "toolCallId": "call-2",
                "toolName": "insert_customer",
                "rule": [
                    [{"fieldCode": "customerId", "fieldType": "string", "fieldValue": "C102"}]
                ],
            },
        ],
    }

    with patch(_INTERRUPT_PATCH, return_value=resume_value):
        result = await user_clarify_node(state, {"configurable": {}})  # type: ignore[arg-type]

    actions = result["clarification_formatted_params"]["actions"]
    assert [action["confirmed"] for action in actions] == [True, True]
    assert actions[0]["params"]["customerId"] == "C101"
    assert actions[1]["params"]["customerId"] == "C102"
