"""Tests for graph compile policy with mandatory checkpointer fail-fast."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_compile_graph_with_policy_raises_when_uninitialized() -> None:
    """Uninitialized checkpointer should always fail fast."""
    from datacloud_analysis.orchestration.graph_compile_policy import compile_graph_with_policy

    fake_graph = MagicMock()
    fake_graph.compile = MagicMock()

    with (
        patch(
            "datacloud_analysis.orchestration.graph_compile_policy.get_checkpointer",
            side_effect=RuntimeError("not initialized"),
        ),
        pytest.raises(RuntimeError, match="Checkpointer is required"),
    ):
        compile_graph_with_policy(fake_graph, caller_name="test")

    fake_graph.compile.assert_not_called()


def test_compile_graph_with_policy_uses_checkpointer_when_available() -> None:
    """Available checkpointer should be passed into graph.compile()."""
    from datacloud_analysis.orchestration.graph_compile_policy import compile_graph_with_policy

    fake_graph = MagicMock()
    fake_compiled = object()
    fake_graph.compile = MagicMock(return_value=fake_compiled)
    fake_checkpointer = object()

    with patch(
        "datacloud_analysis.orchestration.graph_compile_policy.get_checkpointer",
        return_value=fake_checkpointer,
    ):
        compiled = compile_graph_with_policy(fake_graph, caller_name="test")

    assert compiled is fake_compiled
    fake_graph.compile.assert_called_once_with(checkpointer=fake_checkpointer)
