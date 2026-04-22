"""Integration-level checks for checkpointer compile policy wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_create_agent_fail_fast_when_checkpointer_uninitialized() -> None:
    """create_agent should fail-fast if checkpointer is not initialized."""
    from datacloud_analysis.agent import create_agent

    fake_graph = MagicMock()
    fake_graph.compile = MagicMock()
    fake_graph.get_graph.return_value.nodes = {}

    with (
        patch(
            "datacloud_analysis.agent.build_analysis_graph",
            return_value=fake_graph,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_compile_policy.get_checkpointer",
            side_effect=RuntimeError("not initialized"),
        ),
        pytest.raises(RuntimeError, match="Checkpointer is required"),
    ):
        create_agent()

    fake_graph.compile.assert_not_called()


@pytest.mark.asyncio
async def test_run_agent_fail_fast_when_checkpointer_uninitialized() -> None:
    """run_agent should fail-fast if checkpointer is not initialized."""
    from datacloud_analysis.orchestration.runner import run_agent

    fake_graph = MagicMock()
    fake_graph.compile = MagicMock()

    class _FakeTaskPaths:
        class _Inputs:
            parent = "D:/tmp/ws"

        inputs = _Inputs()

    async def _collect() -> None:
        async for _ in run_agent("hi", _FakeTaskPaths(), {"configurable": {}}):
            pass

    with (
        patch(
            "datacloud_analysis.orchestration.runner.build_analysis_graph",
            return_value=fake_graph,
        ),
        patch(
            "datacloud_analysis.orchestration.graph_compile_policy.get_checkpointer",
            side_effect=RuntimeError("not initialized"),
        ),
        pytest.raises(RuntimeError, match="Checkpointer is required"),
    ):
        await _collect()

    fake_graph.compile.assert_not_called()
