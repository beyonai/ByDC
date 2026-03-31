from __future__ import annotations

from typing import Any, cast

import pytest

from datacloud_analysis.orchestration.execution_summary import (
    build_execution_summary,
    execution_summary_from_json,
    execution_summary_to_json,
)
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.orchestration.summary_persistence import get_execution_summary_store


class _FakeGatewayContext:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id


def test_execution_summary_model_contains_fixed_and_extensible_fields() -> None:
    state = cast(
        AgentState,
        {
            "agent_id": "A100",
            "user_query": "查询企业综合分析表前100条",
            "enriched_query": "查询企业综合分析表前100条",
            "intent": "查询企业综合分析表前100条",
            "query_mode": "online_query",
            "execution_status": "done",
            "resume_context": {"thread_id": "thread-1"},
            "todos": [
                {
                    "todo_id": "t1",
                    "goal": "查询企业综合分析表",
                    "status": "done",
                    "depends_on": [],
                    "required_tools": ["dws_enterprise_wide_query"],
                    "required_capabilities": [
                        {"capability_id": "dws_enterprise_wide_query", "capability_type": "tool"}
                    ],
                },
                {
                    "todo_id": "t2",
                    "goal": "生成汇总",
                    "status": "skipped",
                    "depends_on": ["t1"],
                    "required_tools": ["render_report"],
                },
            ],
            "results": [{"task_id": "t1", "data": {"records": []}}],
            "artifact_refs": [{"file_id": "F1", "file_url": "https://file/F1"}],
        },
    )

    summary = build_execution_summary(
        state,
        gateway_context=_FakeGatewayContext("session-123"),
        final_answer="结果已返回",
    )

    assert summary["model_version"] == "v1"
    assert summary["session_id"] == "session-123"
    assert summary["thread_id"] == "thread-1"
    assert summary["agent_id"] == "A100"
    assert summary["todo_total"] == 2
    assert summary["todo_done"] == 1
    assert summary["todo_skipped"] == 1
    assert summary["result_total"] == 1
    assert summary["final_answer_chars"] == len("结果已返回")
    assert summary["todos"][0]["todo_id"] == "t1"
    assert isinstance(summary["extensions"], dict)


def test_execution_summary_serialization_roundtrip() -> None:
    state = cast(
        AgentState,
        {
            "agent_id": "A1",
            "user_query": "q",
            "todos": [],
            "results": [],
        },
    )
    summary = build_execution_summary(state, gateway_context=_FakeGatewayContext("S1"))
    payload = execution_summary_to_json(summary)
    restored = execution_summary_from_json(payload)
    assert restored["model_version"] == summary["model_version"]
    assert restored["session_id"] == "S1"
    assert restored["todo_total"] == 0


@pytest.mark.asyncio
async def test_default_execution_summary_store_is_noop() -> None:
    store = get_execution_summary_store()
    ref = await store.persist(
        cast(
            Any,
            {
                "model_version": "v1",
                "generated_at": "2026-03-31T00:00:00+00:00",
                "session_id": "S1",
                "thread_id": "T1",
                "agent_id": "A1",
                "query_mode": "analysis",
                "user_query": "q",
                "enriched_query": "q",
                "intent": "q",
                "execution_status": "done",
                "todo_total": 0,
                "todo_done": 0,
                "todo_failed": 0,
                "todo_skipped": 0,
                "todo_blocked": 0,
                "result_total": 0,
                "todos": [],
                "artifact_refs": [],
                "final_answer_chars": 0,
                "extensions": {},
            },
        )
    )
    assert ref["status"] == "skipped"
    assert ref["storage"] == "noop"

