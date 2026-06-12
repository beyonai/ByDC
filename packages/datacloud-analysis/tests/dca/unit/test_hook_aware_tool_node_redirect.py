"""HookAwareToolNode redirect behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode


@pytest.mark.asyncio
async def test_hook_aware_tool_node_executes_redirect_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A before-hook redirect should execute the target tool with redirect params."""
    from datacloud_analysis.orchestration.execution import hook_aware_tool_node as module
    from datacloud_analysis.orchestration.execution.hook_aware_tool_node import HookAwareToolNode

    @tool
    async def query_demo(query: str, complex_conditions: list[str] | None = None) -> str:
        """Original query tool."""
        return "original"

    @tool
    async def data_query_demo(query: str, contextKnowledge: str = "") -> str:  # noqa: N803
        """Redirect target query tool."""
        return "redirected"

    manager = AsyncMock()
    manager.run_before = AsyncMock(
        return_value=(
            {
                "tool_name": "query_demo",
                "tool_params": {
                    "query": "original question",
                    "complex_conditions": ["top 30 percent"],
                },
            },
            {
                "action": "redirect",
                "tool": "data_query_demo",
                "params": {
                    "query": "original question",
                    "contextKnowledge": '{"resolved_params": {"limit": 20}}',
                },
            },
        )
    )
    manager.run_after = AsyncMock(return_value=({"tool_name": "data_query_demo"}, None))
    monkeypatch.setattr(module, "get_tool_hook_plugin_manager", lambda: manager)

    node = HookAwareToolNode([query_demo, data_query_demo])
    captured_states: list[dict[str, Any]] = []

    async def _fake_super(
        self_instance: Any, input_state: Any, config: Any = None, **kw: Any
    ) -> dict[str, Any]:
        captured_states.append(dict(input_state) if isinstance(input_state, dict) else {})
        return {
            "messages": [
                ToolMessage(
                    content="redirected",
                    name="data_query_demo",
                    tool_call_id="call_redirect_1",
                )
            ]
        }

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "query_demo",
                        "id": "call_redirect_1",
                        "args": {
                            "query": "original question",
                            "complex_conditions": ["top 30 percent"],
                        },
                    }
                ],
            )
        ]
    }

    with patch.object(ToolNode, "ainvoke", _fake_super):
        result = await node.ainvoke(state)

    assert len(captured_states) == 1
    patched_messages = captured_states[0]["messages"]
    patched_ai = patched_messages[-1]
    assert isinstance(patched_ai, AIMessage)
    assert patched_ai.tool_calls[0]["name"] == "data_query_demo"
    assert patched_ai.tool_calls[0]["args"] == {
        "query": "original question",
        "contextKnowledge": '{"resolved_params": {"limit": 20}}',
    }
    messages = result["messages"]
    assert messages[-1].name == "data_query_demo"
    assert messages[-1].tool_call_id == "call_redirect_1"
