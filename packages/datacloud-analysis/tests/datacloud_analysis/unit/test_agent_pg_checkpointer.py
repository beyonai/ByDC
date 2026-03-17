"""Unit tests for PG checkpointer wiring.

Persistence is no longer managed inside agent.py.  The OpenGauss-compatible
checkpointer lives in datacloud_analysis.session.pg_opengauss and is injected by
the langgraph dev platform via langgraph.json / checkpointer.py.

These tests verify:
1. create_agent() compiles without error and returns a graph.
2. create_agent() does NOT embed a checkpointer (platform injects it externally).
3. pg_opengauss.get_checkpointer() raises RuntimeError when URI is missing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_agent_module() -> object:
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "datacloud-analysis"
        / "agent.py"
    )
    spec = importlib.util.spec_from_file_location("datacloud_analysis_hyphen_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_agent_returns_compiled_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_agent() should return a compiled graph (no checkpointer embedded)."""
    module = _load_agent_module()
    captured: dict[str, object] = {}

    def fake_init_chat_model(**_: object) -> object:
        return object()

    def fake_lc_create_agent(
        _model: object,
        tools: list[object] | None = None,
        *,
        system_prompt: str | None = None,
        checkpointer: object | None = None,
        **__: object,
    ) -> object:
        captured["tools"] = tools
        captured["system_prompt"] = system_prompt
        captured["checkpointer"] = checkpointer
        return SimpleNamespace(
            get_graph=lambda: SimpleNamespace(nodes={"__start__": None, "model": None})
        )

    monkeypatch.setattr(module, "init_chat_model", fake_init_chat_model)
    monkeypatch.setattr(module, "_lc_create_agent", fake_lc_create_agent)

    graph = module.create_agent()

    assert graph is not None
    # Checkpointer must NOT be embedded — the platform injects it via langgraph.json.
    assert captured.get("checkpointer") is None, (
        "create_agent() must not pass a checkpointer to _lc_create_agent(); "
        "persistence is managed externally via langgraph.json."
    )


def test_get_checkpointer_raises_when_uri_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """pg_opengauss.get_checkpointer() should raise RuntimeError if URI is unset."""
    import asyncio
    from datacloud_analysis.session.pg_opengauss import get_checkpointer

    monkeypatch.delenv("DATACLOUD_PG_CHECKPOINT_URI", raising=False)

    async def _run() -> None:
        async with get_checkpointer():
            pass

    with pytest.raises(RuntimeError, match="DATACLOUD_PG_CHECKPOINT_URI"):
        asyncio.run(_run())
