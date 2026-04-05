"""End-to-end-style unit tests for the OQL query workflow via DataCloudWorker.

These tests simulate the complete request flow:
  AskAgentCommand → process_command → _build_graph → _stream_graph → done/waiting

All external dependencies (LLM, DB) are mocked. The tests verify that:
  1. OQL query flow produces a "done" result after streaming
  2. Action execution flow works end-to-end
  3. Interrupt/resume cycle completes correctly
  4. Messages are passed through correctly to the graph

Marked with no marker → runs as unit tests (no DB / LLM required).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from by_framework.core.protocol.commands import AskAgentCommand, ResumeCommand
from by_framework.core.protocol.message_header import MessageHeader
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from unittest.mock import MagicMock
from datacloud_service.worker import DataCloudWorker


# ---------------------------------------------------------------------------
# Fake infrastructure
# ---------------------------------------------------------------------------


@dataclass
class _AgentConfig:
    agent_id: str
    tools: dict[str, Any] = field(default_factory=dict)
    prompts: dict[str, Any] = field(default_factory=dict)


class _FakeContext:
    """Minimal AgentContext stub for process_command tests."""

    def __init__(self, configs: list[_AgentConfig] | None = None) -> None:
        self.session_id = "sess-e2e"
        self.user_id = "u-e2e"
        self._configs = configs or []
        self.emitted: list[dict[str, Any]] = []
        self.flush_count = 0
        self.ask_user_calls: list[Any] = []
        self._sub_step_counter = 0

    def list_agent_configs(self) -> list[_AgentConfig]:
        return self._configs

    async def emit_chunk(self, event: Any, **kwargs: Any) -> None:
        self.emitted.append(
            {
                "content": getattr(event, "content", event if isinstance(event, str) else ""),
                "metadata": getattr(event, "metadata", {}) or {},
                **kwargs,
            }
        )

    async def flush_to_history(self) -> None:
        self.flush_count += 1

    async def check_cancelled(self) -> None:
        return None

    async def ask_user(self, event: Any, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.ask_user_calls.append(event)
        return {"status": "waiting"}

    @asynccontextmanager
    async def sub_step(self, title: str, **_kwargs: Any):
        self._sub_step_counter += 1
        yield f"msg-{self._sub_step_counter}", f"parent-{self._sub_step_counter}"


@dataclass
class _FakeSnapshot:
    interrupts: list[Any] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeInterrupt:
    value: Any


def _no_checkpointer_graph(events: list[dict[str, Any]]) -> Any:
    """Graph without checkpointer — aget_state is never called."""

    class _Graph:
        checkpointer = None

        async def astream_events(self, _input: Any, **_kw: Any):
            for e in events:
                yield e

        async def aget_state(self, _config: Any) -> None:
            return None

    return _Graph()


def _checkpointed_graph(
    events: list[dict[str, Any]], snapshot: _FakeSnapshot
) -> Any:
    """Graph with a fake checkpointer that returns the given snapshot."""

    class _Graph:
        checkpointer = MagicMock(spec=BaseCheckpointSaver)

        async def astream_events(self, _input: Any, **_kw: Any):
            for e in events:
                yield e

        async def aget_state(self, _config: Any) -> _FakeSnapshot:
            return snapshot

    return _Graph()


# ---------------------------------------------------------------------------
# Tests: complete query flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oql_query_flow_messages_passed_to_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AskAgentCommand content is converted to HumanMessage and passed to the graph."""
    worker = DataCloudWorker(worker_id="w-e2e")
    config = _AgentConfig(agent_id="agent-oql")
    context = _FakeContext([config])

    received_inputs: list[Any] = []

    class _CapturingGraph:
        checkpointer = None

        async def astream_events(self, input_val: Any, **_kw: Any):
            received_inputs.append(input_val)
            return
            yield

        async def aget_state(self, _config: Any) -> None:
            return None

    monkeypatch.setattr(worker, "_build_graph", lambda **_kw: _CapturingGraph())

    command = AskAgentCommand(
        header=MessageHeader(
            message_id="m-oql-1",
            session_id=context.session_id,
            trace_id="trace-oql-1",
            metadata={"agent_id": "agent-oql"},
        ),
        content="查询本月销售额",
        extra_payload={"agent_id": "agent-oql"},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "done"}
    # Graph received input with messages containing user text
    assert len(received_inputs) == 1
    inp = received_inputs[0]
    assert "messages" in inp
    user_messages = [m for m in inp["messages"] if isinstance(m, HumanMessage)]
    assert any("销售额" in m.content for m in user_messages)


@pytest.mark.asyncio
async def test_oql_query_flow_normal_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full AskAgentCommand → stream → done flow returns {"status": "done"}."""
    worker = DataCloudWorker(worker_id="w-e2e")
    config = _AgentConfig(agent_id="agent-oql")
    context = _FakeContext([config])

    graph = _no_checkpointer_graph(
        [
            {"event": "on_chat_model_end", "data": {}, "metadata": {"langgraph_node": "model"}},
        ]
    )

    monkeypatch.setattr(worker, "_build_graph", lambda **_kw: graph)

    command = AskAgentCommand(
        header=MessageHeader(
            message_id="m-oql-2",
            session_id=context.session_id,
            trace_id="trace-oql-2",
            metadata={"agent_id": "agent-oql"},
        ),
        content="分析订单趋势",
        extra_payload={"agent_id": "agent-oql"},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "done"}
    assert context.flush_count == 1


@pytest.mark.asyncio
async def test_oql_action_flow_with_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When graph is interrupted, process_command returns {"status": "waiting"}."""
    worker = DataCloudWorker(worker_id="w-e2e")
    config = _AgentConfig(agent_id="agent-oql")
    context = _FakeContext([config])

    interrupt = _FakeInterrupt(
        value={"prompt": "确认执行更新操作？", "reason_code": "user_confirm"}
    )
    snapshot = _FakeSnapshot(
        interrupts=[interrupt],
        config={"configurable": {"checkpoint_id": "ckpt-oql", "checkpoint_ns": "ns-oql"}},
    )
    graph = _checkpointed_graph([], snapshot)

    monkeypatch.setattr(worker, "_build_graph", lambda **_kw: graph)

    command = AskAgentCommand(
        header=MessageHeader(
            message_id="m-oql-3",
            session_id=context.session_id,
            trace_id="trace-oql-3",
            metadata={"agent_id": "agent-oql"},
        ),
        content="更新商品名称",
        extra_payload={"agent_id": "agent-oql"},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "waiting"}
    assert len(context.ask_user_calls) == 1
    assert context.flush_count == 0  # no flush on interrupt


@pytest.mark.asyncio
async def test_resume_after_interrupt_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ResumeCommand after interrupt completes normally."""
    worker = DataCloudWorker(worker_id="w-e2e")
    config = _AgentConfig(agent_id="agent-oql")
    context = _FakeContext([config])

    # Resume graph has no interrupts — completes normally
    snapshot = _FakeSnapshot(
        interrupts=[],
        config={"configurable": {"checkpoint_id": "ckpt-resume", "checkpoint_ns": "ns-resume"}},
    )
    graph = _checkpointed_graph(
        [{"event": "on_chat_model_end", "data": {}, "metadata": {"langgraph_node": "model"}}],
        snapshot,
    )

    monkeypatch.setattr(worker, "_build_graph", lambda **_kw: graph)

    command = ResumeCommand(
        header=MessageHeader(
            message_id="m-resume-1",
            session_id=context.session_id,
            trace_id="trace-resume-1",
            metadata={
                "agent_id": "agent-oql",
                "checkpoint_id": "ckpt-resume",
                "checkpoint_ns": "ns-resume",
            },
        ),
        content="确认",
        reply_data="确认执行",
        extra_payload={},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "done"}
    assert context.flush_count == 1


@pytest.mark.asyncio
async def test_pipeline_flow_multi_node_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-step pipeline: planning → model → tools events all processed."""
    worker = DataCloudWorker(worker_id="w-e2e")
    config = _AgentConfig(agent_id="agent-pipeline")
    context = _FakeContext([config])

    events = [
        # Knowledge enhance phase
        {"event": "on_chat_model_end", "data": {}, "metadata": {"langgraph_node": "model"}},
        # Planning phase
        {"event": "on_chat_model_end", "data": {}, "metadata": {"langgraph_node": "planning"}},
        # Tool execution
        {"event": "on_tool_start", "data": {}, "metadata": {"langgraph_node": "tools"}},
        {"event": "on_tool_end", "data": {}, "metadata": {"langgraph_node": "tools"}},
        # Final model call
        {"event": "on_chat_model_end", "data": {}, "metadata": {"langgraph_node": "model"}},
    ]
    graph = _no_checkpointer_graph(events)

    monkeypatch.setattr(worker, "_build_graph", lambda **_kw: graph)

    command = AskAgentCommand(
        header=MessageHeader(
            message_id="m-pipeline-1",
            session_id=context.session_id,
            trace_id="trace-pipeline-1",
            metadata={"agent_id": "agent-pipeline"},
        ),
        content="生成销售分析报告",
        extra_payload={"agent_id": "agent-pipeline"},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "done"}
    # planning phase should trigger a sub_step
    assert context._sub_step_counter >= 2  # initial + planning


@pytest.mark.asyncio
async def test_chitchat_short_circuit_does_not_invoke_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simple chitchat content ('你好') bypasses graph execution entirely."""
    worker = DataCloudWorker(worker_id="w-e2e")
    context = _FakeContext([])
    graph_invoked = False

    async def _fake_stream_graph(**_kw: Any) -> dict[str, Any]:
        nonlocal graph_invoked
        graph_invoked = True
        return {"status": "done"}

    monkeypatch.setattr(worker, "_stream_graph", _fake_stream_graph)

    command = AskAgentCommand(
        header=MessageHeader(
            message_id="m-chitchat-1",
            session_id=context.session_id,
            trace_id="trace-chitchat-1",
        ),
        content="你好",
        extra_payload={},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "done"}
    assert graph_invoked is False
    # Should have emitted a direct reply
    assert context.flush_count == 1


@pytest.mark.asyncio
async def test_oql_flow_with_history_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-turn: history messages are prepended before current user message."""
    worker = DataCloudWorker(worker_id="w-e2e")
    config = _AgentConfig(agent_id="agent-oql")
    context = _FakeContext([config])

    received_inputs: list[Any] = []

    class _CapturingGraph:
        checkpointer = None

        async def astream_events(self, input_val: Any, **_kw: Any):
            received_inputs.append(input_val)
            return
            yield

        async def aget_state(self, _config: Any) -> None:
            return None

    monkeypatch.setattr(worker, "_build_graph", lambda **_kw: _CapturingGraph())

    # Simulate history loading returning previous turns as LangChain messages
    async def _fake_history(*_a: Any, **_kw: Any) -> list:
        return [
            HumanMessage(content="上月销售多少？"),
            AIMessage(content="上月销售额为100万。"),
        ]

    import datacloud_service.worker as worker_mod  # noqa: PLC0415

    monkeypatch.setattr(worker_mod, "_load_recent_history_messages", _fake_history)

    command = AskAgentCommand(
        header=MessageHeader(
            message_id="m-history-1",
            session_id=context.session_id,
            trace_id="trace-history-1",
            metadata={"agent_id": "agent-oql"},
        ),
        content="那今月呢？",
        extra_payload={"agent_id": "agent-oql"},
    )

    result = await worker.process_command(command, context)

    assert result == {"status": "done"}
    assert len(received_inputs) == 1
    messages = received_inputs[0]["messages"]
    # History messages should be prepended
    contents = [m.content for m in messages]
    assert any("上月销售多少" in c for c in contents)
    assert any("今月" in c for c in contents)
