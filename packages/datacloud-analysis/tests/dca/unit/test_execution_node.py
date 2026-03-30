from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import anyio
import pytest

from datacloud_analysis.orchestration import execution as execution_module
from datacloud_analysis.orchestration.execution import _build_invocation_id, execution_node
from datacloud_analysis.orchestration.state import AgentState


@pytest.mark.asyncio
async def test_execution_uses_required_capabilities_for_effective_tools() -> None:
    state = cast(
        AgentState,
        {
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "required_capabilities": ["cap_a", "cap_b"],
                    "blocked_capabilities": ["cap_b"],
                }
            ],
            "query_mode": "chitchat",
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["active_tools"] == ["cap_a"]
    assert out["execution_status"] == "done"


@pytest.mark.asyncio
async def test_execution_supports_structured_required_capabilities() -> None:
    state = cast(
        AgentState,
        {
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "required_capabilities": [
                        {"capability_id": "cap_skill", "capability_type": "skill"},
                        {"capability_id": "cap_tool", "capability_type": "tool"},
                    ],
                    "blocked_capabilities": ["cap_tool"],
                }
            ],
            "query_mode": "chitchat",
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["active_tools"] == ["cap_skill"]
    assert out["execution_status"] == "done"


@pytest.mark.asyncio
async def test_execution_replans_when_effective_tools_empty(tmp_path: Path) -> None:
    state = cast(
        AgentState,
        {
            "workspace_dir": str(tmp_path),
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "required_capabilities": ["cap_a"],
                    "blocked_capabilities": ["cap_a"],
                    "required_tools": ["cap_a"],
                }
            ],
            "query_mode": "analysis",
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["execution_status"] == "replan"
    assert out["todos"][0]["status"] == "blocked"
    todo_md_path = str(out["todo_md_path"])
    path = anyio.Path(todo_md_path)
    assert await path.exists()
    assert "blocked" in await path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_execution_uses_default_capability_fallback_when_required_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_types: list[str] = []

    async def _execute_next_task(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], Any]:
        task = args[0]
        called_types.append(str(task.get("type")))
        return ({**task, "status": "done"}, {"ok": True})

    monkeypatch.setattr(execution_module, "execute_next_task", _execute_next_task)

    state = cast(
        AgentState,
        {
            "query_mode": "analysis",
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "goal": "fallback check",
                    "inputs": {},
                    "depends_on": [],
                }
            ],
            "results": [],
            "invocation_dedup": [],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})

    assert out["execution_status"] == "done"
    assert called_types == ["chat-response-tool"]


@pytest.mark.asyncio
async def test_execution_online_query_dedup_skips_duplicate_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _should_not_run(*_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], Any]:
        raise AssertionError("execute_next_task should be skipped by invocation_dedup")

    monkeypatch.setattr(execution_module, "execute_next_task", _should_not_run)

    invocation_id = _build_invocation_id(
        query_mode="online_query",
        target_tool="tool_a",
        tool_params={"query": "x"},
        todo_active_id="t_direct",
    )
    state = cast(
        AgentState,
        {
            "query_mode": "online_query",
            "target_tool": "tool_a",
            "tool_params": {"query": "x"},
            "invocation_dedup": [invocation_id],
            "todos": [
                {
                    "todo_id": "t_direct",
                    "status": "pending",
                    "required_tools": ["tool_a"],
                    "required_capabilities": ["tool_a"],
                    "inputs": {"query": "x"},
                }
            ],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["execution_status"] == "done"
    assert out["invocation_dedup"] == [invocation_id]
    assert out["todos"][0]["status"] == "done"
    assert out["execution_trace"][-1]["status"] == "dedup_skipped"


@pytest.mark.asyncio
async def test_execution_online_query_records_invocation_and_persists_todo_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []

    async def _execute_next_task(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], Any]:
        task = args[0]
        calls.append({"task_id": task.get("id")})
        return ({**task, "status": "done"}, {"records": [{"id": 1}], "meta": {"total": 1}})

    monkeypatch.setattr(execution_module, "execute_next_task", _execute_next_task)

    state = cast(
        AgentState,
        {
            "workspace_dir": str(tmp_path),
            "query_mode": "online_query",
            "target_tool": "tool_a",
            "tool_params": {"query": "x"},
            "todos": [
                {
                    "todo_id": "t_direct",
                    "status": "pending",
                    "required_tools": ["tool_a"],
                    "required_capabilities": ["tool_a"],
                    "inputs": {"query": "x"},
                }
            ],
            "invocation_dedup": [],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})

    assert calls == [{"task_id": "t_direct"}]
    assert out["execution_status"] == "done"
    assert len(out["invocation_dedup"]) == 1
    assert out["results"][0]["task_id"] == "t_direct"
    todo_md_path = str(out["todo_md_path"])
    path = anyio.Path(todo_md_path)
    assert await path.exists()
    assert "t_direct" in await path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_execution_runs_dependency_batches_in_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    call_order: list[str] = []

    async def _execute_next_task(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], Any]:
        task = args[0]
        task_id = str(task.get("id"))
        call_order.append(task_id)
        return ({**task, "status": "done"}, {"ok": task_id})

    monkeypatch.setattr(execution_module, "execute_next_task", _execute_next_task)

    state = cast(
        AgentState,
        {
            "workspace_dir": str(tmp_path),
            "query_mode": "analysis",
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "required_tools": ["tool_a"],
                    "required_capabilities": ["tool_a"],
                    "inputs": {"q": "1"},
                    "depends_on": [],
                },
                {
                    "todo_id": "t2",
                    "status": "pending",
                    "required_tools": ["tool_b"],
                    "required_capabilities": ["tool_b"],
                    "inputs": {"q": "2"},
                    "depends_on": ["t1"],
                },
            ],
            "results": [],
            "invocation_dedup": [],
        },
    )

    out1 = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out1["execution_status"] == "execution"
    assert call_order == ["t1"]

    next_state = cast(AgentState, {**state, **out1})
    out2 = await execution_node(next_state, {"configurable": {}}, default_tools={})
    assert out2["execution_status"] == "done"
    assert call_order == ["t1", "t2"]
