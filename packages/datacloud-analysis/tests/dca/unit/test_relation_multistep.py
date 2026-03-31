from __future__ import annotations

from datacloud_analysis.orchestration.execution.node import _inject_params_from_deps
from datacloud_analysis.orchestration.planning.decomposer import (
    _should_split_relation_todo,
    split_relation_todo,
)


def test_split_relation_todo_generates_two_steps() -> None:
    todo = {
        "todo_id": "t_rel",
        "goal": "查询企业与园区之间关系",
        "required_tools": ["graph_relation_tool"],
        "required_capabilities": [{"capability_id": "graph_relation_tool", "capability_type": "tool"}],
        "term_context": [{"semantic_type": "relation"}],
        "depends_on": [],
        "inputs": {"limit": 10},
        "status": "pending",
    }

    assert _should_split_relation_todo(todo) is True
    split = split_relation_todo(todo)

    assert len(split) == 2
    assert split[0]["todo_id"] == "t_rel_locate"
    assert split[0]["required_tools"] == ["search_knowledge"]
    assert split[1]["todo_id"] == "t_rel_query"
    assert split[1]["depends_on"] == ["t_rel_locate"]
    assert split[1]["param_from_deps"] == {"t_rel_locate": ["subject_id", "object_id"]}
    assert split[1]["required_tools"] == ["graph_relation_tool"]


def test_split_relation_todo_skips_if_already_has_deps() -> None:
    todo = {
        "todo_id": "t_rel",
        "goal": "查询关系",
        "term_context": {"semantic_types": ["relation"]},
        "depends_on": ["t_prev"],
    }

    assert _should_split_relation_todo(todo) is False


def test_inject_params_from_deps_fills_subject_object() -> None:
    todo = {
        "todo_id": "t_rel_query",
        "inputs": {"limit": 100},
        "param_from_deps": {"t_rel_locate": ["subject_id", "object_id"]},
    }
    completed = {
        "t_rel_locate": {
            "output": {"subject_id": "S001", "object_id": "O002", "name": "ignored"}
        }
    }

    out = _inject_params_from_deps(todo, completed)
    assert out["inputs"]["limit"] == 100
    assert out["inputs"]["subject_id"] == "S001"
    assert out["inputs"]["object_id"] == "O002"


def test_inject_params_from_deps_noop_if_no_param_from_deps() -> None:
    todo = {"todo_id": "t_rel_query", "inputs": {"limit": 100}}
    completed = {"t_rel_locate": {"output": {"subject_id": "S001", "object_id": "O002"}}}

    out = _inject_params_from_deps(todo, completed)
    assert out == todo

