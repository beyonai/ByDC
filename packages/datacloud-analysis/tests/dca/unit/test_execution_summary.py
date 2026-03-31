from __future__ import annotations

from datacloud_analysis.orchestration.execution_summary import (
    build_execution_summary,
    load_latest_summary_by_session,
    persist_execution_summary,
)


def test_execution_summary_persist_and_load_by_session(tmp_path) -> None:
    summary = build_execution_summary(
        state={
            "agent_id": "10001",
            "query_mode": "analysis",
            "user_query": "查询企业综合分析表",
            "enriched_query": "查询企业综合分析表前100条",
            "intent": "查询企业综合分析表数据",
            "execution_status": "done",
            "results": [{"task_id": "t1"}],
            "todos": [{"todo_id": "t1", "status": "done"}],
            "todo_active_id": "",
            "artifact_refs": [],
        },
        history_content="分析完成",
        part23='{"code":0}',
        session_id="10004399",
    )

    persisted = persist_execution_summary(
        summary=summary,
        workspace_dir=None,
        session_id="10004399",
        workspace_root=str(tmp_path),
    )
    assert persisted["status"] == "ok"

    loaded = load_latest_summary_by_session(
        session_id="10004399",
        workspace_root=str(tmp_path),
    )
    assert loaded is not None
    assert loaded["session_id"] == "10004399"
    assert loaded["result_count"] == 1
    assert loaded["todo_stats"]["done"] == 1


def test_execution_summary_persist_skips_when_session_dir_unresolved() -> None:
    persisted = persist_execution_summary(
        summary={"session_id": "", "summary_version": "1.0"},
        workspace_dir=None,
        session_id="",
        workspace_root=None,
    )
    assert persisted["status"] == "skipped"
