"""TC-1-1 ~ TC-1-4: tool_dispatcher_node 单元测试（阶段 1 红阶段）。

验收目标：
- TC-1-1: 从 react_messages_log 读 AIMessage，调用工具，ToolMessage 追加到 log
- TC-1-2: AIMessage.tool_calls = [finish_react] → execution_status="finish_react"，不调用 dispatch_tool
- TC-1-4a: clarification_formatted_params 在 state → dispatch_tool 正常被调用
- TC-1-4b: ClarificationNeededError 被抛 → execution_status="clarify_needed"，pending_clarification_context 写入
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from datacloud_analysis.orchestration.execution.tool_dispatcher_node import (
    make_tool_dispatcher_node,
)
from langchain_core.messages import AIMessage, ToolMessage

# ── 辅助 ──────────────────────────────────────────────────────────────────────

_TOOL_CALL = {"name": "query_ads_enterprise", "args": {"query": "高营收"}, "id": "tc_001"}
_FINISH_CALL = {
    "name": "finish_react",
    "args": {"answer": "done", "result_type": "text"},
    "id": "tc_002",
}
_MIXED_CALLS = [_FINISH_CALL, _TOOL_CALL]


def _serialize(msgs: list) -> list[dict]:
    result = []
    for m in msgs:
        if isinstance(m, AIMessage):
            result.append(
                {
                    "type": "ai",
                    "content": str(m.content or ""),
                    "tool_calls": list(getattr(m, "tool_calls", []) or []),
                }
            )
        elif isinstance(m, ToolMessage):
            result.append(
                {
                    "type": "tool",
                    "content": str(m.content or ""),
                    "tool_call_id": str(m.tool_call_id or ""),
                }
            )
        else:
            result.append({"type": "system", "content": str(getattr(m, "content", ""))})
    return result


def _log_with_ai(tool_calls: list[dict], content: str = "") -> list[dict]:
    ai = AIMessage(content=content, tool_calls=tool_calls)
    return _serialize([ai])


def _make_state(
    *,
    react_messages_log: list[dict] | None = None,
    clarification_formatted_params: dict | None = None,
    react_round_idx: int = 1,
) -> dict[str, Any]:
    state: dict[str, Any] = {"react_round_idx": react_round_idx}
    if react_messages_log is not None:
        state["react_messages_log"] = react_messages_log
    if clarification_formatted_params is not None:
        state["clarification_formatted_params"] = clarification_formatted_params
    return state


# ── TC-1-1: 正常工具分发 ───────────────────────────────────────────────────────


async def test_tc1_1_dispatches_tool_and_appends_tool_message() -> None:
    """TC-1-1: 正常调用工具，ToolMessage 追加到 react_messages_log。"""
    log = _log_with_ai([_TOOL_CALL])
    state = _make_state(react_messages_log=log)
    dispatch_mock = AsyncMock(return_value=("tc_001", {"records": [], "meta": {}}))

    with patch(
        "datacloud_analysis.orchestration.execution.tool_dispatcher_node.dispatch_tool",
        dispatch_mock,
    ):
        node = make_tool_dispatcher_node(tools_list=[])
        result = await node(state, MagicMock())

    assert dispatch_mock.call_count == 1
    new_log = result.get("react_messages_log") or []
    tool_items = [i for i in new_log if i.get("type") == "tool"]
    assert tool_items, "ToolMessage 应追加到 react_messages_log"
    assert result.get("execution_status") is None


# ── TC-1-2: finish_react 工具调用 ─────────────────────────────────────────────


async def test_tc1_2_finish_react_returns_status_without_dispatch() -> None:
    """TC-1-2: AIMessage 只含 finish_react → execution_status=finish_react，不调用 dispatch_tool。"""
    log = _log_with_ai([_FINISH_CALL])
    state = _make_state(react_messages_log=log)
    dispatch_mock = AsyncMock()

    with patch(
        "datacloud_analysis.orchestration.execution.tool_dispatcher_node.dispatch_tool",
        dispatch_mock,
    ):
        node = make_tool_dispatcher_node(tools_list=[])
        result = await node(state, MagicMock())

    assert dispatch_mock.call_count == 0, "finish_react 不应调用 dispatch_tool"
    assert result.get("execution_status") == "finish_react"


# ── TC-1-4a: clarification_formatted_params 命中 ──────────────────────────────


async def test_tc1_4a_clarification_override_in_state_flows_to_dispatch() -> None:
    """TC-1-4a: clarification_formatted_params 在 state → dispatch_tool 正常被调用。"""
    log = _log_with_ai([_TOOL_CALL])
    formatted = {
        "tool_name": "query_ads_enterprise",
        "params": {"filters": [{"field": "total_revenue", "op": "gt", "value": 100}]},
        "is_complex": False,
        "query": "高营收",
    }
    state = _make_state(react_messages_log=log, clarification_formatted_params=formatted)
    dispatch_mock = AsyncMock(return_value=("tc_001", {"records": []}))

    with patch(
        "datacloud_analysis.orchestration.execution.tool_dispatcher_node.dispatch_tool",
        dispatch_mock,
    ):
        node = make_tool_dispatcher_node(tools_list=[])
        result = await node(state, MagicMock())

    assert dispatch_mock.call_count == 1
    # clarification_formatted_params 应被消费后清理
    assert result.get("clarification_formatted_params") is None


# ── TC-1-4b: ClarificationNeededError → clarify_needed ───────────────────────


async def test_tc1_4b_clarification_needed_error_captured() -> None:
    """TC-1-4b: dispatch_tool 抛 ClarificationNeededError → execution_status=clarify_needed。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        ClarificationNeededError,
    )

    log = _log_with_ai([_TOOL_CALL])
    state = _make_state(react_messages_log=log, react_round_idx=2)

    exc_context = {
        "tool_name": "query_ads_enterprise",
        "query": "高营收",
        "scope_code": "ads",
        "structured_input": {"filters": []},
        "is_compute": False,
        "resolved": {},
        "is_complex": False,
    }

    async def _raise(*args: Any, **kwargs: Any) -> None:
        raise ClarificationNeededError(exc_context)

    with patch(
        "datacloud_analysis.orchestration.execution.tool_dispatcher_node.dispatch_tool",
        _raise,
    ):
        node = make_tool_dispatcher_node(tools_list=[])
        result = await node(state, MagicMock())

    assert result.get("execution_status") == "clarify_needed"
    ctx = result.get("pending_clarification_context") or {}
    assert ctx.get("tool_name") == "query_ads_enterprise"
    assert "react_round_idx" in ctx, "react_round_idx 应写入 pending_clarification_context"


async def test_tc1_5_gateway_context_prefers_configurable() -> None:
    """TC-1-5: dispatch_tool 优先使用 config.configurable.gateway_context。"""
    log = _log_with_ai([_TOOL_CALL])
    state = _make_state(react_messages_log=log)
    from_config = object()
    from_closure = object()

    received_ctx: list[Any] = []

    async def _capture(*args: Any, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        received_ctx.append(kwargs.get("gateway_context"))
        return "tc_001", {"records": []}

    with patch(
        "datacloud_analysis.orchestration.execution.tool_dispatcher_node.dispatch_tool",
        _capture,
    ):
        node = make_tool_dispatcher_node(tools_list=[], gateway_context=from_closure)
        result = await node(state, {"configurable": {"gateway_context": from_config}})

    assert result.get("execution_status") is None
    assert received_ctx == [from_config]


async def test_tc1_6_gateway_context_falls_back_to_closure() -> None:
    """TC-1-6: configurable 中无 gateway_context 时回退闭包注入值。"""
    log = _log_with_ai([_TOOL_CALL])
    state = _make_state(react_messages_log=log)
    from_closure = object()
    received_ctx: list[Any] = []

    async def _capture(*args: Any, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        received_ctx.append(kwargs.get("gateway_context"))
        return "tc_001", {"records": []}

    with patch(
        "datacloud_analysis.orchestration.execution.tool_dispatcher_node.dispatch_tool",
        _capture,
    ):
        node = make_tool_dispatcher_node(tools_list=[], gateway_context=from_closure)
        result = await node(state, {"configurable": {}})

    assert result.get("execution_status") is None
    assert received_ctx == [from_closure]


async def test_tc1_7_mixed_calls_ignores_finish_and_dispatches_non_finish() -> None:
    """TC-1-7: mixed tool_calls(含 finish_react) 时应优先执行非 finish 工具。"""
    log = _log_with_ai(_MIXED_CALLS)
    state = _make_state(react_messages_log=log)

    dispatched: list[str] = []

    async def _capture(tc: dict[str, Any], *args: Any, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        dispatched.append(str(tc.get("name") or ""))
        return "tc_001", {"records": []}

    with patch(
        "datacloud_analysis.orchestration.execution.tool_dispatcher_node.dispatch_tool",
        _capture,
    ):
        node = make_tool_dispatcher_node(tools_list=[])
        result = await node(state, MagicMock())

    assert result.get("execution_status") is None
    assert dispatched == ["query_ads_enterprise"], "mixed calls 应忽略 finish_react，仅执行真实工具"
