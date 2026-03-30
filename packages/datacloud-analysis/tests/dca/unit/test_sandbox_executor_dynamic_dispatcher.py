from __future__ import annotations

from typing import Any

import pytest

from datacloud_analysis.orchestration.sandbox_executor import execute_next_task


class _NoopHookManager:
    async def run_before(self, context: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return context, None

    async def run_after(self, context: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return context, None


class _HookManagerLegacyShortCircuit:
    async def run_before(
        self, context: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return context, {"short_circuit": True, "output": {"code": 0, "legacy": True}}

    async def run_after(self, context: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return context, None


class _CaptureContextHookManager:
    def __init__(self) -> None:
        self.last_context: dict[str, Any] | None = None

    async def run_before(self, context: dict[str, Any]) -> tuple[dict[str, Any], None]:
        self.last_context = dict(context)
        return context, None

    async def run_after(self, context: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return context, None


@pytest.mark.asyncio
async def test_dynamic_callable_maps_question_to_content_and_injects_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datacloud_analysis.orchestration import sandbox_executor as se

    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: _NoopHookManager())

    gateway_context = object()

    async def _delegate_tool(content: str, _context: Any = None, **params: Any) -> dict[str, Any]:
        return {"content": content, "context_ok": _context is gateway_context, "params": params}

    task = {
        "id": "t_direct",
        "type": "delegate_tool",
        "status": "pending",
        "deps": [],
        "params": {},
        "description": "query enterprise table top 100",
    }
    state: dict[str, Any] = {"messages": []}
    updated_task, output = await execute_next_task(
        task=task,
        state=state,
        gateway_context=gateway_context,
        custom_tools={"delegate_tool": _delegate_tool},
    )

    assert updated_task["status"] == "done"
    assert output["content"] == "query enterprise table top 100"
    assert output["context_ok"] is True


@pytest.mark.asyncio
async def test_dynamic_callable_filters_unaccepted_kwargs_for_fixed_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datacloud_analysis.orchestration import sandbox_executor as se

    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: _NoopHookManager())

    async def _fixed_signature(content: str) -> str:
        return content

    task = {
        "id": "t_direct",
        "type": "fixed_tool",
        "status": "pending",
        "deps": [],
        "params": {"question": "Q1", "extra": "ignored"},
        "description": "desc",
    }
    state: dict[str, Any] = {"messages": []}
    updated_task, output = await execute_next_task(
        task=task,
        state=state,
        gateway_context=None,
        custom_tools={"fixed_tool": _fixed_signature},
    )

    assert updated_task["status"] == "done"
    assert output == "Q1"


@pytest.mark.asyncio
async def test_dynamic_ainvoke_dispatcher_backfills_content(monkeypatch: pytest.MonkeyPatch) -> None:
    from datacloud_analysis.orchestration import sandbox_executor as se

    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: _NoopHookManager())

    class _AinvokeWrapper:
        async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            return await self(**payload)

        async def __call__(self, content: str, **params: Any) -> dict[str, Any]:
            return {"content": content, "params": params}

    task = {
        "id": "t_direct",
        "type": "ainvoke_tool",
        "status": "pending",
        "deps": [],
        "params": {"question": "Q2"},
        "description": "desc",
    }
    state: dict[str, Any] = {"messages": []}
    updated_task, output = await execute_next_task(
        task=task,
        state=state,
        gateway_context=None,
        custom_tools={"ainvoke_tool": _AinvokeWrapper()},
    )

    assert updated_task["status"] == "done"
    assert output["content"] == "Q2"


@pytest.mark.asyncio
async def test_hook_legacy_short_circuit_schema_is_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datacloud_analysis.orchestration import sandbox_executor as se

    monkeypatch.setattr(
        se,
        "get_tool_hook_plugin_manager",
        lambda: _HookManagerLegacyShortCircuit(),
    )

    async def _should_not_run(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("dispatcher should not run when short-circuited")

    task = {
        "id": "t_hook_legacy",
        "type": "legacy_tool",
        "status": "pending",
        "deps": [],
        "params": {},
        "description": "desc",
    }
    state: dict[str, Any] = {"messages": []}
    updated_task, output = await execute_next_task(
        task=task,
        state=state,
        gateway_context=None,
        custom_tools={"legacy_tool": _should_not_run},
    )

    assert updated_task["status"] == "done"
    assert output == {"code": 0, "legacy": True}


@pytest.mark.asyncio
async def test_hook_context_contains_workspace_and_todo_term_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datacloud_analysis.orchestration import sandbox_executor as se

    manager = _CaptureContextHookManager()
    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: manager)

    async def _tool(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    task = {
        "id": "t1",
        "type": "ctx_tool",
        "status": "pending",
        "deps": [],
        "params": {},
        "description": "desc",
    }
    state: dict[str, Any] = {
        "messages": [],
        "agent_id": "a1",
        "workspace_dir": "/tmp/dc",
        "enriched_query": "q1",
        "knowledge_snippets": [{"source": "k"}],
        "todos": [{"todo_id": "t1", "goal": "g1", "term_context": [{"mention": "m1"}]}],
        "resume_context": {"checkpoint_id": "c1", "checkpoint_ns": "n1"},
    }
    updated_task, output = await execute_next_task(
        task=task,
        state=state,
        gateway_context=None,
        custom_tools={"ctx_tool": _tool},
    )

    assert updated_task["status"] == "done"
    assert output == {"ok": True}
    assert manager.last_context is not None
    assert manager.last_context["agent_id"] == "a1"
    assert manager.last_context["workspace_dir"] == "/tmp/dc"
    assert manager.last_context["checkpoint_id"] == "c1"
    assert manager.last_context["checkpoint_ns"] == "n1"
    assert manager.last_context["term_context"] == [{"mention": "m1"}]
