"""阶段一 — HookAwareToolNode 单元测试（TC-HAN-1 ~ TC-HAN-9）。

验收目标（文档 1.4.7 阶段一卡点）：
- TC-HAN-1 ~ TC-HAN-5: HookAwareToolNode before/after hook、ClarificationNeededError→Command、
  finish_react Markdown 内容完整性
- TC-HAN-6: should_continue 路由函数（L2 / L3 / 正常）
- TC-HAN-7: after_tools_route 路由函数（L1 / 正常）
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from datacloud_analysis.orchestration.execution.hook_aware_tool_node import HookAwareToolNode
from datacloud_analysis.orchestration.graph_builder import after_tools_route, should_continue
from datacloud_analysis.tool_hook_plugins.types import ClarificationNeededError
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

# ── 共用常量 ───────────────────────────────────────────────────────────────────

_MAX_ROUNDS = 10
_TOOL_CALL_ID = "tc_001"


# ── 测试用 mock 工具 ───────────────────────────────────────────────────────────


@tool
def mock_query_tool(query: str) -> str:
    """Simple mock tool for unit tests."""
    return f"result: {query}"


@tool
def mock_finish_react(
    result_type: str,
    answer: str,
    stop_reason: str = "",
    csv_file_path: str = "",
) -> str:
    """Mock finish_react sentinel tool."""
    return answer


# ── 辅助工厂 ───────────────────────────────────────────────────────────────────


def _state_with_tool_call(
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tc = {"name": tool_name, "id": _TOOL_CALL_ID, "args": tool_args or {}}
    state: dict[str, Any] = {
        "messages": [
            HumanMessage(content="查询营收"),
            AIMessage(content="", tool_calls=[tc]),
        ],
        "react_round_idx": 1,
        "user_query": "查询营收",
    }
    if extra:
        state.update(extra)
    return state


def _make_mock_manager(
    patched_tool_params: dict[str, Any] | None = None,
    clarification_error: ClarificationNeededError | None = None,
) -> MagicMock:
    """返回 mock ToolHookPluginManager。

    run_before：若 clarification_error 非 None 则抛出，否则返回 (ctx, None)，
               可选地用 patched_tool_params 覆盖 tool_params。
    run_after：总是返回 (ctx, None)。
    """
    manager = MagicMock()

    if clarification_error is not None:
        manager.run_before = AsyncMock(side_effect=clarification_error)
    else:

        async def _run_before(ctx: dict[str, Any]) -> tuple[dict[str, Any], None]:
            merged = dict(ctx)
            if patched_tool_params is not None:
                merged["tool_params"] = patched_tool_params
            return merged, None

        manager.run_before = _run_before

    manager.run_after = AsyncMock(return_value=({"tool_name": "x"}, None))
    return manager


def _fake_super_ok(
    tool_name: str = "mock_query_tool",
    content: str = "tool_result",
) -> AsyncMock:
    """返回模拟正常工具执行结果的 super().ainvoke mock。"""
    tool_msg = ToolMessage(content=content, tool_call_id=_TOOL_CALL_ID, name=tool_name)
    return AsyncMock(return_value={"messages": [tool_msg]})


# ═══════════════════════════════════════════════════════════════════════════════
# TC-HAN-1: 无 tool_calls → 直接委托父类
# ═══════════════════════════════════════════════════════════════════════════════


async def test_han1_no_tool_calls_delegates_to_super() -> None:
    """TC-HAN-1: state 中 AIMessage 无 tool_calls → 直接委托 ToolNode.ainvoke。"""
    node = HookAwareToolNode([mock_query_tool])
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="hello"), AIMessage(content="world", tool_calls=[])],
    }

    with patch.object(ToolNode, "ainvoke", new_callable=AsyncMock) as super_mock:
        super_mock.return_value = {"messages": []}
        result = await node.ainvoke(state, None)

    super_mock.assert_called_once()
    assert result == {"messages": []}


# ═══════════════════════════════════════════════════════════════════════════════
# TC-HAN-2: before hook 修改 tool_params → 透传到实际工具调用
# ═══════════════════════════════════════════════════════════════════════════════


async def test_han2_before_hook_patches_tool_params() -> None:
    """TC-HAN-2: before hook 修改 tool_params，patch 被透传到 super().ainvoke 的 patched_state。"""
    node = HookAwareToolNode([mock_query_tool])
    state = _state_with_tool_call("mock_query_tool", {"query": "original"})
    manager = _make_mock_manager(patched_tool_params={"query": "patched"})

    captured_states: list[dict[str, Any]] = []

    async def _fake_super(
        self_instance: Any, input_state: Any, config: Any = None, **kw: Any
    ) -> Any:
        captured_states.append(dict(input_state) if isinstance(input_state, dict) else {})
        return {
            "messages": [
                ToolMessage(content="ok", tool_call_id=_TOOL_CALL_ID, name="mock_query_tool")
            ]
        }

    with (
        patch(
            "datacloud_analysis.orchestration.execution.hook_aware_tool_node.get_tool_hook_plugin_manager",
            return_value=manager,
        ),
        patch.object(ToolNode, "ainvoke", _fake_super),
    ):
        await node.ainvoke(state, None)

    assert len(captured_states) == 1, "super().ainvoke 应被调用一次"
    msgs = captured_states[0].get("messages") or []
    last_ai = next((m for m in reversed(msgs) if isinstance(m, AIMessage)), None)
    assert last_ai is not None, "patched_state 应含 AIMessage"
    assert last_ai.tool_calls[0]["args"]["query"] == "patched", (
        f"tool_params 应被 before hook patch，实际: {last_ai.tool_calls[0]['args']}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TC-HAN-3: ClarificationNeededError → Command(goto="analyze_clarify")
# ═══════════════════════════════════════════════════════════════════════════════


async def test_han3_clarification_needed_returns_command() -> None:
    """TC-HAN-3: before hook 抛 ClarificationNeededError → 返回 Command(goto='analyze_clarify')。"""
    node = HookAwareToolNode([mock_query_tool])
    state = _state_with_tool_call("mock_query_tool", {"query": "ambiguous"})
    exc = ClarificationNeededError({"reason": "字段名歧义", "field": "query"})
    manager = _make_mock_manager(clarification_error=exc)

    with patch(
        "datacloud_analysis.orchestration.execution.hook_aware_tool_node.get_tool_hook_plugin_manager",
        return_value=manager,
    ):
        result = await node.ainvoke(state, None)

    assert isinstance(result, Command), f"应返回 Command，实际: {type(result)}"
    update: dict[str, Any] = dict(result.update or {})
    assert update.get("execution_status") == "clarify_needed", (
        f"execution_status 应为 clarify_needed，实际: {update.get('execution_status')}"
    )
    ctx = update.get("pending_clarification_context") or {}
    assert ctx.get("tool_name") == "mock_query_tool", (
        f"pending_clarification_context.tool_name 应为 mock_query_tool，实际: {ctx.get('tool_name')}"
    )
    assert ctx.get("field") == "query", "exc.context 应被合并到 pending_clarification_context"


# ═══════════════════════════════════════════════════════════════════════════════
# TC-HAN-4: after hook 在工具执行后被调用
# ═══════════════════════════════════════════════════════════════════════════════


async def test_han4_after_hook_called_with_tool_message() -> None:
    """TC-HAN-4: 工具执行后，after hook 被调用，传入 tool_name 和 tool_output。"""
    node = HookAwareToolNode([mock_query_tool])
    state = _state_with_tool_call("mock_query_tool", {"query": "test"})

    after_calls: list[dict[str, Any]] = []

    async def _run_before(ctx: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return ctx, None

    async def _run_after(ctx: dict[str, Any]) -> tuple[dict[str, Any], None]:
        after_calls.append(dict(ctx))
        return ctx, None

    manager = MagicMock()
    manager.run_before = _run_before
    manager.run_after = _run_after

    tool_msg = ToolMessage(
        content="tool_result_xyz", tool_call_id=_TOOL_CALL_ID, name="mock_query_tool"
    )

    with (
        patch(
            "datacloud_analysis.orchestration.execution.hook_aware_tool_node.get_tool_hook_plugin_manager",
            return_value=manager,
        ),
        patch.object(ToolNode, "ainvoke", new_callable=AsyncMock) as sm,
    ):
        sm.return_value = {"messages": [tool_msg]}
        await node.ainvoke(state, None)

    assert len(after_calls) >= 1, "after hook 应至少被调用一次"
    assert any(c.get("tool_name") == "mock_query_tool" for c in after_calls), (
        "after hook context 应含 tool_name='mock_query_tool'"
    )
    assert any("tool_result_xyz" in str(c.get("tool_output", "")) for c in after_calls), (
        "after hook context 应含 ToolMessage 的 content"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TC-HAN-5: finish_react ToolMessage 保留完整 Markdown 内容
# ═══════════════════════════════════════════════════════════════════════════════


async def test_han5_finish_react_markdown_preserved() -> None:
    """TC-HAN-5: finish_react ToolMessage 的 Markdown 内容被 HookAwareToolNode 完整透传。

    ToolNode 执行工具后返回 ToolMessage，HookAwareToolNode 不应修改 content。
    用 mock 模拟 super().ainvoke 返回含 Markdown 的 ToolMessage，验证透传无损。
    """
    markdown = "## 分析结果\n营收共 100 家企业。"
    tc = {
        "name": "mock_finish_react",
        "id": "tc_fr",
        "args": {"result_type": "text", "answer": markdown, "stop_reason": ""},
    }
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="分析"), AIMessage(content="", tool_calls=[tc])],
        "react_round_idx": 1,
    }

    node = HookAwareToolNode([mock_finish_react])
    manager = _make_mock_manager()

    # ToolNode 在单元测试中需要完整 graph config，此处 mock super().ainvoke
    # 验证重点：HookAwareToolNode 不修改 ToolMessage content（Markdown 内容透传）
    finish_tool_msg = ToolMessage(content=markdown, tool_call_id="tc_fr", name="mock_finish_react")

    with (
        patch(
            "datacloud_analysis.orchestration.execution.hook_aware_tool_node.get_tool_hook_plugin_manager",
            return_value=manager,
        ),
        patch.object(ToolNode, "ainvoke", new_callable=AsyncMock) as sm,
    ):
        sm.return_value = {"messages": [finish_tool_msg]}
        result = await node.ainvoke(state, None)

    msgs = result.get("messages") or []
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert tool_msgs, "应产出至少一条 ToolMessage"
    assert markdown in tool_msgs[0].content, (
        f"ToolMessage 应保留完整 Markdown，实际 content[:200]={tool_msgs[0].content[:200]}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TC-HAN-6: should_continue 路由函数
# ═══════════════════════════════════════════════════════════════════════════════


def test_han6_should_continue_l2_no_tool_calls() -> None:
    """TC-HAN-6a: L2 — AIMessage 无 tool_calls → 返回 'respond'。"""
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="q"), AIMessage(content="直接回答", tool_calls=[])],
        "react_round_idx": 1,
    }
    assert should_continue(state) == "respond"


def test_han6_should_continue_l2_no_ai_message() -> None:
    """TC-HAN-6b: L2 — messages 中无 AIMessage → 返回 'respond'。"""
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="q")],
        "react_round_idx": 1,
    }
    assert should_continue(state) == "respond"


def test_han6_should_continue_l3_max_rounds() -> None:
    """TC-HAN-6c: L3 — react_round_idx >= max_rounds → 返回 'respond'。"""
    tc = {"name": "some_tool", "id": "x", "args": {}}
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="q"), AIMessage(content="", tool_calls=[tc])],
        "react_round_idx": _MAX_ROUNDS,
    }
    assert should_continue(state) == "respond"


def test_han6_should_continue_l3_max_rounds_exceeded_status() -> None:
    """TC-HAN-6d: L3 — execution_status=max_rounds_exceeded → 返回 'respond'。"""
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="q"), AIMessage(content="兜底", tool_calls=[])],
        "react_round_idx": 5,
        "execution_status": "max_rounds_exceeded",
    }
    assert should_continue(state) == "respond"


def test_han6_should_continue_with_tool_calls() -> None:
    """TC-HAN-6e: 有 tool_calls 且轮次未超 → 返回 'tools'。"""
    tc = {"name": "some_tool", "id": "x", "args": {}}
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="q"), AIMessage(content="", tool_calls=[tc])],
        "react_round_idx": 1,
    }
    assert should_continue(state) == "tools"


def test_han6_should_continue_finish_react_also_routes_to_tools() -> None:
    """TC-HAN-6f: finish_react tool_call 也应走 tools，不能在 should_continue 短路。"""
    tc = {"name": "finish_react", "id": "fr", "args": {"answer": "done"}}
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="q"), AIMessage(content="", tool_calls=[tc])],
        "react_round_idx": 1,
    }
    assert should_continue(state) == "tools", (
        "finish_react tool_call 必须走 tools 节点执行工具体，不能直接短路"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TC-HAN-7: after_tools_route 路由函数
# ═══════════════════════════════════════════════════════════════════════════════


def test_han7_after_tools_route_l1_finish_react() -> None:
    """TC-HAN-7a: L1 — 本轮 ToolMessage 含 finish_react → 返回 'finish_react_node'。"""
    state: dict[str, Any] = {
        "messages": [
            HumanMessage(content="q"),
            AIMessage(content="", tool_calls=[{"name": "finish_react", "id": "f1", "args": {}}]),
            ToolMessage(content="done", tool_call_id="f1", name="finish_react"),
        ],
        "react_round_idx": 1,
    }
    assert after_tools_route(state) == "finish_react_node"


def test_han7_after_tools_route_normal_tool() -> None:
    """TC-HAN-7b: 普通工具 ToolMessage → 返回 'agent'。"""
    state: dict[str, Any] = {
        "messages": [
            HumanMessage(content="q"),
            AIMessage(content="", tool_calls=[{"name": "query_ads", "id": "t1", "args": {}}]),
            ToolMessage(content="records...", tool_call_id="t1", name="query_ads"),
        ],
        "react_round_idx": 1,
    }
    assert after_tools_route(state) == "agent"


def test_han7_after_tools_route_mixed_tools_with_finish_react() -> None:
    """TC-HAN-7c: 本轮同时有普通工具和 finish_react ToolMessage → 返回 'finish_react_node'。"""
    state: dict[str, Any] = {
        "messages": [
            HumanMessage(content="q"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "query_ads", "id": "t1", "args": {}},
                    {"name": "finish_react", "id": "f1", "args": {}},
                ],
            ),
            ToolMessage(content="records", tool_call_id="t1", name="query_ads"),
            ToolMessage(content="done", tool_call_id="f1", name="finish_react"),
        ],
        "react_round_idx": 2,
    }
    assert after_tools_route(state) == "finish_react_node"


def test_han7_after_tools_route_no_tool_messages() -> None:
    """TC-HAN-7d: 本轮无 ToolMessage（仅 AIMessage）→ 返回 'agent'。"""
    state: dict[str, Any] = {
        "messages": [
            HumanMessage(content="q"),
            AIMessage(content="", tool_calls=[{"name": "some_tool", "id": "t1", "args": {}}]),
        ],
        "react_round_idx": 1,
    }
    assert after_tools_route(state) == "agent"
