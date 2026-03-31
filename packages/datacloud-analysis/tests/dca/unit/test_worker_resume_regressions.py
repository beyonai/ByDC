from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from by_framework.core.protocol.commands import AskAgentCommand, ResumeCommand
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
        self.user_id = "u-1"
        self._configs = configs
        self.emitted: list[dict[str, Any]] = []
        self.flush_count = 0

    def list_agent_configs(self) -> list[_AgentConfig]:
        return self._configs

    async def emit_chunk(self, event: Any, **kwargs: Any) -> None:
        self.emitted.append(
            {
                "content": getattr(event, "content", ""),
                "metadata": getattr(event, "metadata", {}) or {},
                **kwargs,
            }
        )

    async def flush_to_history(self) -> None:
        self.flush_count += 1

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


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["hi", "你好"])
async def test_ask_chitchat_short_circuits_without_graph_execution(
    monkeypatch: pytest.MonkeyPatch,
    content: str,
) -> None:
    worker = DataCloudWorker(worker_id="worker-test")
    context = _FakeContext([])
    stream_called = False

    async def _never_called(**_kwargs: Any) -> dict[str, Any]:
        nonlocal stream_called
        stream_called = True
        return {"status": "done"}

    monkeypatch.setattr(worker, "_stream_graph", _never_called)

    command = AskAgentCommand(
        header=MessageHeader(message_id="m-ask-1", session_id=context.session_id, trace_id="trace-ask-1"),
        content=content,
        extra_payload={},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "done"}
    assert stream_called is False
    assert context.flush_count == 1
    assert any(item["metadata"].get("graph_nodes_executed") == 0 for item in context.emitted)


@pytest.mark.asyncio
async def test_ext_command_keeps_priority_over_chitchat_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = DataCloudWorker(worker_id="worker-test")
    context = _FakeContext([])
    called: dict[str, Any] = {}

    async def _fake_handle_ext_command(**kwargs: Any) -> tuple[bool, Any]:
        called.update(kwargs)
        return True, None

    worker.command_plugin_manager.handle_ext_command = _fake_handle_ext_command  # type: ignore[method-assign]

    async def _never_called(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("_stream_graph should not be called for handled ext_command")

    monkeypatch.setattr(worker, "_stream_graph", _never_called)

    command = AskAgentCommand(
        header=MessageHeader(message_id="m-ask-2", session_id=context.session_id, trace_id="trace-ask-2"),
        content="hello",
        extra_payload={"ext_params": {"command": "noop"}},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "done"}
    assert called["ext_params"] == {"command": "noop"}


@pytest.mark.asyncio
async def test_resume_idempotent_cache_prevents_duplicate_stream_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = DataCloudWorker(worker_id="worker-test")
    config = _AgentConfig(agent_id="agent-1", tools={"tool_a": object()}, prompts={"intent": "p"})
    context = _FakeContext([config])
    stream_call_count = 0

    monkeypatch.setattr(worker, "_build_graph", lambda **_kwargs: object())

    async def _fake_stream_graph(**_kwargs: Any) -> dict[str, Any]:
        nonlocal stream_call_count
        stream_call_count += 1
        return {"status": "done"}

    monkeypatch.setattr(worker, "_stream_graph", _fake_stream_graph)

    command = ResumeCommand(
        header=MessageHeader(
            message_id="m-idem-1",
            session_id=context.session_id,
            trace_id="trace-idem-1",
            metadata={
                "agent_id": "agent-1",
                "checkpoint_id": "ckpt-idem",
                "checkpoint_ns": "ns-idem",
            },
        ),
        content="fallback-content",
        reply_data={"confirm": "继续"},
        extra_payload={},
    )

    result_1 = await worker.process_command(command, context)
    result_2 = await worker.process_command(command, context)

    assert result_1 == {"status": "done"}
    assert result_2 == {"status": "done"}
    assert stream_call_count == 1
