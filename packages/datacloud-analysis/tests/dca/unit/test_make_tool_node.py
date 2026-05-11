"""TC-3-1 ~ TC-3-4: make_tool_node 单元测试（阶段 3 红阶段）。

验收目标：
- TC-3-1: 正常工具调用 → 从 state.messages 提取 tool_call，执行，写 ToolMessage
- TC-3-2: ClarificationNeededError → execution_status="clarify_needed"
- TC-3-3: 工具执行后 state 清理（澄清相关字段置 None）
- TC-3-4: state.messages 中无匹配 tool_call → 返回 error
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from datacloud_analysis.orchestration.execution.make_tool_node import make_tool_node
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    ClarificationNeededError,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# ── 辅助 ──────────────────────────────────────────────────────────────────────

_TOOL_NAME = "query_ads_enterprise"
_TOOL_CALL_ID = "tc_001"


def _make_state_with_tool_call(
    tool_name: str = _TOOL_NAME,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "id": _TOOL_CALL_ID, "args": {"query": "营收"}}],
    )
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="查询营收"), ai_msg],
        "react_round_idx": 1,
    }
    if extra:
        state.update(extra)
    return state


def _make_state_with_parallel_tool_calls() -> dict[str, Any]:
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": _TOOL_NAME, "id": "tc_001", "args": {"query": "营收A"}},
            {"name": _TOOL_NAME, "id": "tc_002", "args": {"query": "营收B"}},
        ],
    )
    return {
        "messages": [HumanMessage(content="查询营收"), ai_msg],
        "react_round_idx": 1,
        "react_current_tool_call": {
            "name": _TOOL_NAME,
            "id": "tc_002",
            "args": {"query": "营收B"},
        },
    }


# ── TC-3-1: 正常执行 → ToolMessage 写入 ──────────────────────────────────────


async def test_tc3_1_single_tool_call_writes_tool_message() -> None:
    """TC-3-1: 从 state.messages 提取 tool_call，执行工具，返回含 ToolMessage 的更新。"""
    state = _make_state_with_tool_call()
    mock_tool = MagicMock()
    mock_tool.name = _TOOL_NAME

    with patch(
        "datacloud_analysis.orchestration.execution.make_tool_node.dispatch_tool",
        return_value=(_TOOL_CALL_ID, {"records": [], "total": 0}),
    ):
        node = make_tool_node(_TOOL_NAME, mock_tool)
        result = await node(state, MagicMock())  # type: ignore[arg-type]

    assert "messages" in result
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], ToolMessage)
    assert result["messages"][0].tool_call_id == _TOOL_CALL_ID
    assert result.get("execution_status") is None


async def test_tc3_1b_current_tool_call_takes_priority_over_first_match() -> None:
    """TC-3-1b: per-tool Send 注入的当前 tool_call 应优先于 messages 中的第一条同名 call。"""
    state = _make_state_with_parallel_tool_calls()
    mock_tool = MagicMock()
    mock_tool.name = _TOOL_NAME
    captured: dict[str, Any] = {}

    async def _dispatch_tool(tool_call: dict[str, Any], tools_map: Any, state: Any, **kwargs: Any):
        captured["tool_call"] = dict(tool_call)
        return tool_call["id"], {"records": [], "total": 0}

    with patch(
        "datacloud_analysis.orchestration.execution.make_tool_node.dispatch_tool",
        new=AsyncMock(side_effect=_dispatch_tool),
    ):
        node = make_tool_node(_TOOL_NAME, mock_tool)
        result = await node(state, MagicMock())  # type: ignore[arg-type]

    assert captured["tool_call"]["id"] == "tc_002"
    assert captured["tool_call"]["args"]["query"] == "营收B"
    assert result["messages"][0].tool_call_id == "tc_002"


# ── TC-3-2: ClarificationNeededError → clarify_needed ───────────────────────


async def test_tc3_2_clarification_needed_error_captured() -> None:
    """TC-3-2: dispatch_tool 抛 ClarificationNeededError → execution_status="clarify_needed"。"""
    state = _make_state_with_tool_call()
    mock_tool = MagicMock()
    mock_tool.name = _TOOL_NAME

    exc_context = {
        "tool_name": _TOOL_NAME,
        "query": "营收",
        "paradigm_list": [],
        "ontology_code": "ads_enterprise",
    }
    with patch(
        "datacloud_analysis.orchestration.execution.make_tool_node.dispatch_tool",
        side_effect=ClarificationNeededError(exc_context),
    ):
        node = make_tool_node(_TOOL_NAME, mock_tool)
        result = await node(state, MagicMock())  # type: ignore[arg-type]

    assert result["execution_status"] == "clarify_needed"
    ctx = result.get("pending_clarification_context") or {}
    assert ctx.get("tool_name") == _TOOL_NAME
    assert "query" in ctx or "ontology_code" in ctx


# ── TC-3-3: 执行后 state 字段清理 ────────────────────────────────────────────


async def test_tc3_3_state_fields_cleared_after_execution() -> None:
    """TC-3-3: 工具执行成功后澄清相关 state 字段全部置 None。"""
    state = _make_state_with_tool_call(
        extra={
            "clarification_formatted_params": {
                "tool_name": _TOOL_NAME,
                "params": {},
                "is_complex": False,
            },
            "pending_clarification_context": {"tool_name": _TOOL_NAME},
            "clarification_analyze_result": {"paradigm_list": []},
        }
    )
    mock_tool = MagicMock()
    mock_tool.name = _TOOL_NAME

    with patch(
        "datacloud_analysis.orchestration.execution.make_tool_node.dispatch_tool",
        return_value=(_TOOL_CALL_ID, "ok"),
    ):
        node = make_tool_node(_TOOL_NAME, mock_tool)
        result = await node(state, MagicMock())  # type: ignore[arg-type]

    assert result.get("clarification_formatted_params") is None
    assert result.get("pending_clarification_context") is None
    assert result.get("clarification_analyze_result") is None


# ── TC-3-4: 无匹配 tool_call → 错误处理 ──────────────────────────────────────


async def test_tc3_4_no_matching_tool_call_returns_error() -> None:
    """TC-3-4: state.messages 中无对应工具的 tool_call → execution_status="error"。"""
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="hello")],
        "react_round_idx": 1,
    }
    mock_tool = MagicMock()
    mock_tool.name = _TOOL_NAME

    node = make_tool_node(_TOOL_NAME, mock_tool)
    result = await node(state, MagicMock())  # type: ignore[arg-type]

    assert result.get("execution_status") == "error"
