from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from datacloud_analysis.orchestration import planning as planning_module
from datacloud_analysis.orchestration.planning import planning_node
from datacloud_analysis.orchestration.state import AgentState


@pytest.mark.asyncio
async def test_planning_normalizes_online_query_to_agent_delegate_for_delegate_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_intent_node(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "delegate this task",
            "query_mode": "online_query",
            "target_tool": "delegate_tool",
            "tool_params": {"k": 1},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    monkeypatch.setattr(planning_module, "intent_node", _fake_intent_node)

    async def _delegate_tool(content: str, **_kwargs: Any) -> dict[str, Any]:
        return {"content": content}

    _delegate_tool._is_agent_delegate = True  # type: ignore[attr-defined]
    state = cast(AgentState, {"user_query": "q1"})
    out = await planning_node(state, default_tools={"delegate_tool": _delegate_tool})

    assert out["query_mode"] == "agent_delegate"
    assert out["todos"][0]["required_tools"] == ["delegate_tool"]


@pytest.mark.asyncio
async def test_planning_normalizes_agent_delegate_to_online_query_for_non_delegate_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_intent_node(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "run direct query",
            "query_mode": "agent_delegate",
            "target_tool": "query_tool",
            "tool_params": {"k": 2},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    monkeypatch.setattr(planning_module, "intent_node", _fake_intent_node)

    async def _query_tool(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    state = cast(AgentState, {"user_query": "q2"})
    out = await planning_node(state, default_tools={"query_tool": _query_tool})

    assert out["query_mode"] == "online_query"
    assert out["todos"][0]["required_tools"] == ["query_tool"]


@pytest.mark.asyncio
async def test_planning_persists_todo_md_to_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _fake_intent_node(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "run direct query",
            "query_mode": "online_query",
            "target_tool": "query_tool",
            "tool_params": {},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    monkeypatch.setattr(planning_module, "intent_node", _fake_intent_node)

    async def _query_tool(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    state = cast(AgentState, {"user_query": "q3", "workspace_dir": str(tmp_path)})
    out = await planning_node(state, default_tools={"query_tool": _query_tool})

    assert out["todo_md_path"] is not None


@pytest.mark.asyncio
async def test_planning_emits_structured_required_capabilities_for_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_intent_node(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "run skill",
            "query_mode": "online_query",
            "target_tool": "skill.normalize",
            "tool_params": {"x": 1},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    monkeypatch.setattr(planning_module, "intent_node", _fake_intent_node)

    async def _skill_tool(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    _skill_tool._is_skill_capability = True  # type: ignore[attr-defined]

    state = cast(AgentState, {"user_query": "q4"})
    out = await planning_node(state, default_tools={"skill.normalize": _skill_tool})

    assert out["todos"][0]["required_capabilities"] == [
        {"capability_id": "skill.normalize", "capability_type": "skill"}
    ]
