from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from datacloud_analysis.tools.delegate import build_delegate_tool


class _FakeHeader:
    def __init__(self) -> None:
        self.metadata = {"agent_id": "parent-agent", "conf_hash": "conf-parent"}


class _FakeCommand:
    def __init__(self) -> None:
        self.header = _FakeHeader()
        self.extra_payload = {"agent_id": "parent-agent", "agent_name": "父Agent"}


class _FakeDelegateContext:
    def __init__(self) -> None:
        self.session_id = "sess-parent"
        self.current_agent_id = "worker-parent"
        self.current_command = _FakeCommand()
        self.message_id = "top-level-id"
        self._delegate_parent_message_id = "tool-level-id"
        self.call_agent_calls: list[dict[str, Any]] = []
        self.emitted: list[dict[str, Any]] = []

    async def emit_chunk(self, event: Any, **kwargs: Any) -> None:
        self.emitted.append({"content": getattr(event, "content", ""), **kwargs})

    async def call_agent(self, **kwargs: Any) -> dict[str, Any]:
        self.call_agent_calls.append(dict(kwargs))
        return {"status": "submitted"}

    def _resolve_delegate_parent_message_id(self, parent_message_id: str | None = None) -> str:
        return parent_message_id or self._delegate_parent_message_id


@pytest.mark.asyncio
async def test_agent_delegate_tool_calls_agent_in_tool_then_interrupts() -> None:
    """call_agent 由基类 _dispatch_side_effect 在工具内部调用（不再走 worker 侧）。"""
    tool = build_delegate_tool(
        target_agent_type="child-agent",
        agent_name="专项Agent",
        agent_desc="处理专项任务",
    )
    context = _FakeDelegateContext()
    captured_payload: dict[str, Any] = {}

    def fake_interrupt(payload: Any) -> Any:
        captured_payload.update(payload)
        # 子 Agent 完成后 worker 发回的 ResumeCommand.reply_data 结构
        return {"status": "done", "conclusion": "子Agent分析结论：订单异常原因为库存不足"}

    with patch("datacloud_analysis.tools.base.interruptible.interrupt", side_effect=fake_interrupt):
        result = await tool._arun(
            content="继续分析订单异常",
            _context=context,
            delegate_policy={"mode": "sync", "wait_for_reply": True},
            payload={"ext_params": {"command": "delegate"}},
            metadata={"scene": "test"},
        )

    # 结论正确透传给 LLM
    assert result == "子Agent分析结论：订单异常原因为库存不足"

    # call_agent 已在工具内部调用
    assert len(context.call_agent_calls) == 1
    assert context.emitted == []

    call = context.call_agent_calls[0]
    assert call["target_agent_type"] == "child-agent"
    assert call["content"] == "继续分析订单异常"
    assert call["wait_for_reply"] is True
    assert call["parent_message_id"] == "tool-level-id"
    assert call["payload"] == {"ext_params": {"command": "delegate"}}
    # message_id 是稳定 hash（16 位），不是随机生成
    assert len(call["message_id"]) == 16

    meta = call["metadata"]
    assert meta["scene"] == "test"
    assert meta["delegate_parent_message_id"] == "tool-level-id"
    assert meta["parent_resume_target"]["delegate_parent_message_id"] == "tool-level-id"
    assert meta["parent_resume_target"]["resume_via"] == "ResumeCommand.reply_data"
    assert meta["resume_agent_id"] == "parent-agent"
    assert meta["resume_agent_name"] == "父Agent"
    assert meta["resume_agent_type"] == "worker-parent"
    assert meta["resume_conf_hash"] == "conf-parent"

    # interrupt payload 不再含 call_agent_kwargs，改用 side_effect_kwargs（不入 payload）
    assert "call_agent_kwargs" not in captured_payload
    assert captured_payload["reason_code"] == "AGENT_DELEGATE_WAIT"
    assert captured_payload["display"]["target_agent_type"] == "child-agent"
    assert captured_payload["display"]["delegate_content"] == "继续分析订单异常"
    # correlation_id 与 call_agent 的 message_id 一致
    assert captured_payload["correlation_id"] == call["message_id"]


@pytest.mark.asyncio
async def test_agent_delegate_tool_resume_idempotent_same_message_id() -> None:
    """同样的入参第二次调用（resume 重跑）产生相同的 message_id，保证幂等。"""
    tool = build_delegate_tool(
        target_agent_type="child-agent",
        agent_name="专项Agent",
        agent_desc="处理专项任务",
    )
    context = _FakeDelegateContext()

    def fake_interrupt(payload: Any) -> Any:
        return {"status": "done", "conclusion": "结论"}

    with patch("datacloud_analysis.tools.base.interruptible.interrupt", side_effect=fake_interrupt):
        await tool._arun(content="同一任务", _context=context)
        await tool._arun(content="同一任务", _context=context)

    msg_id_1 = context.call_agent_calls[0]["message_id"]
    msg_id_2 = context.call_agent_calls[1]["message_id"]
    assert msg_id_1 == msg_id_2, "resume 重跑时 message_id 必须稳定，保证框架侧幂等去重"


@pytest.mark.asyncio
async def test_resume_data_falsy_string_preserved() -> None:
    """resume.data 为空字符串时不应被错误丢弃（修复 or 链 bug）。"""
    tool = build_delegate_tool(
        target_agent_type="child-agent",
        agent_name="专项Agent",
        agent_desc="处理专项任务",
    )
    context = _FakeDelegateContext()

    def fake_interrupt(_payload: Any) -> Any:
        return {"status": "done", "data": ""}  # 空字符串是有效的 data

    with patch("datacloud_analysis.tools.base.interruptible.interrupt", side_effect=fake_interrupt):
        result = await tool._arun(content="任务", _context=context)

    # 空字符串应被保留（不 fallback 到 conclusion 或 "未返回结论内容"）
    assert result == ""


@pytest.mark.asyncio
async def test_side_effect_kwargs_not_in_interrupt_payload() -> None:
    """side_effect_kwargs 不写入 interrupt payload，不污染 checkpoint。"""
    tool = build_delegate_tool(
        target_agent_type="child-agent",
        agent_name="专项Agent",
        agent_desc="处理专项任务",
    )
    context = _FakeDelegateContext()
    captured_payload: dict[str, Any] = {}

    def fake_interrupt(payload: Any) -> Any:
        captured_payload.update(payload)
        return {"status": "done", "conclusion": "结论"}

    with patch("datacloud_analysis.tools.base.interruptible.interrupt", side_effect=fake_interrupt):
        await tool._arun(content="分析任务", _context=context)

    assert "side_effect_kwargs" not in captured_payload
    assert "call_agent_kwargs" not in captured_payload
    # payload 只含规定字段
    assert set(captured_payload.keys()) <= {
        "reason_code",
        "display",
        "resume_schema",
        "correlation_id",
        "timeout_seconds",
    }
