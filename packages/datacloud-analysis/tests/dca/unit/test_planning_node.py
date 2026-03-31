from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from datacloud_analysis.orchestration.planning import node as planning_module
from datacloud_analysis.orchestration.planning import planning_node
from datacloud_analysis.orchestration.state import AgentState


@pytest.mark.asyncio
async def test_planning_normalizes_online_query_to_agent_delegate_for_delegate_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_planning_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "delegate this task",
            "query_mode": "online_query",
            "target_tool": "delegate_tool",
            "tool_params": {"k": 1},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    monkeypatch.setattr(planning_module, "resolve_planning_context", _fake_planning_context)

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
    async def _fake_planning_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "run direct query",
            "query_mode": "agent_delegate",
            "target_tool": "query_tool",
            "tool_params": {"k": 2},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    monkeypatch.setattr(planning_module, "resolve_planning_context", _fake_planning_context)

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
    async def _fake_planning_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "run direct query",
            "query_mode": "online_query",
            "target_tool": "query_tool",
            "tool_params": {},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    monkeypatch.setattr(planning_module, "resolve_planning_context", _fake_planning_context)

    async def _query_tool(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    state = cast(AgentState, {"user_query": "q3", "workspace_dir": str(tmp_path)})
    out = await planning_node(state, default_tools={"query_tool": _query_tool})

    assert out["todo_md_path"] is not None


@pytest.mark.asyncio
async def test_planning_emits_structured_required_capabilities_for_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_planning_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "run skill",
            "query_mode": "online_query",
            "target_tool": "skill.normalize",
            "tool_params": {"x": 1},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    monkeypatch.setattr(planning_module, "resolve_planning_context", _fake_planning_context)

    async def _skill_tool(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    _skill_tool._is_skill_capability = True  # type: ignore[attr-defined]

    state = cast(AgentState, {"user_query": "q4"})
    out = await planning_node(state, default_tools={"skill.normalize": _skill_tool})

    assert out["todos"][0]["required_capabilities"] == [
        {"capability_id": "skill.normalize", "capability_type": "skill"}
    ]


@pytest.mark.asyncio
async def test_planning_blocks_unavailable_capability_from_dag_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_planning_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "run analysis plan",
            "query_mode": "analysis",
            "target_tool": "",
            "tool_params": {},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    async def _fake_decompose_analysis_plan(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "plan": [
                {
                    "id": "t_missing",
                    "type": "not_registered_tool",
                    "description": "missing capability",
                    "status": "pending",
                    "deps": [],
                    "params": {},
                }
            ]
        }

    monkeypatch.setattr(planning_module, "resolve_planning_context", _fake_planning_context)
    monkeypatch.setattr(
        planning_module,
        "decompose_analysis_plan",
        _fake_decompose_analysis_plan,
    )

    state = cast(AgentState, {"user_query": "q5"})
    out = await planning_node(state, default_tools={})
    todo = out["todos"][0]

    assert todo["required_tools"] == ["not_registered_tool"]
    assert todo["blocked_tools"] == ["not_registered_tool"]
    assert todo["required_capabilities"] == [
        {"capability_id": "not_registered_tool", "capability_type": "tool"}
    ]
    assert todo["blocked_capabilities"] == [
        {"capability_id": "not_registered_tool", "capability_type": "tool"}
    ]


@pytest.mark.asyncio
async def test_planning_preserves_term_hints_from_knowledge_enhance_in_term_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_planning_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "query with hints",
            "query_mode": "online_query",
            "target_tool": "query_tool",
            "tool_params": {},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    monkeypatch.setattr(planning_module, "resolve_planning_context", _fake_planning_context)

    async def _query_tool(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    state = cast(
        AgentState,
        {
            "user_query": "q6",
            "term_hints": [
                {
                    "mention": "企业综合分析表",
                    "normalized_term": "企业综合分析表",
                    "term_id": "T100",
                    "confidence": 0.95,
                    "source": "knowledge_match",
                    "semantic_type": "view",
                },
            ],
        },
    )
    out = await planning_node(state, default_tools={"query_tool": _query_tool})
    term_context = out["todos"][0]["term_context"]

    assert len(term_context) == 1
    assert term_context[0]["mention"] == "企业综合分析表"
    assert term_context[0]["semantic_type"] == "view"


@pytest.mark.asyncio
async def test_planning_agent_delegate_todo_injects_default_delegate_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_planning_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "delegate task",
            "query_mode": "agent_delegate",
            "target_tool": "delegate_tool",
            "tool_params": {"content": "query text"},
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    monkeypatch.setattr(planning_module, "resolve_planning_context", _fake_planning_context)

    async def _delegate_tool(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    _delegate_tool._is_agent_delegate = True  # type: ignore[attr-defined]

    state = cast(AgentState, {"user_query": "q7"})
    out = await planning_node(state, default_tools={"delegate_tool": _delegate_tool})
    todo_inputs = out["todos"][0]["inputs"]

    assert out["query_mode"] == "agent_delegate"
    assert todo_inputs["delegate_policy"] == {"mode": "sync", "wait_for_reply": True}


@pytest.mark.asyncio
async def test_planning_compat_fallback_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_planning_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "intent": "state only planning",
            "query_mode": "analysis",
            "target_tool": "",
            "tool_params": {},
            "confirmed_terms": [],
            "ambiguous_terms": [],
            "planning_context_source": "state",
        }

    async def _fake_decompose_analysis_plan(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "plan": [
                {
                    "id": "t1",
                    "type": "chat-response-tool",
                    "description": "reply",
                    "status": "pending",
                    "deps": [],
                    "params": {"message": "ok"},
                }
            ]
        }

    monkeypatch.setattr(planning_module, "resolve_planning_context", _fake_planning_context)
    monkeypatch.setattr(
        planning_module,
        "decompose_analysis_plan",
        _fake_decompose_analysis_plan,
    )

    state = cast(AgentState, {"user_query": "q8"})
    out = await planning_node(state, default_tools={})

    assert out["planning_context_source"] == "state"
    assert out["todos"][0]["required_tools"] == ["chat-response-tool"]

