"""T2：user_clarify_node 直接读取 configurable["user_code"] 兼容测试（红阶段）。

验收目标：
- TC-T2-1: configurable 中有 user_code 且无 gateway_context 时，user_id 取 user_code 值
- TC-T2-2: configurable 中有 gateway_context 时，沿用现有路径（user_code 不影响）
- TC-T2-3: 两者都没有时 user_id 为 None，persist_confirmed_synonyms 不被调用
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from datacloud_analysis.orchestration.clarification.user_clarify_node import (
    user_clarify_node,
)

# ── patch 路径 ────────────────────────────────────────────────────────────────
_INTERRUPT_PATCH = "datacloud_analysis.orchestration.clarification.user_clarify_node.interrupt"
_FINALIZE_PATCH = (
    "datacloud_analysis.orchestration.clarification.user_clarify_node.finalize_query_clarification"
)

_TOOL_NAME = "query_ads_enterprise"
_QUERY = "查询高营收企业"

_PARADIGM_LIST: list[dict[str, Any]] = [
    {
        "paradigmCode": "P001",
        "paradigmName": "营收",
        "paradigmResult": [{"choiceKeyword": "总营收", "recall": "total_revenue"}],
    }
]

_FORMATTED_PARAMS: dict[str, Any] = {"select": ["total_revenue"], "filters": []}

_RESUME_VALUE: dict[str, Any] = {
    "paradigmList": [{"paradigmList": [{"choiceKeyword": "总营收", "recall": "total_revenue"}]}]
}


def _make_state(paradigm_list: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "pending_clarification_context": {
            "tool_name": _TOOL_NAME,
            "query": _QUERY,
            "structured_input": {"select": ["营收"]},
            "is_compute": False,
        },
        "clarification_analyze_result": {
            "paradigm_list": paradigm_list if paradigm_list is not None else _PARADIGM_LIST,
            "clarify_knowledge": "知识",
        },
        "messages": [],
    }


# ── TC-T2-1: configurable["user_code"] 被使用（无 gateway_context） ────────────


async def test_user_code_from_configurable_used_when_no_gateway_context() -> None:
    """user_code 直接在 configurable 中时，persist_confirmed_synonyms 以该 user_code 调用。"""
    config: dict[str, Any] = {
        "configurable": {
            "thread_id": "test-thread",
            "user_code": "direct_user_001",
            # 无 gateway_context
        }
    }
    finalized = MagicMock()
    finalized.structured_input = _FORMATTED_PARAMS
    finalized.persisted_synonyms = MagicMock(created_ids=[])

    with (
        patch(_INTERRUPT_PATCH, return_value=_RESUME_VALUE),
        patch(_FINALIZE_PATCH, return_value=finalized) as mock_finalize,
    ):
        result = await user_clarify_node(_make_state(), config)  # type: ignore[arg-type]

    mock_finalize.assert_called_once()
    assert mock_finalize.call_args.kwargs.get("user_id") == "direct_user_001"
    assert result.get("clarification_formatted_params") is not None


# ── TC-T2-2: gateway_context 存在时仍走原有路径 ──────────────────────────────


async def test_gateway_context_takes_priority_over_direct_user_code() -> None:
    """gateway_context 存在时，get_gateway_user_id 路径不受 user_code 干扰。"""
    mock_ctx = MagicMock()
    mock_ctx.user_id = "gw_user_001"

    config: dict[str, Any] = {
        "configurable": {
            "thread_id": "test-thread",
            "gateway_context": mock_ctx,
            "user_code": "should_not_be_used",
        }
    }
    finalized = MagicMock()
    finalized.structured_input = _FORMATTED_PARAMS
    finalized.persisted_synonyms = MagicMock(created_ids=[])

    with (
        patch(_INTERRUPT_PATCH, return_value=_RESUME_VALUE),
        patch(_FINALIZE_PATCH, return_value=finalized) as mock_finalize,
        patch(
            "datacloud_analysis.orchestration.clarification.user_clarify_node.get_gateway_user_id",
            return_value="gw_user_001",
        ),
    ):
        await user_clarify_node(_make_state(), config)  # type: ignore[arg-type]

    mock_finalize.assert_called_once()
    assert mock_finalize.call_args.kwargs.get("user_id") == "gw_user_001"


# ── TC-T2-3: 两者都没有时 persist 不被调用 ────────────────────────────────────


async def test_no_user_id_skips_persistence() -> None:
    """user_code 和 gateway_context 都不存在时，persist_confirmed_synonyms 不被调用。"""
    config: dict[str, Any] = {
        "configurable": {
            "thread_id": "test-thread",
            # 无 gateway_context, 无 user_code
        }
    }
    finalized = MagicMock()
    finalized.structured_input = _FORMATTED_PARAMS
    finalized.persisted_synonyms = None

    with (
        patch(_INTERRUPT_PATCH, return_value=_RESUME_VALUE),
        patch(_FINALIZE_PATCH, return_value=finalized) as mock_finalize,
    ):
        result = await user_clarify_node(_make_state(), config)  # type: ignore[arg-type]

    mock_finalize.assert_called_once()
    assert mock_finalize.call_args.kwargs.get("user_id") is None
    assert result.get("clarification_formatted_params") is not None
