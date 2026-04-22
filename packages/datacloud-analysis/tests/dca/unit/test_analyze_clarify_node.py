"""TC-2-2 ~ TC-2-9: analyze_clarify_node 鍗曞厓娴嬭瘯锛堥樁娈?2 绾㈤樁娈碉級銆?
楠屾敹鐩爣锛?- TC-2-2/2-3: paradigm_list 闈炵┖ 鈫?clarification_analyze_result 鍚?paradigm_list + clarify_knowledge
- TC-2-4/2-5: paradigm_list 涓虹┖ 鈫?pre_filled_params 鐢?_apply_resolved_to_params 鐢熸垚
- TC-2-9: _analyze_clarification 鎶涘紓甯?鈫?鍚戜笂浼犳挱
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from datacloud_analysis.orchestration.clarification.analyze_clarify_node import (
    analyze_clarify_node,
)

# 鈹€鈹€ 杈呭姪 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

_TOOL_NAME = "query_ads_enterprise"
_QUERY = "查询高营收企业"

_PARADIGM_LIST: list[dict[str, Any]] = [
    {
        "paradigmCode": "P001",
        "paradigmName": "营收",
        "candidates": [{"keyword": "total_revenue", "displayName": "企业总营收（万元）"}],
    }
]

_KNOWLEDGE = "钀ユ敹瀛楁鏄犲皠淇℃伅"


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
            "structured_input": structured_input or {"select": ["钀ユ敹"]},
            "is_compute": is_compute,
            "ontology_code": ontology_code,
            "react_round_idx": 1,
        }
    }


# 鈹€鈹€ TC-2-2/2-3: paradigm_list 闈炵┖ 鈫?clarification_analyze_result 鍐欏叆 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


async def test_tc2_2_paradigm_list_nonempty_writes_analyze_result() -> None:
    """TC-2-2: non-empty paradigm_list should be written to analyze result."""
    state = _make_state()

    with patch(
        "datacloud_analysis.orchestration.clarification.analyze_clarify_node._analyze_clarification",
        return_value=(_PARADIGM_LIST, _KNOWLEDGE, True),
    ):
        result = await analyze_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    analyze_result = result.get("clarification_analyze_result") or {}
    assert analyze_result.get("paradigm_list") == _PARADIGM_LIST
    assert analyze_result.get("clarify_knowledge") == _KNOWLEDGE
    assert analyze_result.get("is_complex") is False


async def test_tc2_3_is_complex_true_propagated() -> None:
    """TC-2-3: is_complex should be true when is_compute is true."""
    state = _make_state(is_compute=True)

    with patch(
        "datacloud_analysis.orchestration.clarification.analyze_clarify_node._analyze_clarification",
        return_value=(_PARADIGM_LIST, _KNOWLEDGE, True),
    ):
        result = await analyze_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    analyze_result = result.get("clarification_analyze_result") or {}
    assert analyze_result.get("is_complex") is True


# 鈹€鈹€ TC-2-4/2-5: paradigm_list 涓虹┖ 鈫?pre_filled_params 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


async def test_tc2_4_empty_paradigm_list_generates_pre_filled_params() -> None:
    """TC-2-4: empty paradigm_list should generate pre_filled_params."""
    structured_input = {"select": ["total_revenue"], "filters": []}
    state = _make_state(structured_input=structured_input)

    with patch(
        "datacloud_analysis.orchestration.clarification.analyze_clarify_node._analyze_clarification",
        return_value=([], _KNOWLEDGE, False),
    ):
        result = await analyze_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    analyze_result = result.get("clarification_analyze_result") or {}
    assert analyze_result.get("paradigm_list") == []
    assert "pre_filled_params" in analyze_result, "绌?paradigm_list 搴旂敓鎴?pre_filled_params"


async def test_tc2_5_empty_paradigm_list_analyze_result_has_knowledge() -> None:
    """TC-2-5: empty paradigm_list should still keep clarify_knowledge."""
    state = _make_state()

    with patch(
        "datacloud_analysis.orchestration.clarification.analyze_clarify_node._analyze_clarification",
        return_value=([], "鐭ヨ瘑鏂囨湰", False),
    ):
        result = await analyze_clarify_node(state, MagicMock())  # type: ignore[arg-type]

    analyze_result = result.get("clarification_analyze_result") or {}
    assert analyze_result.get("clarify_knowledge") == "鐭ヨ瘑鏂囨湰"


# 鈹€鈹€ TC-2-9: 寮傚父浼犳挱 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


async def test_tc2_9_analyze_exception_propagates() -> None:
    """TC-2-9: exceptions from _analyze_clarification should propagate."""
    state = _make_state()

    with (
        patch(
            "datacloud_analysis.orchestration.clarification.analyze_clarify_node._analyze_clarification",
            side_effect=RuntimeError("SDK error"),
        ),
        pytest.raises(RuntimeError, match="SDK error"),
    ):
        await analyze_clarify_node(state, MagicMock())  # type: ignore[arg-type]
