"""TC-V03: query_clarification_plugin V0.3 琛屼负楠屾敹锛堥樁娈?2 绾㈤樁娈碉級銆?
楠屾敹鐩爣锛?- ClarificationNeededError 绫诲瓨鍦ㄤ笖鍙?import
- NEED_CONFIRM 璺緞 鈫?鎶?ClarificationNeededError锛堜笉鍐嶈皟鐢?interrupt锛?- 鏃╄繑鍥炶矾寰勶細state 涓湁 clarification_formatted_params 鈫?鐩存帴杩斿洖 patch/redirect decision
- TC-2-3 绛夋晥锛歩s_complex=True 涓斿懡涓棭杩斿洖 鈫?redirect decision
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    ClarificationNeededError,
    before_call_back,
)

# 鈹€鈹€ 杈呭姪 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

TOOL = "query_ads_enterprise"
QUERY = "鏌ヨ楂樿惀鏀剁殑浼佷笟"

_PARADIGM_LIST = [
    {
        "paradigmCode": "P001",
        "paradigmName": "营收",
        "candidates": [{"keyword": "total_revenue", "displayName": "企业总营收（万元）"}],
    }
]


def _make_ctx(
    tool_name: str = TOOL,
    query: str = QUERY,
    params: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    loader: Any = None,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_params": {**(params or {"select": ["钀ユ敹"], "filters": []}), "query": query},
        "user_query": query,
        "metadata": {"loader": loader, "state": state or {}},
        "session_id": "test-sess",
        "knowledge_snippets": [],
        "term_context": [],
        "knowledge_payload": {},
    }


# 鈹€鈹€ TC-V03-1: ClarificationNeededError 鍙?import 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


def test_clarification_needed_error_importable() -> None:
    """ClarificationNeededError should be importable and carry context."""
    err = ClarificationNeededError({"tool_name": TOOL})
    assert isinstance(err, Exception)
    assert err.context["tool_name"] == TOOL


# 鈹€鈹€ TC-V03-2: NEED_CONFIRM 鈫?ClarificationNeededError 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


async def test_need_confirm_raises_clarification_needed_error() -> None:
    """NEED_CONFIRM path should raise ClarificationNeededError."""
    ctx = _make_ctx()

    with (
        # catalog 闈炵┖ + unresolved 鏈 鈫?杩涘叆 NEED_CONFIRM 鍒嗘敮
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._get_field_catalog",
            return_value={"total_revenue": "total_revenue"},
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._resolve_terms",
            return_value=({}, ["钀ユ敹"]),  # resolved={}, unresolved=["钀ユ敹"] 鈫?NEED_CONFIRM
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._analyze_clarification",
            return_value=(_PARADIGM_LIST, "鐭ヨ瘑", True),
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin.interrupt",
            side_effect=AssertionError("interrupt should not be called"),
        ),
        pytest.raises(ClarificationNeededError) as exc_info,
    ):
        await before_call_back(ctx)

    assert exc_info.value.context.get("tool_name") == TOOL
    assert "paradigm_list" in exc_info.value.context or "query" in exc_info.value.context


# 鈹€鈹€ TC-V03-3: 鏃╄繑鍥炶矾寰?鈥?clarification_formatted_params 宸插湪 state 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


async def test_early_return_when_formatted_params_in_state() -> None:
    """Should return a decision when formatted params already exist in state."""
    formatted = {
        "tool_name": TOOL,
        "is_complex": False,
        "params": {"select": ["total_revenue"], "filters": []},
    }
    state = {"clarification_formatted_params": formatted}
    ctx = _make_ctx(state=state)

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._analyze_clarification",
        side_effect=AssertionError("analyze should not be called on early return"),
    ):
        decision = await before_call_back(ctx)

    assert decision is not None, "鏃╄繑鍥炶矾寰勫簲杩斿洖 HookDecision锛屼笉搴旇繑鍥?None"
    # 闈?complex 鈫?patch 鍐崇瓥
    assert decision.get("action") in ("patch", "redirect"), f"闈為鏈?action: {decision}"


# 鈹€鈹€ TC-V03-4: 鏃╄繑鍥?is_complex=True 鈫?redirect 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


async def test_early_return_is_complex_true_returns_redirect() -> None:
    """TC-V03-4: early return with is_complex=True should redirect."""
    formatted = {
        "tool_name": TOOL,
        "is_complex": True,
        "params": {"select": ["total_revenue"], "filters": []},
    }
    state = {"clarification_formatted_params": formatted}
    ctx = _make_ctx(state=state)

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._analyze_clarification",
        side_effect=AssertionError("analyze should not be called"),
    ):
        decision = await before_call_back(ctx)

    assert decision is not None
    assert decision.get("action") == "redirect", (
        f"is_complex=True 搴旇繑鍥?redirect锛屽疄闄? {decision}"
    )
