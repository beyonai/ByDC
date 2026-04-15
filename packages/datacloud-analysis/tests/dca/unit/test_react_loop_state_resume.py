"""TC-R01 ~ TC-R05: react_loop 基于 LangGraph State 的 interrupt-resume 机制（方案 B）。

架构目标：
- 中断时将 messages / pending_tool_calls / round_idx / last_query_data 写入 state
- 恢复时从 state 读取，LangGraph checkpoint 自动持久化 state，天然跨实例/重启

测试用例：
- TC-R01: interrupt 触发时，react_messages 写入 state
- TC-R02: resume 时从 state["react_messages"] 恢复，LLM 不被重新调用
- TC-R03: resume replay 成功后，state 中的 react_messages 字段被清除
- TC-R04: 多个 pending tool calls 在 resume 时按顺序全部重放
- TC-R05: messages 序列化/反序列化完整性（SystemMessage/HumanMessage/AIMessage/ToolMessage）
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.errors import GraphBubbleUp
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 辅助 Schema
# ---------------------------------------------------------------------------

class _SimpleSchema(BaseModel):
    query: str = ""


# ---------------------------------------------------------------------------
# 辅助：构造最小 state
# ---------------------------------------------------------------------------

def _make_state(**extra: Any) -> dict[str, Any]:
    return {
        "user_query": "测试查询",
        "messages": [HumanMessage(content="测试查询")],
        "react_messages": None,
        "react_pending_tool_calls": None,
        "react_round_idx": None,
        "react_last_query_data": None,
        **extra,
    }


def _make_tool(name: str = "data_query_test", coroutine: Any = None) -> StructuredTool:
    if coroutine is None:
        coroutine = AsyncMock(return_value={"records": [], "meta": {}})
    return StructuredTool(
        name=name,
        description="test tool",
        args_schema=_SimpleSchema,
        coroutine=coroutine,
    )


def _fake_llm_with_tools() -> Any:
    """返回一个假 LLM（bind_tools 后返回自身，不做真实网络调用）。"""
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm
    return mock_llm


def _make_ai_msg(*tool_names: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"id": f"tc_{i}", "name": name, "args": {"query": "test"}}
            for i, name in enumerate(tool_names)
        ],
    )


# ---------------------------------------------------------------------------
# TC-R01: interrupt 触发 → react_messages 写入 state，进程内缓存不写入
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_r01_interrupt_writes_react_messages_to_state() -> None:
    """TC-R01: dispatch_tool 抛 GraphBubbleUp 时，state["react_messages"] 和
    state["react_pending_tool_calls"] 被填充（方案 B 核心约束）。
    """
    from datacloud_analysis.orchestration.execution.react_loop import run_react_loop

    state = _make_state()
    tool = _make_tool("data_query_test")
    ai_msg = _make_ai_msg("data_query_test")

    with patch(
        "datacloud_analysis.orchestration.execution.react_loop._build_llm",
        return_value=_fake_llm_with_tools(),
    ):
        with patch(
            "datacloud_analysis.orchestration.execution.react_loop._invoke_llm_with_fallback",
            new_callable=AsyncMock,
            return_value=(ai_msg, False),
        ):
            with patch(
                "datacloud_analysis.orchestration.execution.react_loop.dispatch_tool",
                side_effect=GraphBubbleUp("paradigm interrupt"),
            ):
                with pytest.raises(GraphBubbleUp):
                    await run_react_loop(
                        state=state,
                        tools_list=[tool],
                        system_prompt="你是数据分析助手",
                    )

    # 核心断言 1：state 已写入 react_messages
    assert state.get("react_messages") is not None, (
        "interrupt 后 state['react_messages'] 应非 None"
    )
    assert isinstance(state["react_messages"], list), (
        "react_messages 应为 list（序列化后的消息列表）"
    )
    # 核心断言 2：state 已写入 react_pending_tool_calls
    assert state.get("react_pending_tool_calls") is not None, (
        "interrupt 后 state['react_pending_tool_calls'] 应非 None"
    )
    pending = state["react_pending_tool_calls"]
    assert len(pending) >= 1, "pending_tool_calls 至少包含被中断的工具"
    assert pending[0]["name"] == "data_query_test"


# ---------------------------------------------------------------------------
# TC-R02: resume 时从 state 恢复，LLM 不被重新调用
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_r02_resume_reads_from_state_llm_not_called() -> None:
    """TC-R02: state["react_messages"] 有值时，run_react_loop 直接重放工具，不调用 LLM。"""
    from datacloud_analysis.orchestration.execution.react_loop import (
        _deserialize_messages,
        _serialize_messages,
        run_react_loop,
    )

    # 准备：中断时应有的 messages 上下文
    prior_messages = [
        SystemMessage(content="你是数据分析助手"),
        HumanMessage(content="测试查询"),
        AIMessage(
            content="",
            tool_calls=[{"id": "tc_0", "name": "data_query_test", "args": {"query": "test"}}],
        ),
    ]
    pending_calls = [{"id": "tc_0", "name": "data_query_test", "args": {"query": "test"}}]

    state = _make_state(
        react_messages=_serialize_messages(prior_messages),
        react_pending_tool_calls=pending_calls,
        react_round_idx=0,
        react_last_query_data=None,
    )

    tool_calls_received: list[dict] = []

    async def _capturing_tool(query: str = "", **kwargs: Any) -> dict:
        tool_calls_received.append({"query": query})
        return {"__finish__": True, "answer": "done", "result_type": "text"}

    tool = StructuredTool(
        name="data_query_test",
        description="test",
        args_schema=_SimpleSchema,
        coroutine=_capturing_tool,
    )

    llm_call_count = 0

    async def _fake_llm(*args: Any, **kwargs: Any) -> tuple:
        nonlocal llm_call_count
        llm_call_count += 1
        return (AIMessage(content="ok"), False)

    with patch(
        "datacloud_analysis.orchestration.execution.react_loop._build_llm",
        return_value=_fake_llm_with_tools(),
    ):
        with patch(
            "datacloud_analysis.orchestration.execution.react_loop._invoke_llm_with_fallback",
            side_effect=_fake_llm,
        ):
            result = await run_react_loop(
                state=state,
                tools_list=[tool],
                system_prompt="你是数据分析助手",
            )

    # 核心断言 1：LLM 未被调用（replay 直接执行 pending_tool_calls）
    assert llm_call_count == 0, (
        f"resume 时 LLM 不应被调用，实际调用了 {llm_call_count} 次"
    )
    # 核心断言 2：工具被调用一次（replay）
    assert len(tool_calls_received) == 1, (
        f"工具应被 replay 调用一次，实际 {len(tool_calls_received)} 次"
    )


# ---------------------------------------------------------------------------
# TC-R03: resume 成功后 state 中的 react_messages 字段被清除
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_r03_state_cleared_after_successful_resume() -> None:
    """TC-R03: resume replay 完成后，state["react_messages"] / state["react_pending_tool_calls"] 恢复为 None。"""
    from datacloud_analysis.orchestration.execution.react_loop import (
        _serialize_messages,
        run_react_loop,
    )

    prior_messages = [
        SystemMessage(content="sys"),
        HumanMessage(content="query"),
        AIMessage(
            content="",
            tool_calls=[{"id": "tc_0", "name": "data_query_test", "args": {"query": "q"}}],
        ),
    ]
    pending_calls = [{"id": "tc_0", "name": "data_query_test", "args": {"query": "q"}}]

    state = _make_state(
        react_messages=_serialize_messages(prior_messages),
        react_pending_tool_calls=pending_calls,
        react_round_idx=0,
    )

    # 工具返回 finish 信号，让 react_loop 正常结束
    async def _finish_tool(query: str = "", **kwargs: Any) -> dict:
        return {"__finish__": True, "answer": "完成", "result_type": "text"}

    tool = StructuredTool(
        name="data_query_test",
        description="test",
        args_schema=_SimpleSchema,
        coroutine=_finish_tool,
    )

    with patch(
        "datacloud_analysis.orchestration.execution.react_loop._build_llm",
        return_value=_fake_llm_with_tools(),
    ):
        with patch(
            "datacloud_analysis.orchestration.execution.react_loop._invoke_llm_with_fallback",
            new_callable=AsyncMock,
            return_value=(AIMessage(content="ok"), False),
        ):
            await run_react_loop(state=state, tools_list=[tool], system_prompt="sys")

    # 核心断言：replay 消费后 state 字段被清除
    assert state.get("react_messages") is None, (
        "resume 消费后 state['react_messages'] 应被清除为 None"
    )
    assert state.get("react_pending_tool_calls") is None, (
        "resume 消费后 state['react_pending_tool_calls'] 应被清除为 None"
    )
    assert state.get("react_round_idx") is None, (
        "resume 消费后 state['react_round_idx'] 应被清除为 None"
    )


# ---------------------------------------------------------------------------
# TC-R04: 多个 pending tool calls 在 resume 时全部按顺序重放
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_r04_multiple_pending_tools_all_replayed_in_order() -> None:
    """TC-R04: 中断时有多个 pending tool calls，resume 后全部按顺序重放。"""
    from datacloud_analysis.orchestration.execution.react_loop import (
        _serialize_messages,
        run_react_loop,
    )

    prior_messages = [
        SystemMessage(content="sys"),
        HumanMessage(content="query"),
        AIMessage(
            content="",
            tool_calls=[
                {"id": "tc_0", "name": "data_query_a", "args": {"query": "qa"}},
                {"id": "tc_1", "name": "data_query_b", "args": {"query": "qb"}},
                {"id": "tc_2", "name": "data_query_c", "args": {"query": "qc"}},
            ],
        ),
    ]
    # 中断发生在 data_query_b（tc_1），pending = [tc_1, tc_2]
    pending_calls = [
        {"id": "tc_1", "name": "data_query_b", "args": {"query": "qb"}},
        {"id": "tc_2", "name": "data_query_c", "args": {"query": "qc"}},
    ]

    state = _make_state(
        react_messages=_serialize_messages(prior_messages),
        react_pending_tool_calls=pending_calls,
        react_round_idx=0,
    )

    replayed_tools: list[str] = []

    async def _tool_b(query: str = "", **kwargs: Any) -> dict:
        replayed_tools.append("data_query_b")
        return {"records": [], "meta": {}}

    async def _tool_c(query: str = "", **kwargs: Any) -> dict:
        replayed_tools.append("data_query_c")
        return {"__finish__": True, "answer": "done", "result_type": "text"}

    tool_b = StructuredTool(name="data_query_b", description="b", args_schema=_SimpleSchema, coroutine=_tool_b)
    tool_c = StructuredTool(name="data_query_c", description="c", args_schema=_SimpleSchema, coroutine=_tool_c)

    with patch(
        "datacloud_analysis.orchestration.execution.react_loop._build_llm",
        return_value=_fake_llm_with_tools(),
    ):
        with patch(
            "datacloud_analysis.orchestration.execution.react_loop._invoke_llm_with_fallback",
            new_callable=AsyncMock,
            return_value=(AIMessage(content="ok"), False),
        ):
            await run_react_loop(
                state=state,
                tools_list=[tool_b, tool_c],
                system_prompt="sys",
            )

    assert replayed_tools == ["data_query_b", "data_query_c"], (
        f"两个 pending tool 应按顺序 b→c 重放，实际：{replayed_tools}"
    )


# ---------------------------------------------------------------------------
# TC-R05: messages 序列化/反序列化完整性
# ---------------------------------------------------------------------------

def test_tc_r05_serialize_deserialize_all_message_types() -> None:
    """TC-R05: _serialize_messages / _deserialize_messages 支持全部四种消息类型，往返无损。"""
    from datacloud_analysis.orchestration.execution.react_loop import (
        _deserialize_messages,
        _serialize_messages,
    )

    original = [
        SystemMessage(content="系统提示"),
        HumanMessage(content="用户提问"),
        AIMessage(
            content="",
            tool_calls=[{"id": "tc_x", "name": "data_query_test", "args": {"query": "q"}}],
        ),
        ToolMessage(content='{"records": []}', tool_call_id="tc_x"),
    ]

    serialized = _serialize_messages(original)
    assert isinstance(serialized, list), "序列化结果应为 list"
    assert all(isinstance(m, dict) for m in serialized), "每个元素应为 dict"

    restored = _deserialize_messages(serialized)
    assert len(restored) == len(original), "反序列化后消息数量应与原始一致"

    assert isinstance(restored[0], SystemMessage), "第 0 条应为 SystemMessage"
    assert restored[0].content == "系统提示"

    assert isinstance(restored[1], HumanMessage), "第 1 条应为 HumanMessage"
    assert restored[1].content == "用户提问"

    assert isinstance(restored[2], AIMessage), "第 2 条应为 AIMessage"
    tcs = getattr(restored[2], "tool_calls", [])
    assert len(tcs) == 1
    assert tcs[0]["name"] == "data_query_test"

    assert isinstance(restored[3], ToolMessage), "第 3 条应为 ToolMessage"
    assert restored[3].tool_call_id == "tc_x"
    assert '{"records": []}' in restored[3].content
