from __future__ import annotations

from typing import cast

from datacloud_analysis.orchestration.end import node as end_module
from datacloud_analysis.orchestration.shared import ArtifactRef, PlanTask, TaskResult
from datacloud_analysis.orchestration.state import AgentState


def _plan_dict(todo_id: str, goal: str, depends_on: list[str] | None = None) -> dict[str, object]:
    return PlanTask(
        todo_id=todo_id,
        goal=goal,
        required_tools=["tool_a"],
        depends_on=depends_on or [],
        inputs_from={},
    ).to_dict()


def _result_dict(
    todo_id: str,
    status: str,
    *,
    blocked_by: str | None = None,
) -> dict[str, object]:
    return TaskResult(
        todo_id=todo_id,
        status=status,  # type: ignore[arg-type]
        result_meta={"count": 10} if status == "success" else {},
        artifact_refs=[
            ArtifactRef(todo_id=todo_id, path=f"/tmp/{todo_id}.json", name=f"{todo_id}.json")
        ]
        if status == "success"
        else [],
        blocked_by=blocked_by,
    ).to_dict()


def test_final_summary_builds_from_plan_and_results() -> None:
    state = cast(
        AgentState,
        {
            "planned_tasks": [_plan_dict("t1", "查询网格 Top10")],
            "task_queue": ["t1"],
            "results_list": [_result_dict("t1", "success")],
            "results_map": {"t1": _result_dict("t1", "success")},
        },
    )

    summary = end_module._ensure_final_summary(state)

    assert "tasks" in summary
    assert summary["stats"]["success"] == 1
    task_entry = summary["tasks"][0]
    assert task_entry["todo_id"] == "t1"
    assert task_entry["status"] == "success"
    assert summary["artifact_index"][0]["todo_id"] == "t1"


def test_final_summary_marks_blocked_and_failed_tasks() -> None:
    state = cast(
        AgentState,
        {
            "planned_tasks": [
                _plan_dict("t1", "查询网格 Top10"),
                _plan_dict("t2", "查询企业 Top10", depends_on=["t1"]),
            ],
            "task_queue": ["t1", "t2"],
            "results_list": [
                _result_dict("t1", "success"),
                _result_dict("t2", "blocked"),
            ],
            "results_map": {
                "t1": _result_dict("t1", "success"),
                "t2": _result_dict("t2", "blocked"),
            },
        },
    )

    summary = end_module._ensure_final_summary(state)

    assert summary["stats"]["blocked"] == 1
    combined = summary["combined_narrative"]
    assert "t2" in combined
    assert "未执行" in combined
