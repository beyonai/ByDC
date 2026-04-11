"""Tests for refactored nodes: intend, react_loop, tool_wrapper, formatter, graph_builder."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# intend_node tests
# ---------------------------------------------------------------------------

class TestIntendNode:
    @pytest.mark.asyncio
    async def test_intend_routes_command(self) -> None:
        """intend_node should route JSON command messages to command_done path."""
        import json
        from langchain_core.messages import HumanMessage
        from datacloud_analysis.orchestration.intend.node import intend_node

        # Build a state with a command message
        cmd_msg = HumanMessage(content=json.dumps({"command": "get_file", "page": 1}))
        state: dict[str, Any] = {"messages": [cmd_msg]}
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(True, {"data": "ok"}))
            mock_factory.return_value = mock_mgr

            result = await intend_node(state, config)

        assert result["execution_status"] == "command_done"
        assert result["intent"] == "command"
        assert result["intent_source"] == "command"

    @pytest.mark.asyncio
    async def test_intend_routes_react_for_normal_query(self) -> None:
        """intend_node should route non-command query to execution with intent=react."""
        from langchain_core.messages import HumanMessage
        from datacloud_analysis.orchestration.intend.node import intend_node

        state: dict[str, Any] = {"messages": [HumanMessage(content="请查询本季度销售额")]}
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(False, None))
            mock_factory.return_value = mock_mgr

            result = await intend_node(state, config)

        assert result["execution_status"] == "execution"
        assert result["intent"] == "react"

    @pytest.mark.asyncio
    async def test_intend_uses_last_human_not_trailing_ai(self) -> None:
        """When messages end with AIMessage, user_query must be last HumanMessage."""
        from langchain_core.messages import AIMessage, HumanMessage
        from datacloud_analysis.orchestration.intend.node import intend_node

        state: dict[str, Any] = {
            "messages": [
                HumanMessage(content="first question"),
                AIMessage(content="long assistant answer"),
                HumanMessage(content="second question"),
                AIMessage(content="another ai tail"),
            ],
        }
        config: dict[str, Any] = {"configurable": {}}

        with patch(
            "datacloud_analysis.orchestration.intend.command_router.CommandPluginManager.from_defaults"
        ) as mock_factory:
            mock_mgr = AsyncMock()
            mock_mgr.handle_ext_command = AsyncMock(return_value=(False, None))
            mock_factory.return_value = mock_mgr

            result = await intend_node(state, config)

        assert result["user_query"] == "second question"


# ---------------------------------------------------------------------------
# run_react_loop tests
# ---------------------------------------------------------------------------

class TestReactLoop:
    @pytest.mark.asyncio
    async def test_stop_on_finish_tool(self) -> None:
        """L1 stop: LLM calls finish_react -> loop terminates."""
        from langchain_core.messages import AIMessage
        import datacloud_analysis.orchestration.execution.react_loop as rl_module
        from datacloud_analysis.orchestration.execution.react_loop import run_react_loop

        tool_call = {
            "name": "finish_react",
            "args": {"reason": "done", "answer": "42", "result_type": "text", "csv_file_path": ""},
            "id": "tc1",
        }
        ai_msg = AIMessage(content="", tool_calls=[tool_call])

        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.ainvoke = AsyncMock(return_value=ai_msg)

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        with patch.object(rl_module, "_build_llm", return_value=mock_llm):
            result = await run_react_loop(
                state={"user_query": "test", "messages": []},
                tools_list=[],
                system_prompt="sys",
                max_rounds=5,
            )

        assert result["react_final"]["stop_reason"] == "finish_tool"
        assert result["react_final"]["answer"] == "42"
        assert result["react_rounds"] == 1

    @pytest.mark.asyncio
    async def test_stop_on_no_tool_call(self) -> None:
        """L2 stop: LLM returns text without tool calls -> loop terminates."""
        from langchain_core.messages import AIMessage
        import datacloud_analysis.orchestration.execution.react_loop as rl_module
        from datacloud_analysis.orchestration.execution.react_loop import run_react_loop

        ai_msg = AIMessage(content="Direct answer here", tool_calls=[])

        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.ainvoke = AsyncMock(return_value=ai_msg)

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        with patch.object(rl_module, "_build_llm", return_value=mock_llm):
            result = await run_react_loop(
                state={"user_query": "test", "messages": []},
                tools_list=[],
                system_prompt="sys",
                max_rounds=5,
            )

        assert result["react_final"]["stop_reason"] == "no_tool_call"
        assert result["react_final"]["answer"] == "Direct answer here"

    @pytest.mark.asyncio
    async def test_multi_turn_state_messages_passed_to_llm(self) -> None:
        """Prior Human+AIMessage in state.messages must reach the LLM (not only user_query)."""
        from langchain_core.messages import AIMessage, HumanMessage
        import datacloud_analysis.orchestration.execution.react_loop as rl_module
        from datacloud_analysis.orchestration.execution.react_loop import run_react_loop

        ai_msg = AIMessage(content="grid A,B,C (prior answer)", tool_calls=[])

        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.ainvoke = AsyncMock(return_value=ai_msg)

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        prior = [
            HumanMessage(content="first question"),
            AIMessage(content="10 grids: g1..g10"),
            HumanMessage(content="list enterprises for first 3 grids"),
        ]
        with patch.object(rl_module, "_build_llm", return_value=mock_llm):
            await run_react_loop(
                state={
                    "user_query": "list enterprises for first 3 grids",
                    "messages": prior,
                },
                tools_list=[],
                system_prompt="sys",
                max_rounds=3,
            )

        call_args = mock_llm_with_tools.ainvoke.call_args
        assert call_args is not None
        passed = call_args[0][0]
        joined = " ".join(
            str(getattr(m, "content", m)) for m in passed if hasattr(m, "content")
        )
        assert "g1..g10" in joined
        assert "first 3 grids" in joined

    @pytest.mark.asyncio
    async def test_stop_on_max_rounds(self) -> None:
        """L3 stop: max rounds exceeded -> loop terminates with fallback."""
        from langchain_core.messages import AIMessage
        import datacloud_analysis.orchestration.execution.react_loop as rl_module
        from datacloud_analysis.orchestration.execution.react_loop import run_react_loop
        from langchain_core.tools import tool

        @tool("dummy_tool")
        async def dummy_tool(x: str) -> str:
            """Dummy."""
            return "ok"

        tool_call = {
            "name": "dummy_tool",
            "args": {"x": "val"},
            "id": "tc1",
        }
        ai_msg = AIMessage(content="", tool_calls=[tool_call])

        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.ainvoke = AsyncMock(return_value=ai_msg)

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm_with_tools

        with patch.object(rl_module, "_build_llm", return_value=mock_llm):
            with patch.object(rl_module, "dispatch_tool", new=AsyncMock(return_value=("tc1", "tool_result"))):
                result = await run_react_loop(
                    state={"user_query": "test", "messages": []},
                    tools_list=[dummy_tool],
                    system_prompt="sys",
                    max_rounds=2,
                )

        assert result["react_final"]["stop_reason"] == "max_rounds"
        assert result["react_rounds"] == 2


# ---------------------------------------------------------------------------
# dispatch_tool tests
# ---------------------------------------------------------------------------

class TestDispatchTool:
    @pytest.mark.asyncio
    async def test_finish_react_path(self) -> None:
        """dispatch_tool should return finish marker for finish_react tool."""
        from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

        tc = {
            "name": "finish_react",
            "args": {"reason": "done", "answer": "result", "result_type": "text", "csv_file_path": ""},
            "id": "id1",
        }
        _, result = await dispatch_tool(tc, {}, state={})
        assert result["__finish__"] is True
        assert result["answer"] == "result"

    @pytest.mark.asyncio
    async def test_ask_user_path(self) -> None:
        """dispatch_tool should call ask_user directly without hooks."""
        from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

        mock_tool = AsyncMock()
        mock_tool.name = "ask_user"
        mock_tool.ainvoke = AsyncMock(return_value="user answered")

        tc = {
            "name": "ask_user",
            "args": {"question": "confirm?", "reason": "need info"},
            "id": "id2",
        }
        _, result = await dispatch_tool(tc, {"ask_user": mock_tool}, state={})
        assert result == "user answered"

    @pytest.mark.asyncio
    async def test_normal_tool_path(self) -> None:
        """dispatch_tool should call regular tools via hook pipeline."""
        import datacloud_analysis.orchestration.execution.tool_wrapper as tw_module
        from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

        mock_tool = AsyncMock()
        mock_tool.name = "my_tool"
        mock_tool.ainvoke = AsyncMock(return_value={"data": "result"})

        tc = {
            "name": "my_tool",
            "args": {"reason": "because", "param": "val"},
            "id": "id3",
        }

        mock_hook_manager = MagicMock()
        mock_hook_manager.run_before = AsyncMock(
            return_value=({"tool_name": "my_tool", "tool_params": {"param": "val"}, "tool_output": None, "tool_error": None}, None)
        )
        mock_hook_manager.run_after = AsyncMock(
            return_value=({"tool_name": "my_tool", "tool_params": {"param": "val"}, "tool_output": {"data": "result"}, "tool_error": None}, None)
        )

        with patch.object(tw_module, "get_tool_hook_plugin_manager", return_value=mock_hook_manager):
            _, result = await dispatch_tool(
                tc,
                {"my_tool": mock_tool},
                state={"agent_id": "s1", "user_query": "q", "workspace_dir": None},
            )

        assert result == {"data": "result"}

    @pytest.mark.asyncio
    async def test_normal_tool_passes_workspace_dir_to_invocation_context(self) -> None:
        import datacloud_analysis.orchestration.execution.tool_wrapper as tw_module
        from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

        mock_tool = AsyncMock()
        mock_tool.name = "my_tool"
        mock_tool.ainvoke = AsyncMock(return_value={"data": "result"})

        tc = {
            "name": "my_tool",
            "args": {"reason": "because", "param": "val"},
            "id": "id4",
        }

        mock_hook_manager = MagicMock()
        mock_hook_manager.run_before = AsyncMock(
            return_value=(
                {"tool_name": "my_tool", "tool_params": {"param": "val"}, "tool_output": None, "tool_error": None},
                None,
            )
        )
        mock_hook_manager.run_after = AsyncMock(
            return_value=(
                {
                    "tool_name": "my_tool",
                    "tool_params": {"param": "val"},
                    "tool_output": {"data": "result"},
                    "tool_error": None,
                },
                None,
            )
        )

        captured_kwargs: dict[str, object] = {}

        class FakeInvocationContext:
            def __init__(self, **kwargs: object) -> None:
                captured_kwargs.update(kwargs)

            def __enter__(self) -> FakeInvocationContext:
                return self

            def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
                return None

        with patch.object(tw_module, "get_tool_hook_plugin_manager", return_value=mock_hook_manager):
            with patch("datacloud_data_sdk.context.InvocationContext", FakeInvocationContext):
                _, result = await dispatch_tool(
                    tc,
                    {"my_tool": mock_tool},
                    state={
                        "agent_id": "s1",
                        "user_query": "q",
                        "workspace_dir": "/tmp/datacloud/10011741/private/10011835",
                    },
                )

        assert result == {"data": "result"}
        assert captured_kwargs["workspace_dir"] == "/tmp/datacloud/10011741/private"


# ---------------------------------------------------------------------------
# format_result tests
# ---------------------------------------------------------------------------

class TestFormatResult:
    @pytest.mark.asyncio
    async def test_text_result(self) -> None:
        """format_result with text type should call _emit_text."""
        from datacloud_analysis.orchestration.respond.formatter import format_result

        mock_gw = AsyncMock()

        with patch(
            "datacloud_analysis.orchestration.respond.formatter._emit_text",
            new_callable=AsyncMock,
        ) as mock_emit:
            await format_result(
                {"result_type": "text", "answer": "hello"},
                gateway_context=mock_gw,
            )
        mock_emit.assert_called_once_with(mock_gw, "hello")

    @pytest.mark.asyncio
    async def test_csv_file_missing_path(self) -> None:
        """format_result with csv_file but empty path should emit error text."""
        from datacloud_analysis.orchestration.respond.formatter import format_result

        mock_gw = AsyncMock()

        with patch(
            "datacloud_analysis.orchestration.respond.formatter._emit_text",
            new_callable=AsyncMock,
        ) as mock_emit:
            await format_result(
                {"result_type": "csv_file", "csv_file_path": ""},
                gateway_context=mock_gw,
            )

        call_args = mock_emit.call_args[0][1]
        assert "CSV" in call_args

    @pytest.mark.asyncio
    async def test_none_gateway_is_noop(self) -> None:
        """format_result with None gateway should not raise."""
        from datacloud_analysis.orchestration.respond.formatter import format_result

        # Should not raise
        await format_result({"result_type": "text", "answer": "test"}, None)


# ---------------------------------------------------------------------------
# graph_builder test
# ---------------------------------------------------------------------------

class TestGraphBuilder:
    def test_build_analysis_graph_compiles(self) -> None:
        """build_analysis_graph should compile successfully with 3-node pipeline."""
        from datacloud_analysis.orchestration.graph_builder import build_analysis_graph

        graph = build_analysis_graph(prompts_overwrite={}, tools={})
        compiled = graph.compile()
        node_names = list(compiled.get_graph().nodes.keys())

        assert "intend" in node_names
        assert "execution" in node_names
        assert "respond" in node_names
        # Old nodes must not be present
        assert "knowledge_enhance" not in node_names
        assert "planning" not in node_names
        assert "end" not in node_names
