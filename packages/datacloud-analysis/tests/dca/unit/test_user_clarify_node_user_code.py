"""T2：user_clarify_node 直接读取 configurable["user_code"] 兼容测试（红阶段）。

验收目标：
- TC-T2-1: configurable 中有 user_code 且无 gateway_context 时，user_id 取 user_code 值
- TC-T2-2: configurable 中有 gateway_context 时，沿用现有路径（user_code 不影响）
- TC-T2-3: 两者都没有时 user_id 为 None，persist_confirmed_synonyms 不被调用
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from datacloud_analysis.orchestration.clarification.user_clarify_node import (
    user_clarify_node,
)

# ── patch 路径 ────────────────────────────────────────────────────────────────
_INTERRUPT_PATCH = "datacloud_analysis.orchestration.clarification.user_clarify_node.interrupt"
_FORMAT_PATCH = "datacloud_analysis.orchestration.clarification.user_clarify_node._format_clarification"
_NORMALIZE_PATCH = "datacloud_analysis.orchestration.clarification.user_clarify_node.normalize_clarification_params"
_PERSIST_PATCH = "datacloud_analysis.orchestration.clarification.user_clarify_node.persist_confirmed_synonyms"

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

    with (
        patch(_INTERRUPT_PATCH, return_value=_RESUME_VALUE),
        patch(_FORMAT_PATCH, return_value=_FORMATTED_PARAMS),
        patch(_NORMALIZE_PATCH, side_effect=lambda p, **_kw: p),
        patch(_PERSIST_PATCH, return_value=[]) as mock_persist,
    ):
        result = await user_clarify_node(_make_state(), config)  # type: ignore[arg-type]

    mock_persist.assert_called_once()
    call_kwargs = mock_persist.call_args.kwargs
    assert call_kwargs.get("user_id") == "direct_user_001" or (
        # 也接受 positional 传参
        len(mock_persist.call_args.args) >= 3
        and mock_persist.call_args.args[2] == "direct_user_001"
    )
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

    with (
        patch(_INTERRUPT_PATCH, return_value=_RESUME_VALUE),
        patch(_FORMAT_PATCH, return_value=_FORMATTED_PARAMS),
        patch(_NORMALIZE_PATCH, side_effect=lambda p, **_kw: p),
        patch(_PERSIST_PATCH, return_value=[]) as mock_persist,
        patch(
            "datacloud_analysis.orchestration.clarification.user_clarify_node.get_gateway_user_id",
            return_value="gw_user_001",
        ),
    ):
        result = await user_clarify_node(_make_state(), config)  # type: ignore[arg-type]

    mock_persist.assert_called_once()
    _, kwargs = mock_persist.call_args
    # 应使用 gateway_context 中的 user_id，不是 direct user_code
    assert kwargs.get("user_id") == "gw_user_001"


# ── TC-T2-3: 两者都没有时 persist 不被调用 ────────────────────────────────────

async def test_no_user_id_skips_persistence() -> None:
    """user_code 和 gateway_context 都不存在时，persist_confirmed_synonyms 不被调用。"""
    config: dict[str, Any] = {
        "configurable": {
            "thread_id": "test-thread",
            # 无 gateway_context, 无 user_code
        }
    }

    with (
        patch(_INTERRUPT_PATCH, return_value=_RESUME_VALUE),
        patch(_FORMAT_PATCH, return_value=_FORMATTED_PARAMS),
        patch(_NORMALIZE_PATCH, side_effect=lambda p, **_kw: p),
        patch(_PERSIST_PATCH, return_value=[]) as mock_persist,
    ):
        result = await user_clarify_node(_make_state(), config)  # type: ignore[arg-type]

    mock_persist.assert_not_called()
    assert result.get("clarification_formatted_params") is not None
