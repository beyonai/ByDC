from __future__ import annotations

import pytest

from datacloud_analysis.orchestration.shared.contracts import PlanTask, TaskResult
from datacloud_analysis.orchestration.state import (
    ensure_blocked_task,
    ensure_multitask_defaults,
    get_planned_tasks,
    get_task_queue,
    get_task_result_map,
    get_task_results,
    set_planned_tasks,
    set_task_queue,
    upsert_task_result,
)


def test_ensure_multitask_defaults_creates_independent_containers() -> None:
    state_a: dict[str, object] = {}
    ensure_multitask_defaults(state_a)
    state_a_plans = state_a["planned_tasks"]
    state_b: dict[str, object] = {}
    ensure_multitask_defaults(state_b)
    assert state_b["planned_tasks"] == []
    assert state_a_plans is not state_b["planned_tasks"]


def test_planned_tasks_round_trip_serialization() -> None:
    plan = PlanTask(
        todo_id="t1",
        goal="collect data",
        required_tools=["tool.alpha"],
        depends_on=["bootstrap"],
        inputs_from={"grid_ids": "t0.result_meta.grid_ids"},
        required_inputs={"grid_ids": True},
    )
    state: dict[str, object] = {}
    set_planned_tasks(state, [plan])
    restored = get_planned_tasks(state)
    assert len(restored) == 1
    assert restored[0].todo_id == "t1"
    assert restored[0].inputs_from["grid_ids"] == "t0.result_meta.grid_ids"


def test_task_queue_round_trip() -> None:
    state: dict[str, object] = {}
    set_task_queue(state, [" t1 ", "", "t2"])
    assert get_task_queue(state) == ["t1", "t2"]


def test_upsert_task_result_syncs_list_and_map() -> None:
    state: dict[str, object] = {}
    ensure_multitask_defaults(state)
    result = TaskResult(todo_id="t1", status="success", result_meta={"rows": 10})
    upsert_task_result(state, result)
    assert len(state["results_list"]) == 1
    assert state["results_map"]["t1"]["result_meta"]["rows"] == 10  # type: ignore[index]
    restored = get_task_result_map(state)
    assert restored["t1"].status == "success"


def test_upsert_task_result_replaces_existing_entry() -> None:
    state: dict[str, object] = {}
    ensure_multitask_defaults(state)
    first = TaskResult(todo_id="t1", status="success")
    upsert_task_result(state, first)
    second = TaskResult(todo_id="t1", status="failed")
    upsert_task_result(state, second)
    results = get_task_results(state)
    assert len(results) == 1
    assert results[0].status == "failed"


def test_ensure_blocked_task_prefills_missing_dependency() -> None:
    state: dict[str, object] = {}
    ensure_multitask_defaults(state)
    task = PlanTask(todo_id="t2", goal="blocked goal")
    ensure_blocked_task(state, task)
    results = get_task_results(state)
    assert results[0].status == "blocked"
    assert results[0].blocked_by == "missing_dependency"


def test_get_task_results_skips_invalid_entries() -> None:
    state: dict[str, object] = {}
    ensure_multitask_defaults(state)
    state["results_list"].append({"todo_id": "t3", "status": "invalid"})  # type: ignore[index]
    assert get_task_results(state) == []


def test_task_result_from_dict_rejects_invalid_status() -> None:
    with pytest.raises(ValueError):
        TaskResult.from_dict({"todo_id": "t1", "status": "pending"})


def test_plan_task_requires_todo_id() -> None:
    with pytest.raises(ValueError):
        PlanTask.from_dict({"goal": "missing id"})
