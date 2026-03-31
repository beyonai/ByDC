from __future__ import annotations

from typing import Any, cast

import pytest

from datacloud_analysis.orchestration.execution.node import execution_node
from datacloud_analysis.orchestration.execution.sandbox_executor import execute_next_task
from datacloud_analysis.orchestration.state import AgentState


class _NoopHookManager:
    async def run_before(self, context: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return context, None

    async def run_after(self, context: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return context, None


class _GatewayContext:
    def __init__(self, context_tags: list[str]) -> None:
        self.context_tags = context_tags


def _skill_capability(
    *,
    risk_level: str = "medium",
    allowlist_tags: list[str] | None = None,
    blocklist_tags: list[str] | None = None,
) -> Any:
    async def _tool(**_params: Any) -> dict[str, Any]:
        return {"ok": True}

    _tool._is_skill_capability = True  # type: ignore[attr-defined]
    _tool._skill_name = "skill.test"  # type: ignore[attr-defined]
    _tool._skill_risk_level = risk_level  # type: ignore[attr-defined]
    _tool._skill_allowlist_tags = allowlist_tags or []  # type: ignore[attr-defined]
    _tool._skill_blocklist_tags = blocklist_tags or []  # type: ignore[attr-defined]
    return _tool


def _state_for_skill_todo() -> AgentState:
    return cast(
        AgentState,
        {
            "query_mode": "chitchat",
            "todos": [
                {
                    "todo_id": "t1",
                    "status": "pending",
                    "required_capabilities": [
                        {"capability_id": "skill.test", "capability_type": "skill"}
                    ],
                    "blocked_capabilities": [],
                }
            ],
        },
    )


@pytest.mark.asyncio
async def test_skill_allowed_with_empty_context_tags() -> None:
    state = _state_for_skill_todo()
    out = await execution_node(
        state,
        {"configurable": {"gateway_context": _GatewayContext([])}},
        default_tools={
            "skill.test": _skill_capability(
                allowlist_tags=["tenant_a"],
                blocklist_tags=["tenant_blocked"],
            )
        },
    )
    assert out["active_tools"] == ["skill.test"]


@pytest.mark.asyncio
async def test_skill_blocked_by_blocklist_tag() -> None:
    state = _state_for_skill_todo()
    out = await execution_node(
        state,
        {"configurable": {"gateway_context": _GatewayContext(["tenant_a", "scene_prod"])}},
        default_tools={"skill.test": _skill_capability(blocklist_tags=["scene_prod"])},
    )
    assert out["active_tools"] == []


@pytest.mark.asyncio
async def test_skill_blocked_by_allowlist_mismatch() -> None:
    state = _state_for_skill_todo()
    out = await execution_node(
        state,
        {"configurable": {"gateway_context": _GatewayContext(["tenant_b"])}},
        default_tools={"skill.test": _skill_capability(allowlist_tags=["tenant_a"])},
    )
    assert out["active_tools"] == []


@pytest.mark.asyncio
async def test_skill_risk_and_tags_propagated_to_audit(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from datacloud_analysis.orchestration.execution import sandbox_executor as se

    monkeypatch.setattr(se, "get_tool_hook_plugin_manager", lambda: _NoopHookManager())

    skill = _skill_capability(
        risk_level="high",
        allowlist_tags=["tenant_a"],
        blocklist_tags=["scene_prod"],
    )
    task = {
        "id": "t_skill",
        "type": "skill.test",
        "status": "pending",
        "deps": [],
        "params": {"q": "x"},
        "description": "run tagged skill",
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
            custom_tools={"skill.test": skill},
        )

    assert updated_task["status"] == "done"
    assert output == {"ok": True}

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "skill_call_audit" in log_text
    assert "risk_level" in log_text
    assert "high" in log_text
    assert "allowlist_tags" in log_text
    assert "tenant_a" in log_text
    assert "blocklist_tags" in log_text
    assert "scene_prod" in log_text
