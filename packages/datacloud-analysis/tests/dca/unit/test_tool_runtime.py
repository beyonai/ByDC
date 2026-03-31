from __future__ import annotations

from typing import Any

import pytest

from datacloud_analysis.orchestration.execution import sandbox_executor as se


class _NoopAfterHookManager:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def run_before(self, context: dict[str, Any]) -> tuple[dict[str, Any], None]:
        self.events.append("before")
        patched = dict(context)
        tool_params = dict(patched.get("tool_params") or {})
        tool_params["patched"] = "yes"
        patched["tool_params"] = tool_params
        return patched, None

    async def run_after(self, context: dict[str, Any]) -> tuple[dict[str, Any], None]:
        self.events.append("after")
        return context, None


class _ShortCircuitBeforeHookManager:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def run_before(
        self, context: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self.events.append("before")
        return context, {"action": "short_circuit", "result": {"tool_output": {"source": "before"}}}

    async def run_after(self, context: dict[str, Any]) -> tuple[dict[str, Any], None]:
        self.events.append("after")
        return context, None


@pytest.mark.asyncio
async def test_tool_runtime_invoke_calls_before_after_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _NoopAfterHookManager()
    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: manager)

    async def _tool(content: str, **params: Any) -> dict[str, Any]:
        assert content == "q1"
        assert params["patched"] == "yes"
        return {"ok": True, "patched": params["patched"]}

    runtime = se.ToolRuntime(custom_tools={"demo_tool": _tool}, gateway_context=None)
    task = {
        "id": "t1",
        "type": "demo_tool",
        "status": "pending",
        "deps": [],
        "params": {"content": "q1"},
        "description": "desc",
    }
    updated_task, output = await runtime.invoke_with_callbacks(task=task, state={"messages": []})

    assert updated_task["status"] == "done"
    assert output == {"ok": True, "patched": "yes"}
    assert manager.events == ["before", "after"]


@pytest.mark.asyncio
async def test_tool_runtime_before_short_circuit_skips_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _ShortCircuitBeforeHookManager()
    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: manager)

    async def _should_not_run(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("tool should not run when before hook short-circuits")

    runtime = se.ToolRuntime(custom_tools={"demo_tool": _should_not_run}, gateway_context=None)
    task = {
        "id": "t2",
        "type": "demo_tool",
        "status": "pending",
        "deps": [],
        "params": {"content": "q2"},
        "description": "desc",
    }
    updated_task, output = await runtime.invoke_with_callbacks(task=task, state={"messages": []})

    assert updated_task["status"] == "done"
    assert output == {"source": "before"}
    assert manager.events == ["before"]


@pytest.mark.asyncio
async def test_execute_next_task_compat_delegates_to_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _fake_invoke(
        self: se.ToolRuntime, task: dict[str, Any], state: dict[str, Any]
    ) -> tuple[dict[str, Any], Any]:
        captured["task"] = task
        captured["state"] = state
        captured["custom_tools"] = self._custom_tools
        captured["gateway_context"] = self._gateway_context
        return {**task, "status": "done"}, {"ok": True}

    monkeypatch.setattr(se.ToolRuntime, "invoke_with_callbacks", _fake_invoke)

    gateway_context = object()
    task = {"id": "t3", "type": "x", "status": "pending", "deps": [], "params": {}}
    state: dict[str, Any] = {"messages": []}
    custom_tools = {"x": object()}
    updated_task, output = await se.execute_next_task(
        task=task,
        state=state,
        gateway_context=gateway_context,
        custom_tools=custom_tools,
    )

    assert updated_task["status"] == "done"
    assert output == {"ok": True}
    assert captured["task"] == task
    assert captured["state"] == state
    assert captured["custom_tools"] == custom_tools
    assert captured["gateway_context"] is gateway_context
