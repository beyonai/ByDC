from __future__ import annotations

from pathlib import Path
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
async def test_dynamic_ainvoke_keyword_only_content_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    from datacloud_analysis.orchestration import sandbox_executor as se

    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: _NoopHookManager())

    class _AinvokeKeywordOnly:
        async def ainvoke(self, *, content: str, _context: Any = None, **params: Any) -> dict[str, Any]:
            return {"content": content, "context": _context, "params": params}

    gateway_context = object()
    task = {
        "id": "t_direct",
        "type": "ainvoke_tool",
        "status": "pending",
        "deps": [],
        "params": {"question": "Q3"},
        "description": "desc",
    }
    state: dict[str, Any] = {"messages": []}
    updated_task, output = await execute_next_task(
        task=task,
        state=state,
        gateway_context=gateway_context,
        custom_tools={"ainvoke_tool": _AinvokeKeywordOnly()},
    )

    assert updated_task["status"] == "done"
    assert output["content"] == "Q3"
    assert output["context"] is gateway_context


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
        "term_hints": [{"mention": "m0"}],
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
    assert manager.last_context["term_hints"] == [{"mention": "m0"}]
    assert manager.last_context["term_context"] == [{"mention": "m1"}]


@pytest.mark.asyncio
async def test_builtin_chat_response_tool_dispatcher(monkeypatch: pytest.MonkeyPatch) -> None:
    from datacloud_analysis.orchestration import sandbox_executor as se

    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: _NoopHookManager())

    task = {
        "id": "t_chat",
        "type": "chat-response-tool",
        "status": "pending",
        "deps": [],
        "params": {"message": "hello"},
        "description": "desc",
    }
    state: dict[str, Any] = {"messages": []}
    updated_task, output = await execute_next_task(task=task, state=state, gateway_context=None)

    assert updated_task["status"] == "done"
    assert output == {"message": "hello", "result_type": "chat_response"}


@pytest.mark.asyncio
async def test_builtin_task_note_tool_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from datacloud_analysis.orchestration import sandbox_executor as se

    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: _NoopHookManager())

    state: dict[str, Any] = {"messages": [], "workspace_dir": str(tmp_path)}
    write_task = {
        "id": "t_note_write",
        "type": "task-note-tool",
        "status": "pending",
        "deps": [],
        "params": {"action": "write", "content": "# TODOs\n- a\n"},
        "description": "desc",
    }
    updated_write, write_output = await execute_next_task(
        task=write_task,
        state=state,
        gateway_context=None,
    )
    assert updated_write["status"] == "done"
    assert "todo.md" in str(write_output["path"])

    read_task = {
        "id": "t_note_read",
        "type": "task-note-tool",
        "status": "pending",
        "deps": [],
        "params": {"action": "read"},
        "description": "desc",
    }
    updated_read, read_output = await execute_next_task(
        task=read_task,
        state=state,
        gateway_context=None,
    )
    assert updated_read["status"] == "done"
    assert "# TODOs" in str(read_output["content"])


@pytest.mark.asyncio
async def test_skill_call_emits_structured_audit_log_with_masked_params(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from datacloud_analysis.orchestration import sandbox_executor as se

    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: _NoopHookManager())

    async def _skill_run(**_kwargs: Any) -> dict[str, Any]:
        return {"rows": [1, 2, 3], "token": "result-secret"}

    _skill_run._is_skill_capability = True  # type: ignore[attr-defined]

    task = {
        "id": "t_skill",
        "type": "skill.normalize",
        "status": "pending",
        "deps": [],
        "params": {"api_key": "sk-xxx", "keyword": "beijing"},
        "description": "run normalize",
    }
    state: dict[str, Any] = {
        "messages": [],
        "resume_context": {"checkpoint_id": "ckpt-1", "checkpoint_ns": "ns-1"},
    }

    with caplog.at_level("INFO"):
        updated_task, output = await execute_next_task(
            task=task,
            state=state,
            gateway_context=None,
            custom_tools={"skill.normalize": _skill_run},
        )

    assert updated_task["status"] == "done"
    assert output["rows"] == [1, 2, 3]

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "skill_call_audit" in log_text
    assert "skill.normalize" in log_text
    assert "ckpt-1" in log_text
    assert "ns-1" in log_text
    assert "api_key" in log_text
    assert "[REDACTED]" in log_text
    assert "sk-xxx" not in log_text


@pytest.mark.asyncio
async def test_skill_call_failure_still_emits_structured_audit_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from datacloud_analysis.orchestration import sandbox_executor as se

    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: _NoopHookManager())

    async def _broken_skill(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("skill boom")

    _broken_skill._is_skill_capability = True  # type: ignore[attr-defined]

    task = {
        "id": "t_skill_fail",
        "type": "skill.broken",
        "status": "pending",
        "deps": [],
        "params": {"password": "123456"},
        "description": "run broken skill",
    }
    state: dict[str, Any] = {"messages": []}

    with caplog.at_level("INFO"):
        updated_task, output = await execute_next_task(
            task=task,
            state=state,
            gateway_context=None,
            custom_tools={"skill.broken": _broken_skill},
        )

    assert updated_task["status"] == "failed"
    assert output == "skill boom"

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "skill_call_audit" in log_text
    assert "skill.broken" in log_text
    assert "status': 'failed'" in log_text or '"status": "failed"' in log_text
    assert "[REDACTED]" in log_text
    assert "123456" not in log_text

