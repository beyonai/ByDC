"""TC-1-1 ~ TC-1-7: llm_call_node 单元测试（阶段 3 更新）。

验收目标：
- TC-1-1: 首次调用，LLM 被调用 1 次，result["messages"] 含 AIMessage，react_round_idx=1
- TC-1-2: LLM 无 tool_calls，execution_status=None，result["messages"] 含 AIMessage
- TC-1-3: react_round_idx >= max_rounds，返回 max_rounds_exceeded，不调用 LLM
- TC-1-4: state["messages"] 已有历史消息，从中恢复，LLM 被调用 1 次（新一轮）
- TC-1-7: 每次调用 react_round_idx 正确自增
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from datacloud_analysis.orchestration.execution.llm_call_node import make_llm_call_node
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# ── 测试辅助 ───────────────────────────────────────────────────────────────────

_TOOL_CALL = {"name": "query_ads_enterprise", "args": {"query": "高营收企业"}, "id": "tc_001"}
_FINISH_CALL = {
    "name": "finish_react",
    "args": {"answer": "done", "result_type": "text"},
    "id": "tc_002",
}


def _make_ai_msg(tool_calls: list[dict] | None = None, content: str = "") -> AIMessage:
    return AIMessage(content=content, tool_calls=tool_calls or [])


def _make_state(
    *,
    user_query: str = "查询高营收企业",
    react_round_idx: int | None = None,
    messages: list | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {"user_query": user_query}
    if react_round_idx is not None:
        state["react_round_idx"] = react_round_idx
    if messages is not None:
        state["messages"] = messages
    return state


# ── TC-1-1: 首次调用初始化消息历史 ─────────────────────────────────────────────


async def test_tc1_1_first_call_initializes_messages_and_calls_llm() -> None:
    """TC-1-1: state["messages"] 为空时，节点初始化消息历史并调用 LLM，返回 AIMessage。"""
    ai_msg = _make_ai_msg(tool_calls=[_TOOL_CALL])
    state = _make_state(user_query="查询高营收企业")

    _invoke_mock = AsyncMock(return_value=(ai_msg, False))
    with (
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._invoke_llm_with_fallback",
            _invoke_mock,
        ),
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._build_llm",
            return_value=MagicMock(),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._build_fallback_llm",
            return_value=None,
        ),
    ):
        node = make_llm_call_node(
            tools_list=[],
            system_prompt="You are a helpful assistant.",
            max_rounds=10,
        )
        result = await node(state, MagicMock())

    assert _invoke_mock.call_count == 1, "LLM 应被调用 1 次"
    assert "messages" in result, "应写入 messages"
    assert len(result["messages"]) == 1, "应恰好写入 1 条 AIMessage"
    assert isinstance(result["messages"][0], AIMessage)
    assert result.get("react_round_idx") == 1, "首轮完成后 react_round_idx 应为 1"


# ── TC-1-2: LLM 无 tool_calls ──────────────────────────────────────────────────


async def test_tc1_2_no_tool_calls_returns_ai_message() -> None:
    """TC-1-2: LLM 不产生 tool_calls，节点仍正常返回，result["messages"] 含 AIMessage。"""
    ai_msg = _make_ai_msg(tool_calls=[], content="分析完成，结果如下。")
    state = _make_state()

    with (
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._invoke_llm_with_fallback",
            AsyncMock(return_value=(ai_msg, False)),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._build_llm",
            return_value=MagicMock(),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._build_fallback_llm",
            return_value=None,
        ),
    ):
        node = make_llm_call_node(tools_list=[], system_prompt="sys", max_rounds=10)
        result = await node(state, MagicMock())

    msgs = result.get("messages") or []
    assert any(isinstance(m, AIMessage) for m in msgs), "result['messages'] 应含 AIMessage"
    assert result.get("execution_status") is None, "无 tool_calls 时 execution_status 应为 None"


# ── TC-1-3: max_rounds 超限 ─────────────────────────────────────────────────────


async def test_tc1_3_max_rounds_exceeded_no_llm_call() -> None:
    """TC-1-3: react_round_idx >= max_rounds → 返回 max_rounds_exceeded，不调用 LLM。"""
    state = _make_state(react_round_idx=5)
    invoke_mock = AsyncMock()

    with (
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._invoke_llm_with_fallback",
            invoke_mock,
        ),
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._build_llm",
            return_value=MagicMock(),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._build_fallback_llm",
            return_value=None,
        ),
    ):
        node = make_llm_call_node(tools_list=[], system_prompt="sys", max_rounds=5)
        result = await node(state, MagicMock())

    assert invoke_mock.call_count == 0, "超限时不应调用 LLM"
    assert result.get("execution_status") == "max_rounds_exceeded"


# ── TC-1-4: 核心验收 — 从 state["messages"] 恢复历史 ─────────────────────────


async def test_tc1_4_resumes_from_state_messages_without_reinit() -> None:
    """TC-1-4（核心）: state["messages"] 已有历史 → 从中恢复上下文，LLM 被调用 1 次。

    模拟第 2 轮：state["messages"] 已含上一轮 AIMessage + ToolMessage。
    llm_call_node 应将这些历史消息传给 LLM，而不是重新初始化为空。
    """
    prior_ai = AIMessage(content="", tool_calls=[_TOOL_CALL])
    prior_tool = ToolMessage(content='{"total": 5}', tool_call_id="tc_001")
    state = _make_state(
        react_round_idx=1,
        messages=[
            HumanMessage(content="查询高营收企业"),
            prior_ai,
            prior_tool,
        ],
    )
    ai_msg2 = _make_ai_msg(tool_calls=[_FINISH_CALL])
    invoke_mock = AsyncMock(return_value=(ai_msg2, False))

    with (
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._invoke_llm_with_fallback",
            invoke_mock,
        ),
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._build_llm",
            return_value=MagicMock(),
        ),
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._build_fallback_llm",
            return_value=None,
        ),
    ):
        node = make_llm_call_node(tools_list=[], system_prompt="sys", max_rounds=10)
        result = await node(state, MagicMock())

    assert invoke_mock.call_count == 1, "恢复时 LLM 只应调用 1 次（新一轮，非重初始化）"

    # 传入 LLM 的消息应包含历史 AIMessage
    call_args = invoke_mock.call_args
    messages_window = (
        call_args.args[2]
        if len(call_args.args) >= 3
        else call_args.kwargs.get("messages_window", [])
    )
    msg_types = [type(m).__name__ for m in messages_window]
    assert "AIMessage" in msg_types, "传入 LLM 的消息应含上一轮 AIMessage（从 state.messages 恢复）"
    assert "ToolMessage" in msg_types, "传入 LLM 的消息应含 ToolMessage（工具返回结果，V0.3 fix）"

    assert result.get("react_round_idx") == 2


# ── TC-1-7: react_round_idx 自增 ───────────────────────────────────────────────


async def test_tc1_7_round_idx_increments_correctly() -> None:
    """TC-1-7: 每次调用 react_round_idx 正确自增。"""
    for start_round in (0, 1, 3):
        ai_msg = _make_ai_msg(tool_calls=[_TOOL_CALL])
        state = _make_state(react_round_idx=start_round if start_round > 0 else None)
        if start_round == 0:
            state.pop("react_round_idx", None)

        with (
            patch(
                "datacloud_analysis.orchestration.execution.llm_call_node._invoke_llm_with_fallback",
                AsyncMock(return_value=(ai_msg, False)),
            ),
            patch(
                "datacloud_analysis.orchestration.execution.llm_call_node._build_llm",
                return_value=MagicMock(),
            ),
            patch(
                "datacloud_analysis.orchestration.execution.llm_call_node._build_fallback_llm",
                return_value=None,
            ),
        ):
            node = make_llm_call_node(tools_list=[], system_prompt="sys", max_rounds=10)
            result = await node(state, MagicMock())

        expected = start_round + 1
        assert result.get("react_round_idx") == expected, (
            f"从 round={start_round} 开始，完成后应为 {expected}，实际 {result.get('react_round_idx')}"
        )
