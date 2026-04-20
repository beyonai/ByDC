"""TC-1-7: finish_react_node 单元测试（阶段 3 更新）。

验收目标：
- TC-1-7: 从 state["messages"] 提取 finish_react 参数，构造 react_final，清理 round_idx
"""

from __future__ import annotations

from typing import Any

from datacloud_analysis.orchestration.execution.finish_react_node import finish_react_node
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# ── 辅助 ──────────────────────────────────────────────────────────────────────

_FINISH_ARGS = {
    "reason": "分析完成",
    "answer": "高营收企业共 100 家",
    "result_type": "text",
    "csv_file_path": "",
    "data": "",
}


def _messages_with_finish_react() -> list[Any]:
    call = {"name": "finish_react", "args": _FINISH_ARGS, "id": "tc_fr"}
    return [
        SystemMessage(content="sys"),
        HumanMessage(content="查询高营收企业"),
        AIMessage(content="", tool_calls=[call]),
    ]


# ── TC-1-7a: react_final 正确构造 ─────────────────────────────────────────────


async def test_tc1_7a_builds_react_final_from_messages() -> None:
    """TC-1-7a: state["messages"] 中含 finish_react → react_final 正确构造。"""
    state: dict[str, Any] = {
        "messages": _messages_with_finish_react(),
        "react_round_idx": 3,
    }
    result = await finish_react_node(state, None)  # type: ignore[arg-type]

    rf = result.get("react_final") or {}
    assert rf.get("result_type") == "text"
    assert rf.get("answer") == "高营收企业共 100 家"
    assert rf.get("stop_reason") is not None


# ── TC-1-7b: state 清理 ────────────────────────────────────────────────────────


async def test_tc1_7b_clears_log_and_round_idx() -> None:
    """TC-1-7b: finish_react_node 完成后，react_messages_log 和 react_round_idx 被清理。"""
    state: dict[str, Any] = {
        "messages": _messages_with_finish_react(),
        "react_round_idx": 2,
    }
    result = await finish_react_node(state, None)  # type: ignore[arg-type]

    assert result.get("react_messages_log") is None, "react_messages_log 应被清理"
    assert result.get("react_round_idx") is None, "react_round_idx 应被清理"


# ── TC-1-7c: max_rounds_exceeded 也能正常处理 ─────────────────────────────────


async def test_tc1_7c_max_rounds_exceeded_handled() -> None:
    """TC-1-7c: execution_status=max_rounds_exceeded 时，finish_react_node 能生成兜底 react_final。"""
    state: dict[str, Any] = {
        "messages": [
            SystemMessage(content="sys"),
            AIMessage(content="已超出最大轮数", tool_calls=[]),
        ],
        "react_round_idx": 10,
        "execution_status": "max_rounds_exceeded",
    }
    result = await finish_react_node(state, None)  # type: ignore[arg-type]

    rf = result.get("react_final") or {}
    assert rf.get("result_type") is not None, "应生成 react_final"
    assert result.get("react_messages_log") is None


# ── TC-1-7d: query_data 注入 ──────────────────────────────────────────────────


async def test_tc1_7d_query_data_injected_into_react_final() -> None:
    """TC-1-7d: react_last_query_data 在 state 中时，应被注入 react_final["query_data"]。"""
    import typing
    _QUERY_DATA: dict[typing.Any, typing.Any] = {"records": [{"id": 1}], "meta": {"total": 1}}
    state: dict[typing.Any, typing.Any] = {
        "messages": _messages_with_finish_react(),
        "react_round_idx": 1,
        "react_last_query_data": _QUERY_DATA,
    }
    # Override result_type to query_result
    call = {"name": "finish_react", "args": {**_FINISH_ARGS, "result_type": "query_result"}, "id": "tc_fr2"}
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage as _AI
    state["messages"] = [
        SystemMessage(content="sys"),
        HumanMessage(content="test"),
        _AI(content="", tool_calls=[call]),
    ]
    result = await finish_react_node(state, None)  # type: ignore[arg-type]

    rf = result.get("react_final") or {}
    assert rf.get("query_data") == _QUERY_DATA, "query_data 应被注入 react_final"
    assert result.get("react_last_query_data") is None, "react_last_query_data 应被清理"
