from __future__ import annotations

from typing import Any, cast

import pytest
from langchain_core.messages import HumanMessage

from datacloud_analysis.orchestration.end import node as insight_module
from datacloud_analysis.orchestration.end.execution_summary import load_latest_summary_by_session
from datacloud_analysis.orchestration.end import insight_node
from datacloud_analysis.orchestration.state import AgentState


@pytest.mark.asyncio
async def test_insight_persist_summary_success(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATACLOUD_GATEWAY_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(insight_module, "init_chat_model", lambda *_args, **_kwargs: object())
    workspace_dir = tmp_path / "10004399" / "private" / "task-1"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    state = cast(
        AgentState,
        {
            "messages": [HumanMessage(content="你好")],
            "query_mode": "chitchat",
            "chitchat_reply": "你好，有什么可以帮你？",
            "results": [],
            "plan": [],
            "todos": [],
            "workspace_dir": str(workspace_dir),
            "resume_context": {"thread_id": "10004399"},
        },
    )

    out = await insight_node(state, gateway_context=None)
    assert out["messages"][0].content == "你好，有什么可以帮你？"
    assert out["execution_summary_persistence"]["status"] == "ok"

    loaded = load_latest_summary_by_session(
        session_id="10004399",
        workspace_root=str(tmp_path),
    )
    assert loaded is not None
    assert loaded["session_id"] == "10004399"


@pytest.mark.asyncio
async def test_insight_persist_summary_failure_does_not_break_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(insight_module, "init_chat_model", lambda *_args, **_kwargs: object())

    def _raise_persist(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("disk error")

    monkeypatch.setattr(insight_module, "persist_execution_summary", _raise_persist)

    state = cast(
        AgentState,
        {
            "messages": [HumanMessage(content="hello")],
            "query_mode": "chitchat",
            "chitchat_reply": "hello!",
            "results": [],
            "plan": [],
            "todos": [],
            "workspace_dir": None,
            "resume_context": {"thread_id": "10005555"},
        },
    )

    out = await insight_node(state, gateway_context=None)
    assert out["messages"][0].content == "hello!"
    assert out["execution_summary_persistence"]["status"] == "failed"
    assert "disk error" in out["execution_summary_persistence"]["error"]


