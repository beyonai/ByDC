from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from by_framework.core.protocol.commands import ResumeCommand
from by_framework.core.protocol.message_header import MessageHeader

from datacloud_service.worker import DataCloudWorker


@dataclass
class _AgentConfig:
    agent_id: str
    tools: dict[str, Any]
    prompts: dict[str, Any]


class _FakeContext:
    def __init__(self, configs: list[_AgentConfig]) -> None:
        self.session_id = "sess-1"
        self._configs = configs

    def list_agent_configs(self) -> list[_AgentConfig]:
        return self._configs

    async def emit_chunk(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def flush_to_history(self) -> None:
        return None

    async def check_cancelled(self) -> None:
        return None

    async def ask_user(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "waiting"}


@pytest.mark.asyncio
async def test_resume_reads_agent_id_and_conf_hash_from_header_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = DataCloudWorker(worker_id="worker-test")
    config = _AgentConfig(agent_id="agent-1", tools={"tool_a": object()}, prompts={"intent": "p"})
    context = _FakeContext([config])
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        worker,
        "_build_graph",
        lambda **_kwargs: object(),
    )

    async def _fake_stream_graph(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "done"}

    monkeypatch.setattr(worker, "_stream_graph", _fake_stream_graph)

    command = ResumeCommand(
        header=MessageHeader(
            message_id="m-1",
            session_id=context.session_id,
            trace_id="trace-1",
            metadata={
                "agent_id": "agent-1",
                "conf_hash": "meta-hash-001",
                "checkpoint_id": "ckpt-1",
                "checkpoint_ns": "ns-1",
            },
        ),
        content="fallback-content",
        reply_data="reply-text",
        extra_payload={},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "done"}
    assert captured["by_agent_id"] == "agent-1"
    assert captured["conf_hash"] == "meta-hash-001"
    assert captured["config"]["configurable"]["checkpoint_id"] == "ckpt-1"
    assert captured["config"]["configurable"]["checkpoint_ns"] == "ns-1"
    assert captured["graph_input"].resume == "reply-text"


@pytest.mark.asyncio
async def test_resume_keeps_empty_string_reply_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = DataCloudWorker(worker_id="worker-test")
    config = _AgentConfig(agent_id="agent-1", tools={"tool_a": object()}, prompts={"intent": "p"})
    context = _FakeContext([config])
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        worker,
        "_build_graph",
        lambda **_kwargs: object(),
    )

    async def _fake_stream_graph(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "done"}

    monkeypatch.setattr(worker, "_stream_graph", _fake_stream_graph)

    command = ResumeCommand(
        header=MessageHeader(
            message_id="m-2",
            session_id=context.session_id,
            trace_id="trace-2",
            metadata={"agent_id": "agent-1"},
        ),
        content="fallback-content",
        reply_data="",
        extra_payload={"agent_id": "agent-1"},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "done"}
    assert captured["graph_input"].resume == ""
