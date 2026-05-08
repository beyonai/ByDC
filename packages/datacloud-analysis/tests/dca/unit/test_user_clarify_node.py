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
    )
