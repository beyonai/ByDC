from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import anyio
import pytest

from datacloud_analysis.orchestration.execution import node as execution_module
from datacloud_analysis.orchestration.execution.node import _build_invocation_id, execution_node
from datacloud_analysis.orchestration.execution.sandbox_executor import ToolRuntime
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
async def test_execution_normalizes_invocation_dedup_stably() -> None:
    state = cast(
        AgentState,
        {
            "query_mode": "chitchat",
            "invocation_dedup": ["dup", " dup ", "", "dup", "next"],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["invocation_dedup"] == ["dup", "next"]


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

    async def _invoke_with_callbacks(
        self: ToolRuntime, task: dict[str, Any], _state: Any
    ) -> tuple[dict[str, Any], Any]:
        called_types.append(str(task.get("type")))
        return ({**task, "status": "done"}, {"ok": True})

    monkeypatch.setattr(execution_module.ToolRuntime, "invoke_with_callbacks", _invoke_with_callbacks)

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
    async def _should_not_run(
        self: ToolRuntime, _task: dict[str, Any], _state: Any
    ) -> tuple[dict[str, Any], Any]:
        raise AssertionError("invoke_with_callbacks should be skipped by invocation_dedup")

    monkeypatch.setattr(execution_module.ToolRuntime, "invoke_with_callbacks", _should_not_run)

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

    async def _invoke_with_callbacks(
        self: ToolRuntime, task: dict[str, Any], _state: Any
    ) -> tuple[dict[str, Any], Any]:
        calls.append({"task_id": task.get("id")})
        return ({**task, "status": "done"}, {"records": [{"id": 1}], "meta": {"total": 1}})

    monkeypatch.setattr(execution_module.ToolRuntime, "invoke_with_callbacks", _invoke_with_callbacks)

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

    async def _invoke_with_callbacks(
        self: ToolRuntime, task: dict[str, Any], _state: Any
    ) -> tuple[dict[str, Any], Any]:
        task_id = str(task.get("id"))
        call_order.append(task_id)
        return ({**task, "status": "done"}, {"ok": task_id})

    monkeypatch.setattr(execution_module.ToolRuntime, "invoke_with_callbacks", _invoke_with_callbacks)

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


@pytest.mark.asyncio
async def test_execution_records_react_round_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _select_react_capability(**_kwargs: Any) -> dict[str, Any]:
        return {
            "capability_id": "tool_a",
            "source": "llm_function_call",
            "reason": "best_match",
            "tool_call_id": "call_1",
        }

    async def _invoke_with_callbacks(
        self: ToolRuntime, task: dict[str, Any], _state: Any
    ) -> tuple[dict[str, Any], Any]:
        return ({**task, "status": "done"}, {"ok": True})

    monkeypatch.setattr(execution_module, "select_react_capability", _select_react_capability)
    monkeypatch.setattr(execution_module.ToolRuntime, "invoke_with_callbacks", _invoke_with_callbacks)

    state = cast(
        AgentState,
        {
            "query_mode": "analysis",
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "goal": "react round test",
                    "required_capabilities": ["tool_a"],
                    "required_tools": ["tool_a"],
                    "inputs": {"q": "x"},
                    "depends_on": [],
                }
            ],
            "results": [],
            "invocation_dedup": [],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})

    assert out["execution_status"] == "done"
    react_events = [x for x in out["execution_trace"] if x.get("stage") == "react_round"]
    assert react_events
    assert react_events[0]["detail"]["tool_call_id"] == "call_1"
    assert react_events[0]["detail"]["selection_source"] == "llm_function_call"


@pytest.mark.asyncio
async def test_execution_level3_interrupt_confirmed_replans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _select_react_capability(**_kwargs: Any) -> dict[str, Any]:
        return {"capability_id": "tool_a", "source": "fallback", "reason": "test", "tool_call_id": None}

    async def _invoke_with_callbacks(
        self: ToolRuntime, task: dict[str, Any], _state: Any
    ) -> tuple[dict[str, Any], Any]:
        return ({**task, "status": "failed", "error": "boom"}, {"error": "boom"})

    interrupt_payload: dict[str, Any] = {}

    def _fake_interrupt(payload: dict[str, Any]) -> dict[str, Any]:
        interrupt_payload.update(payload)
        return {"confirm": "继续"}

    monkeypatch.setattr(execution_module, "select_react_capability", _select_react_capability)
    monkeypatch.setattr(execution_module.ToolRuntime, "invoke_with_callbacks", _invoke_with_callbacks)
    monkeypatch.setattr(execution_module, "interrupt", _fake_interrupt)

    state = cast(
        AgentState,
        {
            "query_mode": "analysis",
            "level3_failure_threshold": 1,
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "goal": "trigger level3",
                    "required_capabilities": ["tool_a"],
                    "required_tools": ["tool_a"],
                    "inputs": {},
                    "depends_on": [],
                }
            ],
            "results": [],
            "invocation_dedup": [],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})

    assert out["execution_status"] == "replan"
    assert interrupt_payload["reason_code"] == "LEVEL3_GLOBAL_REPLAN_CONFIRM"
    assert interrupt_payload["todo_active_id"] == "t1"
    assert interrupt_payload["react_step_id"] == "t1"
    assert interrupt_payload["pending_capability"] == "tool_a"
    assert interrupt_payload["interrupt_reason"] == "failed_threshold_reached"
    assert any(
        x.get("stage") == "level3_replan" and x.get("status") == "confirmed"
        for x in out["execution_trace"]
    )


@pytest.mark.asyncio
async def test_execution_level3_interrupt_cancelled_marks_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _select_react_capability(**_kwargs: Any) -> dict[str, Any]:
        return {"capability_id": "tool_a", "source": "fallback", "reason": "test", "tool_call_id": None}

    async def _invoke_with_callbacks(
        self: ToolRuntime, task: dict[str, Any], _state: Any
    ) -> tuple[dict[str, Any], Any]:
        return ({**task, "status": "failed", "error": "boom"}, {"error": "boom"})

    monkeypatch.setattr(execution_module, "select_react_capability", _select_react_capability)
    monkeypatch.setattr(execution_module.ToolRuntime, "invoke_with_callbacks", _invoke_with_callbacks)
    monkeypatch.setattr(execution_module, "interrupt", lambda _payload: {"confirm": "取消"})

    state = cast(
        AgentState,
        {
            "query_mode": "analysis",
            "level3_failure_threshold": 1,
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "goal": "trigger level3 cancel",
                    "required_capabilities": ["tool_a"],
                    "required_tools": ["tool_a"],
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
    assert "取消整体重规划" in str(out.get("final_answer") or "")


@pytest.mark.asyncio
async def test_execution_level3_interrupt_for_dependency_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interrupt_payload: dict[str, Any] = {}

    def _fake_interrupt(payload: dict[str, Any]) -> dict[str, Any]:
        interrupt_payload.update(payload)
        return {"confirm": "继续"}

    monkeypatch.setattr(execution_module, "interrupt", _fake_interrupt)

    state = cast(
        AgentState,
        {
            "query_mode": "analysis",
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "goal": "deadlock t1",
                    "required_capabilities": ["tool_a"],
                    "required_tools": ["tool_a"],
                    "inputs": {},
                    "depends_on": ["t2"],
                },
                {
                    "todo_id": "t2",
                    "status": "pending",
                    "goal": "deadlock t2",
                    "required_capabilities": ["tool_b"],
                    "required_tools": ["tool_b"],
                    "inputs": {},
                    "depends_on": ["t1"],
                },
            ],
            "results": [],
            "invocation_dedup": [],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})

    assert out["execution_status"] == "replan"
    assert interrupt_payload["reason_code"] == "LEVEL3_GLOBAL_REPLAN_CONFIRM"
    assert interrupt_payload["interrupt_reason"] == "dependency_deadlock"
    assert any(
        x.get("stage") == "level3_replan"
        and x.get("status") == "interrupt"
        and x.get("detail", {}).get("reason") == "dependency_deadlock"
        for x in out["execution_trace"]
    )


@pytest.mark.asyncio
async def test_execution_semantic_type_prioritizes_query_like_capability_for_object(
) -> None:
    state = cast(
        AgentState,
        {
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "required_capabilities": ["act_tool", "query_tool"],
                    "blocked_capabilities": [],
                    "term_context": [{"semantic_type": "object"}],
                }
            ],
            "query_mode": "chitchat",
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["active_tools"][0] == "query_tool"


@pytest.mark.asyncio
async def test_execution_semantic_type_prioritizes_action_capability_for_action() -> None:
    state = cast(
        AgentState,
        {
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "required_capabilities": ["query_tool", "operate_action_tool"],
                    "blocked_capabilities": [],
                    "term_context": [{"semantic_type": "action"}],
                }
            ],
            "query_mode": "chitchat",
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["active_tools"][0] == "operate_action_tool"


@pytest.mark.asyncio
async def test_execution_semantic_type_prioritizes_query_like_capability_for_view() -> None:
    state = cast(
        AgentState,
        {
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "required_capabilities": ["update_action_tool", "enterprise_view_query"],
                    "blocked_capabilities": [],
                    "term_context": [{"semantic_type": "view"}],
                }
            ],
            "query_mode": "chitchat",
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["active_tools"][0] == "enterprise_view_query"


@pytest.mark.asyncio
async def test_execution_semantic_type_prioritizes_relation_capability_for_relation() -> None:
    state = cast(
        AgentState,
        {
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "required_capabilities": ["enterprise_query_tool", "graph_relation_tool"],
                    "blocked_capabilities": [],
                    "term_context": [{"semantic_type": "relation"}],
                }
            ],
            "query_mode": "chitchat",
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["active_tools"][0] == "graph_relation_tool"


@pytest.mark.asyncio
async def test_execution_builds_todos_from_planned_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_execute(task: dict[str, Any], state: AgentState, runtime: ToolRuntime) -> tuple[dict[str, Any], Any]:
        return {**task, "status": "done"}, {"rows": 5}

    monkeypatch.setattr(execution_module, "execute_next_task", _fake_execute)

    state = cast(
        AgentState,
        {
            "planned_tasks": [
                {
                    "todo_id": "t_plan",
                    "goal": "run plan",
                    "required_tools": ["cap_tool"],
                    "depends_on": [],
                    "inputs_from": {},
                    "required_inputs": {},
                }
            ],
            "task_queue": ["t_plan"],
            "results_list": [],
            "results_map": {},
            "query_mode": "analysis",
        },
    )
    out = await execution_node(
        state,
        {"configurable": {}},
        default_tools={"cap_tool": object()},
    )
    assert state["results_list"][0]["status"] == "success"
    assert out["execution_status"] in {"execution", "done"}


@pytest.mark.asyncio
async def test_execution_blocks_missing_required_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    state = cast(
        AgentState,
        {
            "planned_tasks": [
                {
                    "todo_id": "t_missing",
                    "goal": "need dep",
                    "required_tools": ["cap_tool"],
                    "depends_on": [],
                    "inputs_from": {"grid_ids": "t_prev.result_meta.grid_ids"},
                    "required_inputs": {"grid_ids": True},
                }
            ],
            "task_queue": ["t_missing"],
            "results_list": [],
            "results_map": {},
            "query_mode": "analysis",
        },
    )

    out = await execution_node(
        state,
        {"configurable": {}},
        default_tools={"cap_tool": object()},
    )
    assert state["results_list"][0]["status"] == "blocked"


@pytest.mark.asyncio
async def test_execution_inputs_from_artifact_missing_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(execution_module, "interrupt", lambda _payload: {"confirm": "取消"})
    missing_artifact = tmp_path / "missing.json"
    upstream_result = {
        "todo_id": "t_prev",
        "status": "success",
        "result_meta": {},
        "artifact_refs": [
            {
                "todo_id": "t_prev",
                "path": str(missing_artifact),
                "name": "missing.json",
            }
        ],
    }
    state = cast(
        AgentState,
        {
            "planned_tasks": [
                {
                    "todo_id": "t_missing",
                    "goal": "need artifact",
                    "required_tools": ["cap_tool"],
                    "depends_on": [],
                    "inputs_from": {"artifact_path": "t_prev.artifact_refs[0].path"},
                    "required_inputs": {"artifact_path": True},
                }
            ],
            "task_queue": ["t_missing"],
            "results_list": [upstream_result],
            "results_map": {"t_prev": upstream_result},
            "query_mode": "analysis",
        },
    )

    out = await execution_node(
        state,
        {"configurable": {}},
        default_tools={"cap_tool": object()},
    )

    assert out["execution_status"] in {"execution", "done"}
    injected = next(entry for entry in state["results_list"] if entry["todo_id"] == "t_missing")
    assert injected["status"] == "failed"
    assert injected["error_detail"]["code"] == "artifact_not_found"


@pytest.mark.asyncio
async def test_execution_records_task_result_for_skipped_todo() -> None:
    blocked_caps = list(execution_module._DEFAULT_CAPABILITY_FALLBACK_ORDER)  # type: ignore[attr-defined]
    state = cast(
        AgentState,
        {
            "query_mode": "analysis",
            "todos": [
                {
                    "todo_id": "t_skip",
                    "status": "pending",
                    "required_capabilities": [],
                    "blocked_capabilities": blocked_caps,
                    "depends_on": [],
                }
            ],
            "results": [],
            "invocation_dedup": [],
        },
    )
    out = await execution_node(state, {"configurable": {}}, default_tools={})
    assert out["todos"][0]["status"] == "skipped"
    recorded = next(entry for entry in state["results_list"] if entry["todo_id"] == "t_skip")
    assert recorded["status"] == "blocked"


@pytest.mark.asyncio
async def test_execution_logs_ambiguous_terms_without_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[str] = []

    class _GatewayContext:
        async def emit_chunk(self, event: Any, **_kwargs: Any) -> None:
            emitted.append(str(getattr(event, "content", event)))

    async def _invoke_with_callbacks(
        self: ToolRuntime, task: dict[str, Any], _state: Any
    ) -> tuple[dict[str, Any], Any]:
        return ({**task, "status": "done"}, {"ok": True})

    def _unexpected_interrupt(_payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("interrupt should not be called for ambiguous terms")

    monkeypatch.setattr(execution_module.ToolRuntime, "invoke_with_callbacks", _invoke_with_callbacks)
    monkeypatch.setattr(execution_module, "interrupt", _unexpected_interrupt)

    state = cast(
        AgentState,
        {
            "query_mode": "analysis",
            "ambiguous_terms": [
                {
                    "mention": "活跃用户",
                    "candidates": [{"term_name": "DAU"}, {"term_name": "MAU"}],
                }
            ],
            "confirmed_terms": [
                {
                    "mention": "GMV",
                    "term_name": "GMV",
                    "term_id": "t1",
                    "confidence": 0.95,
                }
            ],
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "goal": "run despite ambiguity",
                    "required_capabilities": ["tool_a"],
                    "required_tools": ["tool_a"],
                    "inputs": {},
                    "depends_on": [],
                }
            ],
            "results": [],
            "invocation_dedup": [],
        },
    )

    out = await execution_node(
        state,
        {"configurable": {"gateway_context": _GatewayContext()}},
        default_tools={},
    )

    assert out["execution_status"] == "done"
    assert out["ambiguous_terms"] == []
    assert out["clarify_needed"] is False
    assert any("活跃用户" in chunk for chunk in emitted)
    assert any("DAU" in chunk for chunk in emitted)

