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
async def test_execution_online_query_dedup_skips_duplicate_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _should_not_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("direct_tool_node should be skipped by invocation_dedup")

    monkeypatch.setattr(execution_module, "direct_tool_node", _should_not_run)

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
            }
        ],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["execution_status"] == "done"
    assert out["invocation_dedup"] == [invocation_id]
    assert out["execution_trace"][-1]["status"] == "dedup_skipped"


@pytest.mark.asyncio
async def test_execution_online_query_records_invocation_and_persists_todo_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []

    async def _direct_tool(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append({"ok": True})
        return {"plan": [{"id": "t_direct", "status": "done"}], "results": [{"task_id": "t_direct"}]}

    monkeypatch.setattr(execution_module, "direct_tool_node", _direct_tool)

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
            }
        ],
        "invocation_dedup": [],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})

    assert len(calls) == 1
    assert out["execution_status"] == "done"
    assert len(out["invocation_dedup"]) == 1
    assert out["execution_trace"][-1]["stage"] == "direct_tool"
    todo_md_path = str(out["todo_md_path"])
    path = anyio.Path(todo_md_path)
    assert await path.exists()
    assert "t_direct" in await path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_execution_merges_invocation_dedup_from_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _loop_node(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "plan": [{"id": "t1", "status": "done"}],
            "results": [{"task_id": "t1", "data": {"ok": True}}],
            "invocation_dedup_add": ["invocation-a"],
        }

    monkeypatch.setattr(execution_module, "loop_node", _loop_node)

    state = cast(
        AgentState,
        {
            "query_mode": "analysis",
            "todos": [{"todo_id": "t1", "status": "pending", "required_tools": ["tool_a"]}],
            "plan": [{"id": "t1", "status": "pending"}],
            "invocation_dedup": [],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})

    assert out["execution_status"] == "done"
    assert out["invocation_dedup"] == ["invocation-a"]
