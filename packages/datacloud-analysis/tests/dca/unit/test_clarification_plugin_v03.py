"""TC-V03: query_clarification_plugin V0.3 行为验收（阶段 2 红阶段）。

验收目标：
- ClarificationNeededError 类存在且可 import
- NEED_CONFIRM 路径 → 抛 ClarificationNeededError（不再调用 interrupt）
- 早返回路径：state 中有 clarification_formatted_params → 直接返回 patch/redirect decision
- TC-2-3 等效：is_complex=True 且命中早返回 → redirect decision
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    ClarificationNeededError,
    before_call_back,
)

# ── 辅助 ──────────────────────────────────────────────────────────────────────

TOOL = "query_ads_enterprise"
QUERY = "查询高营收的企业"

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
        "tool_params": {**(params or {"select": ["营收"], "filters": []}), "query": query},
        "user_query": query,
        "metadata": {"loader": loader, "state": state or {}},
        "session_id": "test-sess",
        "knowledge_snippets": [],
        "term_context": [],
        "knowledge_payload": {},
    }


# ── TC-V03-1: ClarificationNeededError 可 import ─────────────────────────────


def test_clarification_needed_error_importable() -> None:
    """ClarificationNeededError 类存在且可 import。"""
    err = ClarificationNeededError({"tool_name": TOOL})
    assert isinstance(err, Exception)
    assert err.context["tool_name"] == TOOL


# ── TC-V03-2: NEED_CONFIRM → ClarificationNeededError ─────────────────────────


async def test_need_confirm_raises_clarification_needed_error() -> None:
    """NEED_CONFIRM 路径（paradigm_list 非空）→ 抛 ClarificationNeededError，不调用 interrupt。"""
    ctx = _make_ctx()

    with (
        # catalog 非空 + unresolved 术语 → 进入 NEED_CONFIRM 分支
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._get_field_catalog",
            return_value={"total_revenue": "total_revenue"},
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._resolve_terms",
            return_value=({}, ["营收"]),  # resolved={}, unresolved=["营收"] → NEED_CONFIRM
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._analyze_clarification",
            return_value=(_PARADIGM_LIST, "知识"),
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


# ── TC-V03-3: 早返回路径 — clarification_formatted_params 已在 state ───────────


async def test_early_return_when_formatted_params_in_state() -> None:
    """早返回路径：state 中有 clarification_formatted_params 且 tool_name 匹配 → 返回 decision。"""
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

    assert decision is not None, "早返回路径应返回 HookDecision，不应返回 None"
    # 非 complex → patch 决策
    assert decision.get("action") in ("patch", "redirect"), f"非预期 action: {decision}"


# ── TC-V03-4: 早返回 is_complex=True → redirect ───────────────────────────────


async def test_early_return_is_complex_true_returns_redirect() -> None:
    """TC-V03-4: is_complex=True 且命中早返回 → redirect decision。"""
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
        f"is_complex=True 应返回 redirect，实际: {decision}"
    )
