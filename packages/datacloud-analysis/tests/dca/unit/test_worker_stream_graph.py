"""Unit tests for DataCloudWorker._stream_graph with Deep Agents architecture.

These tests verify that the worker correctly handles streaming events from
a Deep Agents compiled graph, including:
- Normal completion flow (done)
- Interrupt/HITL flow (waiting)
- No-checkpointer fallback
- Heartbeat cancellation
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from by_framework.core.protocol.commands import AskAgentCommand
from by_framework.core.protocol.message_header import MessageHeader
from datacloud_service.worker import DataCloudWorker


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


class _FakeContext:
    def __init__(self) -> None:
        self.session_id = "sess-test"
        self.user_id = "u-test"
        self.emitted: list[dict[str, Any]] = []
        self.flush_count = 0
        self.ask_user_calls: list[Any] = []
        self._sub_step_counter = 0

    def list_agent_configs(self) -> list:
        return []

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


def _make_fake_graph(
    events: list[dict[str, Any]],
    *,
    snapshot: Any = None,
) -> Any:
    """Build a fake compiled graph whose astream_events yields the given events
    and aget_state returns the given snapshot."""

    class _FakeGraph:
        checkpointer = None  # no checkpointer by default

        async def astream_events(self, _input: Any, **_kw: Any):
            for evt in events:
                yield evt

        async def aget_state(self, _config: Any) -> Any:
            return snapshot

    return _FakeGraph()


def _make_fake_graph_with_checkpointer(
    events: list[dict[str, Any]],
    *,
    snapshot: Any = None,
) -> Any:
    """Fake graph that pretends to have a real checkpointer."""
    graph = _make_fake_graph(events, snapshot=snapshot)
    # Fake a real checkpointer (non-None, not True)
    from langgraph.checkpoint.base import BaseCheckpointSaver

    graph.checkpointer = MagicMock(spec=BaseCheckpointSaver)
    return graph


@dataclass
class _FakeSnapshot:
    interrupts: list[Any] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeInterrupt:
    value: Any


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_graph_normal_completion_returns_done() -> None:
    """_stream_graph returns {"status": "done"} on normal completion with flush."""
    events = [
        {"event": "on_chat_model_stream", "data": {}, "metadata": {}},
        {"event": "on_chat_model_end", "data": {}, "metadata": {"langgraph_node": "model"}},
    ]
    worker = DataCloudWorker(worker_id="w-test")
    ctx = _FakeContext()
    graph = _make_fake_graph(events, snapshot=None)

    result = await worker._stream_graph(
        target_graph=graph,
        graph_input={"messages": []},
        config={"configurable": {"thread_id": "t-1"}},
        context=ctx,
        by_agent_id="agent-1",
        conf_hash="hash-1",
    )

    assert result == {"status": "done"}
    assert ctx.flush_count == 1


@pytest.mark.asyncio
async def test_stream_graph_with_checkpointer_no_interrupts_returns_done() -> None:
    """With checkpointer but no interrupts, _stream_graph returns {"status": "done"}."""
    events: list[dict[str, Any]] = []
    snapshot = _FakeSnapshot(interrupts=[], config={"configurable": {"checkpoint_id": "ckpt-1"}})
    worker = DataCloudWorker(worker_id="w-test")
    ctx = _FakeContext()
    graph = _make_fake_graph_with_checkpointer(events, snapshot=snapshot)

    result = await worker._stream_graph(
        target_graph=graph,
        graph_input={"messages": []},
        config={"configurable": {"thread_id": "t-1"}},
        context=ctx,
        by_agent_id="agent-1",
        conf_hash="hash-1",
    )

    assert result == {"status": "done"}
    assert ctx.flush_count == 1


@pytest.mark.asyncio
async def test_stream_graph_interrupt_triggers_ask_user_and_returns_waiting() -> None:
    """An interrupted graph snapshot causes ask_user call and returns {"status": "waiting"}."""
    events: list[dict[str, Any]] = []
    interrupt = _FakeInterrupt(value={"prompt": "确认继续？", "reason_code": "human_confirm"})
    snapshot = _FakeSnapshot(
        interrupts=[interrupt],
        config={"configurable": {"checkpoint_id": "ckpt-2", "checkpoint_ns": "ns-2"}},
    )
    worker = DataCloudWorker(worker_id="w-test")
    ctx = _FakeContext()
    graph = _make_fake_graph_with_checkpointer(events, snapshot=snapshot)

    result = await worker._stream_graph(
        target_graph=graph,
        graph_input={"messages": []},
        config={"configurable": {"thread_id": "t-1"}},
        context=ctx,
        by_agent_id="agent-1",
        conf_hash="hash-1",
    )

    assert result == {"status": "waiting"}
    assert len(ctx.ask_user_calls) == 1
    # ask_user event should carry checkpoint metadata
    ask_event = ctx.ask_user_calls[0]
    assert ask_event.metadata["checkpoint_id"] == "ckpt-2"
    assert ask_event.metadata["checkpoint_ns"] == "ns-2"
    assert ctx.flush_count == 0  # no flush on interrupt


@pytest.mark.asyncio
async def test_stream_graph_agent_delegate_interrupt_returns_waiting_without_ask_user() -> None:
    """AGENT_DELEGATE_WAIT interrupt is an internal wait — no ask_user call."""
    events: list[dict[str, Any]] = []
    interrupt = _FakeInterrupt(
        value={
            "prompt": "Delegating to sub-agent",
            "reason_code": "AGENT_DELEGATE_WAIT",
            "call_agent_kwargs": {},
        }
    )
    snapshot = _FakeSnapshot(
        interrupts=[interrupt],
        config={"configurable": {"checkpoint_id": "ckpt-3", "checkpoint_ns": "ns-3"}},
    )
    worker = DataCloudWorker(worker_id="w-test")
    ctx = _FakeContext()
    graph = _make_fake_graph_with_checkpointer(events, snapshot=snapshot)

    result = await worker._stream_graph(
        target_graph=graph,
        graph_input={"messages": []},
        config={"configurable": {"thread_id": "t-1"}},
        context=ctx,
        by_agent_id="agent-1",
        conf_hash="hash-1",
    )

    assert result == {"status": "waiting"}
    assert len(ctx.ask_user_calls) == 0  # no ask_user for delegate wait


@pytest.mark.asyncio
async def test_stream_graph_no_checkpointer_logs_and_returns_done() -> None:
    """Without checkpointer, _stream_graph skips aget_state and returns done."""
    events = [
        {"event": "on_chat_model_end", "data": {}, "metadata": {"langgraph_node": "model"}},
    ]
    worker = DataCloudWorker(worker_id="w-test")
    ctx = _FakeContext()
    graph = _make_fake_graph(events, snapshot=None)
    # graph.checkpointer is None — no checkpointer

    result = await worker._stream_graph(
        target_graph=graph,
        graph_input={"messages": []},
        config={"configurable": {"thread_id": "t-1"}},
        context=ctx,
        by_agent_id="agent-1",
        conf_hash="hash-1",
    )

    assert result == {"status": "done"}


@pytest.mark.asyncio
async def test_stream_graph_passes_messages_only_input() -> None:
    """Verify that a Deep Agents-style graph_input with only 'messages' key works."""
    from langchain_core.messages import HumanMessage

    captured_inputs: list[Any] = []
    events: list[dict[str, Any]] = []

    class _CapturingGraph:
        checkpointer = None

        async def astream_events(self, input_val: Any, **_kw: Any):
            captured_inputs.append(input_val)
            # Yield nothing — no events
            return
            yield  # make it an async generator

        async def aget_state(self, _config: Any) -> None:
            return None

    worker = DataCloudWorker(worker_id="w-test")
    ctx = _FakeContext()

    graph_input = {"messages": [HumanMessage(content="查询销售数据")]}

    await worker._stream_graph(
        target_graph=_CapturingGraph(),
        graph_input=graph_input,
        config={"configurable": {"thread_id": "t-messages-only"}},
        context=ctx,
        by_agent_id="agent-1",
        conf_hash="hash-1",
    )

    assert len(captured_inputs) == 1
    assert "messages" in captured_inputs[0]
    assert captured_inputs[0]["messages"][0].content == "查询销售数据"


@pytest.mark.asyncio
async def test_stream_graph_legacy_graph_input_extra_fields_are_tolerated() -> None:
    """Worker's legacy graph_input with 30+ fields doesn't break Deep Agents graph."""
    from langchain_core.messages import HumanMessage

    received_inputs: list[Any] = []

    class _CapturingGraph:
        checkpointer = None

        async def astream_events(self, input_val: Any, **_kw: Any):
            received_inputs.append(input_val)
            return
            yield

        async def aget_state(self, _config: Any) -> None:
            return None

    worker = DataCloudWorker(worker_id="w-test")
    ctx = _FakeContext()

    # Simulate the full legacy graph_input that worker.py builds
    legacy_graph_input = {
        "messages": [HumanMessage(content="查询月度销售额")],
        "agent_id": "agent-1",
        "agent_name": "销售分析",
        "workspace_dir": "/tmp/workspace",
        "user_query": "",
        "enriched_query": "",
        "plan": [],
        "todos": [],
        "todo_md": "",
        "todo_md_path": "",
        "results": [],
        "execution_status": "",
        "todo_active_id": "",
        "todo_tool_plan": [],
        "active_tools": [],
        "execution_trace": [],
        "invocation_dedup": [],
        "final_answer": "",
        "artifact_refs": [],
        "execution_summary": None,
        "execution_summary_persistence": None,
        "resume_context": {},
        "intent": "",
        "clarify_needed": False,
        "query_mode": "analysis",
        "chitchat_reply": None,
        "target_tool": "",
        "tool_params": {},
        "term_hints": [],
        "knowledge_snippets": [],
        "knowledge_payload": {},
        "concept_terms": [],
        "confirmed_terms": [],
        "ambiguous_terms": [],
        "session_alias_map": {},
        "planned_tasks": [],
        "task_queue": [],
        "results_list": [],
        "results_map": {},
        "final_summary": {},
    }

    result = await worker._stream_graph(
        target_graph=_CapturingGraph(),
        graph_input=legacy_graph_input,
        config={"configurable": {"thread_id": "t-legacy"}},
        context=ctx,
        by_agent_id="agent-1",
        conf_hash="hash-1",
    )

    # Graph still receives the input — extra fields are ignored by Deep Agents
    assert len(received_inputs) == 1
    assert received_inputs[0]["messages"][0].content == "查询月度销售额"
    assert result == {"status": "done"}


@pytest.mark.asyncio
async def test_stream_graph_planning_phase_sub_step_emitted() -> None:
    """'planning' node's on_chat_model_end causes a sub_step emission."""
    events = [
        {
            "event": "on_chat_model_end",
            "data": {},
            "metadata": {"langgraph_node": "planning"},
        },
    ]
    worker = DataCloudWorker(worker_id="w-test")
    ctx = _FakeContext()
    graph = _make_fake_graph(events, snapshot=None)

    result = await worker._stream_graph(
        target_graph=graph,
        graph_input={"messages": []},
        config={"configurable": {"thread_id": "t-1"}},
        context=ctx,
        by_agent_id="agent-1",
        conf_hash="hash-1",
    )

    assert result == {"status": "done"}
    # sub_step was triggered once for 'planning' phase
    assert ctx._sub_step_counter >= 1


@pytest.mark.asyncio
async def test_stream_graph_check_cancelled_called_per_event() -> None:
    """context.check_cancelled() is called once per streamed event."""
    cancel_count = 0

    class _CountingContext(_FakeContext):
        async def check_cancelled(self) -> None:
            nonlocal cancel_count
            cancel_count += 1

    events = [
        {"event": "on_chat_model_stream", "data": {}, "metadata": {}},
        {"event": "on_chain_start", "data": {}, "metadata": {}},
        {"event": "on_chain_end", "data": {}, "metadata": {}, "name": "other"},
    ]
    worker = DataCloudWorker(worker_id="w-test")
    ctx = _CountingContext()
    graph = _make_fake_graph(events, snapshot=None)

    await worker._stream_graph(
        target_graph=graph,
        graph_input={"messages": []},
        config={"configurable": {"thread_id": "t-1"}},
        context=ctx,
        by_agent_id="agent-1",
        conf_hash="hash-1",
    )

    assert cancel_count == len(events)


@pytest.mark.asyncio
async def test_stream_graph_cancellation_propagates() -> None:
    """CancelledError from check_cancelled propagates out of _stream_graph."""

    class _CancellingContext(_FakeContext):
        def __init__(self) -> None:
            super().__init__()
            self._call_count = 0

        async def check_cancelled(self) -> None:
            self._call_count += 1
            if self._call_count >= 2:
                raise asyncio.CancelledError("test cancel")

    events = [
        {"event": "on_chain_start", "data": {}, "metadata": {}},
        {"event": "on_chain_end", "data": {}, "metadata": {}, "name": "other"},
        {"event": "on_chain_end", "data": {}, "metadata": {}, "name": "other2"},
    ]
    worker = DataCloudWorker(worker_id="w-test")
    ctx = _CancellingContext()
    graph = _make_fake_graph(events, snapshot=None)

    with pytest.raises(asyncio.CancelledError):
        await worker._stream_graph(
            target_graph=graph,
            graph_input={"messages": []},
            config={"configurable": {"thread_id": "t-cancel"}},
            context=ctx,
            by_agent_id="agent-1",
            conf_hash="hash-1",
        )
