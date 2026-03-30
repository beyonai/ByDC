from __future__ import annotations

from typing import Any, cast

import pytest

from datacloud_analysis.orchestration import loop as loop_module
from datacloud_analysis.orchestration.loop import _task_invocation_id, loop_node
from datacloud_analysis.orchestration.state import AgentState


@pytest.mark.asyncio
async def test_loop_node_skips_task_when_invocation_dedup_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _should_not_run(*_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], Any]:
        raise AssertionError("execute_next_task should be skipped by invocation_dedup")

    monkeypatch.setattr(loop_module, "execute_next_task", _should_not_run)

    task = {
        "id": "t1",
        "type": "tool_a",
        "status": "pending",
        "deps": [],
        "params": {"query": "x"},
        "description": "desc",
    }
    state = cast(
        AgentState,
        {
            "plan": [task],
            "results": [],
            "invocation_dedup": [_task_invocation_id(task)],
            "workspace_dir": None,
            "dynamic_tools": {},
        },
    )

    out = await loop_node(state, gateway_context=None, default_tools={})
    assert out["plan"][0]["status"] == "done"
    assert out["results"] == []
    assert out["invocation_dedup_add"] == []


@pytest.mark.asyncio
async def test_loop_node_records_invocation_for_newly_done_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run_task(*_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], Any]:
        return (
            {
                "id": "t1",
                "type": "tool_a",
                "status": "done",
                "deps": [],
                "params": {"query": "x"},
                "description": "desc",
            },
            {"ok": True},
        )

    monkeypatch.setattr(loop_module, "execute_next_task", _run_task)

    task = {
        "id": "t1",
        "type": "tool_a",
        "status": "pending",
        "deps": [],
        "params": {"query": "x"},
        "description": "desc",
    }
    state = cast(
        AgentState,
        {
            "plan": [task],
            "results": [],
            "invocation_dedup": [],
            "workspace_dir": None,
            "dynamic_tools": {},
        },
    )

    out = await loop_node(state, gateway_context=None, default_tools={})
    assert out["plan"][0]["status"] == "done"
    assert len(out["invocation_dedup_add"]) == 1
