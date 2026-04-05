"""Unit tests for agent graph compilation and PG checkpointer helpers."""

from __future__ import annotations

import asyncio

import pytest


def test_create_agent_returns_compiled_graph() -> None:
    """``create_agent()`` should return a compiled LangGraph runnable."""
    from datacloud_analysis.agent import create_agent

    graph = create_agent()
    assert graph is not None
    nodes = list(graph.get_graph().nodes.keys())
    # Deep Agents architecture uses model/tools nodes
    assert "model" in nodes
    assert "tools" in nodes


def test_get_checkpointer_raises_when_uri_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """pg_opengauss.get_checkpointer() should raise RuntimeError if URI is unset."""
    from datacloud_analysis.session.pg_opengauss import get_checkpointer

    monkeypatch.delenv("DATACLOUD_PG_CHECKPOINT_URI", raising=False)

    async def _run() -> None:
        async with get_checkpointer():
            pass

    with pytest.raises(RuntimeError, match="DATACLOUD_PG_CHECKPOINT_URI"):
        asyncio.run(_run())
