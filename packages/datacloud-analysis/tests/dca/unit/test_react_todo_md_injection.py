from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from datacloud_analysis.orchestration.execution import node as execution_module
from datacloud_analysis.orchestration.execution import react_runtime
from datacloud_analysis.orchestration.execution.node import execution_node
from datacloud_analysis.orchestration.execution.react_runtime import select_react_capability
from datacloud_analysis.orchestration.state import AgentState


@dataclass
class _FakeAIMessage:
    tool_calls: list[dict[str, Any]]


class _CaptureBoundModel:
    def __init__(self, tool_calls: list[dict[str, Any]], sink: list[list[Any]]) -> None:
        self._tool_calls = tool_calls
        self._sink = sink

    async def ainvoke(self, messages: list[Any]) -> _FakeAIMessage:
        self._sink.append(messages)
        return _FakeAIMessage(tool_calls=self._tool_calls)


class _CaptureModel:
    def __init__(self, tool_calls: list[dict[str, Any]], sink: list[list[Any]]) -> None:
        self._tool_calls = tool_calls
        self._sink = sink

    def bind_tools(self, *_args: Any, **_kwargs: Any) -> _CaptureBoundModel:
        return _CaptureBoundModel(self._tool_calls, self._sink)


@pytest.mark.asyncio
async def test_select_react_capability_injects_todo_md(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_messages: list[list[Any]] = []

    def _fake_init_chat_model(*_args: Any, **_kwargs: Any) -> _CaptureModel:
        return _CaptureModel(
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "choose_capability",
                    "args": {"capability_id": "tool.query", "reason": "ok"},
                }
            ],
            sink=captured_messages,
        )

    monkeypatch.setattr(react_runtime, "init_chat_model", _fake_init_chat_model)
    await select_react_capability(
        state={},
        todo={"goal": "query goal"},
        candidates=["tool.query"],
        round_index=1,
        todo_md_summary="todo-line-1\ntodo-line-2",
    )

    assert captured_messages
    system_text = str(captured_messages[0][0].content)
    assert "当前任务进度" in system_text
    assert "todo-line-1" in system_text


@pytest.mark.asyncio
async def test_select_react_capability_injects_observe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_messages: list[list[Any]] = []

    def _fake_init_chat_model(*_args: Any, **_kwargs: Any) -> _CaptureModel:
        return _CaptureModel(
            tool_calls=[
                {
                    "id": "call_2",
                    "name": "choose_capability",
                    "args": {"capability_id": "tool.query", "reason": "ok"},
                }
            ],
            sink=captured_messages,
        )

    monkeypatch.setattr(react_runtime, "init_chat_model", _fake_init_chat_model)
    await select_react_capability(
        state={},
        todo={"goal": "query goal"},
        candidates=["tool.query"],
        round_index=2,
        observe="上一轮执行失败: timeout",
    )

    assert captured_messages
    system_text = str(captured_messages[0][0].content)
    assert "上一轮执行结果" in system_text
    assert "timeout" in system_text


@pytest.mark.asyncio
async def test_react_loop_reads_todo_md_each_round(monkeypatch: pytest.MonkeyPatch) -> None:
    round_calls = {"read": 0, "select": 0}

    async def _fake_read_todo_md(_workspace_dir: str | None) -> str | None:
        round_calls["read"] += 1
        return "todo summary"

    async def _fake_select_react_capability(**_kwargs: Any) -> dict[str, Any]:
        round_calls["select"] += 1
        if round_calls["select"] == 1:
            return {
                "capability_id": "tool_a",
                "source": "llm_function_call",
                "reason": "first",
                "tool_call_id": "call_1",
                "param_overrides": {},
            }
        return {
            "capability_id": "tool_b",
            "source": "llm_function_call",
            "reason": "second",
            "tool_call_id": "call_2",
            "param_overrides": {},
        }

    async def _fake_execute_next_task(*args: Any, **_kwargs: Any) -> tuple[dict[str, Any], Any]:
        task = args[0]
        if str(task.get("type")) == "tool_a":
            return ({**task, "status": "failed", "error": "boom"}, {"error": "boom"})
        return ({**task, "status": "done"}, {"ok": True})

    monkeypatch.setattr(execution_module, "_read_todo_md", _fake_read_todo_md)
    monkeypatch.setattr(execution_module, "select_react_capability", _fake_select_react_capability)
    monkeypatch.setattr(execution_module, "execute_next_task", _fake_execute_next_task)

    state: AgentState = {
        "workspace_dir": "C:/tmp/not-required",
        "query_mode": "analysis",
        "todos": [
            {
                "todo_id": "t1",
                "status": "pending",
                "goal": "need two rounds",
                "required_capabilities": ["tool_a", "tool_b"],
                "required_tools": ["tool_a", "tool_b"],
                "inputs": {"q": "x"},
                "depends_on": [],
            }
        ],
        "results": [],
        "invocation_dedup": [],
    }
    out = await execution_node(state, {"configurable": {}}, default_tools={})

    assert out["execution_status"] == "done"
    assert round_calls["read"] == 2


@pytest.mark.asyncio
async def test_param_overrides_applied_to_next_round(monkeypatch: pytest.MonkeyPatch) -> None:
    select_round = {"n": 0}
    called_params: list[dict[str, Any]] = []

    async def _fake_read_todo_md(_workspace_dir: str | None) -> str | None:
        return "todo summary"

    async def _fake_select_react_capability(**_kwargs: Any) -> dict[str, Any]:
        select_round["n"] += 1
        if select_round["n"] == 1:
            return {
                "capability_id": "tool_a",
                "source": "llm_function_call",
                "reason": "try first",
                "tool_call_id": "call_a",
                "param_overrides": {"query": "new-value"},
            }
        return {
            "capability_id": "tool_b",
            "source": "llm_function_call",
            "reason": "retry",
            "tool_call_id": "call_b",
            "param_overrides": {},
        }

    async def _fake_execute_next_task(*args: Any, **_kwargs: Any) -> tuple[dict[str, Any], Any]:
        task = args[0]
        called_params.append(dict(task.get("params") or {}))
        if str(task.get("type")) == "tool_a":
            return ({**task, "status": "failed", "error": "boom"}, {"error": "boom"})
        return ({**task, "status": "done"}, {"ok": True})

    monkeypatch.setattr(execution_module, "_read_todo_md", _fake_read_todo_md)
    monkeypatch.setattr(execution_module, "select_react_capability", _fake_select_react_capability)
    monkeypatch.setattr(execution_module, "execute_next_task", _fake_execute_next_task)

    state: AgentState = {
        "query_mode": "analysis",
        "todos": [
            {
                "todo_id": "t1",
                "status": "pending",
                "goal": "override params",
                "required_capabilities": ["tool_a", "tool_b"],
                "required_tools": ["tool_a", "tool_b"],
                "inputs": {"query": "old-value"},
                "depends_on": [],
            }
        ],
        "results": [],
        "invocation_dedup": [],
    }
    out = await execution_node(state, {"configurable": {}}, default_tools={})

    assert out["execution_status"] == "done"
    assert len(called_params) == 2
    assert called_params[1]["query"] == "new-value"
