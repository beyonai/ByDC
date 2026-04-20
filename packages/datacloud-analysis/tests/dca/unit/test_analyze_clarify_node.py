"""TC-2-2 ~ TC-2-9: analyze_clarify_node 单元测试（阶段 2 红阶段）。

验收目标：
- TC-2-2/2-3: paradigm_list 非空 → clarification_analyze_result 含 paradigm_list + clarify_knowledge
- TC-2-4/2-5: paradigm_list 为空 → pre_filled_params 由 _apply_resolved_to_params 生成
- TC-2-9: _analyze_clarification 抛异常 → 向上传播
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from datacloud_analysis.orchestration.clarification.analyze_clarify_node import (
    analyze_clarify_node,
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

_KNOWLEDGE = "营收字段映射信息"


def _make_state(
    tool_name: str = _TOOL_NAME,
    query: str = _QUERY,
    structured_input: dict[str, Any] | None = None,
    is_compute: bool = False,
    ontology_code: str = "ads_enterprise",
) -> dict[str, Any]:
    return {
        "pending_clarification_context": {
            "tool_name": tool_name,
            "query": query,
            "structured_input": structured_input or {"select": ["营收"]},
            "is_compute": is_compute,
            "ontology_code": ontology_code,
            "react_round_idx": 1,
        }
    }


# ── TC-2-2/2-3: paradigm_list 非空 → clarification_analyze_result 写入 ────────


async def test_tc2_2_paradigm_list_nonempty_writes_analyze_result() -> None:
    """TC-2-2: paradigm_list 非空 → clarification_analyze_result 含正确字段。"""
    state = _make_state()

    with patch(
        "datacloud_analysis.orchestration.clarification.analyze_clarify_node._analyze_clarification",
        return_value=(_PARADIGM_LIST, _KNOWLEDGE),
    ):
        result = await analyze_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    analyze_result = result.get("clarification_analyze_result") or {}
    assert analyze_result.get("paradigm_list") == _PARADIGM_LIST
    assert analyze_result.get("clarify_knowledge") == _KNOWLEDGE
    assert analyze_result.get("is_complex") is False


async def test_tc2_3_is_complex_true_propagated() -> None:
    """TC-2-3: is_compute=True 时 is_complex=True 写入 clarification_analyze_result。"""
    state = _make_state(is_compute=True)

    with patch(
        "datacloud_analysis.orchestration.clarification.analyze_clarify_node._analyze_clarification",
        return_value=(_PARADIGM_LIST, _KNOWLEDGE),
    ):
        result = await analyze_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    analyze_result = result.get("clarification_analyze_result") or {}
    assert analyze_result.get("is_complex") is True


# ── TC-2-4/2-5: paradigm_list 为空 → pre_filled_params ───────────────────────


async def test_tc2_4_empty_paradigm_list_generates_pre_filled_params() -> None:
    """TC-2-4: paradigm_list 为空 → pre_filled_params 由 _apply_resolved_to_params 生成。"""
    structured_input = {"select": ["total_revenue"], "filters": []}
    state = _make_state(structured_input=structured_input)

    with patch(
        "datacloud_analysis.orchestration.clarification.analyze_clarify_node._analyze_clarification",
        return_value=([], _KNOWLEDGE),
    ):
        result = await analyze_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    analyze_result = result.get("clarification_analyze_result") or {}
    assert analyze_result.get("paradigm_list") == []
    assert "pre_filled_params" in analyze_result, "空 paradigm_list 应生成 pre_filled_params"


async def test_tc2_5_empty_paradigm_list_analyze_result_has_knowledge() -> None:
    """TC-2-5: paradigm_list 为空时，clarify_knowledge 仍写入 clarification_analyze_result。"""
    state = _make_state()

    with patch(
        "datacloud_analysis.orchestration.clarification.analyze_clarify_node._analyze_clarification",
        return_value=([], "知识文本"),
    ):
        result = await analyze_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    analyze_result = result.get("clarification_analyze_result") or {}
    assert analyze_result.get("clarify_knowledge") == "知识文本"


# ── TC-2-9: 异常传播 ──────────────────────────────────────────────────────────


async def test_tc2_9_analyze_exception_propagates() -> None:
    """TC-2-9: _analyze_clarification 抛异常 → 向上传播（不吞异常）。"""
    state = _make_state()

    with (
        patch(
            "datacloud_analysis.orchestration.clarification.analyze_clarify_node._analyze_clarification",
            side_effect=RuntimeError("SDK error"),
        ),
        pytest.raises(RuntimeError, match="SDK error"),
    ):
        await analyze_clarify_node(state, MagicMock())  # type: ignore[arg-type]
