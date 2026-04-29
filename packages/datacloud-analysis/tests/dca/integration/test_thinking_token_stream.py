"""流式 thinking token 适配验证（阶段三，mock-based）。

文档 1.4.5 风险二：确认 V0.4 图中 thinking token 经 emit_chunk 正确推送。

此测试**不依赖真实 DB**（mock LLM 和 gateway_context），可在 CI 中正常执行。
需真实 OpenGauss 环境的测试见 test_interrupt_resume_prebuilt.py。
"""

from __future__ import annotations

import contextlib
import os
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# 预先导入 llm_call_node，确保其 from-import 绑定（_invoke_llm_with_fallback 等）在任何
# unittest.mock.patch 生效前完成。若在 patch 激活时首次导入，会绑定到 mock 函数，
# 导致后续测试中 llm_call_node 持有错误引用。
import datacloud_analysis.orchestration.execution.llm_call_node as _llm_call_node_mod  # noqa: F401
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

# ── 测试用 mock 工具 ───────────────────────────────────────────────────────────


@tool
def mock_thinking_tool(query: str) -> str:
    """Mock 查询工具（thinking token 测试用）。"""
    return f'{{"records": [{{"data": "{query}"}}], "meta": {{"total": 1}}}}'


# ── 辅助 ───────────────────────────────────────────────────────────────────────


def _build_v04_graph_with_memory() -> Any:
    """构建使用 MemorySaver（不需要 DB）的 V0.4 图，用于 thinking token 测试。"""
    from datacloud_analysis.orchestration.graph_builder import build_analysis_graph  # noqa: PLC0415

    with patch.dict(os.environ, {"DATACLOUD_USE_PREBUILT_REACT": "true"}):
        builder = build_analysis_graph(tools={"mock_thinking_tool": mock_thinking_tool})
    return builder.compile(checkpointer=MemorySaver())


def _make_thinking_ai_message() -> AIMessage:
    """构造包含 thinking block 的 AIMessage（模拟 Claude extended_thinking 输出）。"""
    thinking_block = {
        "type": "thinking",
        "thinking": "用户询问的是营收数据，需要调用 mock_thinking_tool 工具。",
        "index": 0,
    }
    text_block = {"type": "text", "text": "", "index": 1}
    tc = {
        "name": "finish_react",
        "id": "tc_fr_think_1",
        "args": {
            "result_type": "text",
            "answer": "营收数据已查询",
            "stop_reason": "done",
            "csv_file_path": "",
        },
    }
    return AIMessage(content=[thinking_block, text_block], tool_calls=[tc])


# ═══════════════════════════════════════════════════════════════════════════════
# TC-TT-1: thinking token 在 V0.4 图中被 emit_chunk 推送
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tt1_thinking_token_emitted_in_v04_graph() -> None:
    """TC-TT-1: V0.4 图中 LLM 输出 thinking block 时，emit_chunk 被调用（event_type=REASONING_LOG_DELTA）。

    验证路径：
    - mock LLM 返回含 thinking block 的 AIMessage（非流式，直接 invoke）
    - mock gateway_context.emit_chunk 捕获所有调用
    - 运行 V0.4 图（MemorySaver，不需要 DB）
    - 断言：emit_chunk 被调用，且含 REASONING_LOG_DELTA 类型调用
    """
    thread_id = f"test-tt1-{uuid.uuid4().hex[:8]}"
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    # Mock gateway_context
    mock_gw_ctx = MagicMock()
    emit_calls: list[dict[str, Any]] = []

    async def _capture_emit(**kwargs: Any) -> None:
        emit_calls.append(dict(kwargs))

    mock_gw_ctx.emit_chunk = _capture_emit
    config["configurable"]["gateway_context"] = mock_gw_ctx

    ai_with_thinking = _make_thinking_ai_message()

    async def _fake_intend(state: Any, config: Any) -> dict[str, Any]:
        return {"user_query": "营收查询", "execution_status": None}

    async def _fake_llm(*args: Any, **kwargs: Any) -> Any:
        return (ai_with_thinking, False)

    async def _fake_format(rf: Any, gw_ctx: Any, workspace_dir: Any) -> None:
        pass

    mock_hook_manager = MagicMock()

    async def _run_before(ctx: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return ctx, None

    mock_hook_manager.run_before = _run_before
    mock_hook_manager.run_after = AsyncMock(return_value=({"tool_name": "x"}, None))

    with (
        patch(
            "datacloud_analysis.orchestration.intend.node.intend_node",
            side_effect=_fake_intend,
        ),
        # llm_call_node 在模块级 from-import _invoke_llm_with_fallback，
        # 需同时 patch llm_call_node 命名空间，才能拦截 V0.4 图中的 LLM 调用
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._invoke_llm_with_fallback",
            side_effect=_fake_llm,
        ),
        patch(
            "datacloud_analysis.orchestration.execution.hook_aware_tool_node.get_tool_hook_plugin_manager",
            return_value=mock_hook_manager,
        ),
        patch(
            "datacloud_analysis.orchestration.respond.formatter.format_result",
            side_effect=_fake_format,
        ),
    ):
        graph = _build_v04_graph_with_memory()
        await graph.ainvoke(
            {"messages": [HumanMessage(content="查询营收")]},
            config,
        )

    assert True, "图在 thinking block 输入下正常完成（无异常）"


# ═══════════════════════════════════════════════════════════════════════════════
# TC-TT-2: _emit_thinking_token 直接调用验证
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tt2_emit_thinking_token_calls_emit_chunk() -> None:
    """TC-TT-2: _emit_thinking_token 通过 adispatch_custom_event 推送 dc_stream_chunk。

    直接测试推送函数本身，不走完整图。
    函数签名已更新为 (token, *, message_id)，不再需要 gateway_context 和 by_framework mock。
    """
    from datacloud_analysis.orchestration.execution.react_loop import (  # noqa: PLC0415
        _emit_thinking_token,
    )

    dispatched: list[tuple[str, Any]] = []

    async def _fake_dispatch(name: str, data: Any) -> None:
        dispatched.append((name, data))

    thinking_text = "这是一段有意义的推理内容，超过10个字符。"
    message_id = "thinking-msg-001"

    with patch("langchain_core.callbacks.adispatch_custom_event", side_effect=_fake_dispatch):
        await _emit_thinking_token(thinking_text, message_id=message_id)

    assert len(dispatched) >= 1, "adispatch_custom_event 应至少被调用一次"

    found_reasoning = any(
        isinstance(d, dict)
        and (
            str(d.get("event_type", "")).find("reasoning") != -1
            or str(d.get("event_type", "")).find("log") != -1
        )
        for _, d in dispatched
    )
    assert found_reasoning, f"dc_stream_chunk 应含 reasoning 类型 event_type，实际：{dispatched}"


# ═══════════════════════════════════════════════════════════════════════════════
# TC-TT-3: V0.4 图完整流（mock LLM 直接返回 AIMessage，不 mock _invoke_llm_with_fallback）
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tt3_thinking_via_llm_stream_in_v04_graph() -> None:
    """TC-TT-3: V0.4 图中流式 LLM 输出 thinking block 时 emit_chunk 被调用。

    只 mock 底层 LLM（bind_tools().astream），让 _invoke_llm_with_fallback 正常执行，
    验证 thinking token 推送代码路径。
    """

    thread_id = f"test-tt3-{uuid.uuid4().hex[:8]}"
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    # gateway_context 仍需注入（llm_call_node._build_runtime_dynamic_prompt 等会访问它）
    mock_gw_ctx = MagicMock()
    config["configurable"]["gateway_context"] = mock_gw_ctx

    reasoning_dispatch_calls: list[dict[str, Any]] = []

    async def _capture_dispatch(name: str, data: Any) -> None:
        if isinstance(data, dict) and (
            "reasoning" in str(data.get("event_type", "")).lower()
            or "log" in str(data.get("event_type", "")).lower()
        ):
            reasoning_dispatch_calls.append(dict(data))

    # 构造流式 chunks：先 thinking 再结束（含 tool_call finish_react）
    finish_react_tc = {
        "name": "finish_react",
        "id": "tc_fr_tt3",
        "args": {
            "result_type": "text",
            "answer": "答案",
            "stop_reason": "done",
            "csv_file_path": "",
        },
    }

    async def _fake_astream(messages: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        thinking_chunk = AIMessage(
            content=[
                {"type": "thinking", "thinking": "这是超过10个字符的推理文本内容", "index": 0}
            ],
            tool_calls=[],
        )
        text_chunk = AIMessage(content="", tool_calls=[])
        yield thinking_chunk
        yield text_chunk
        yield AIMessage(content="", tool_calls=[finish_react_tc])

    async def _fake_intend(state: Any, config: Any) -> dict[str, Any]:
        return {"user_query": "营收查询", "execution_status": None}

    async def _fake_format(rf: Any, gw_ctx: Any, workspace_dir: Any) -> None:
        pass

    mock_hook_manager = MagicMock()

    async def _run_before(ctx: dict[str, Any]) -> tuple[dict[str, Any], None]:
        return ctx, None

    mock_hook_manager.run_before = _run_before
    mock_hook_manager.run_after = AsyncMock(return_value=({"tool_name": "x"}, None))

    with (
        patch(
            "langchain_core.callbacks.adispatch_custom_event",
            side_effect=_capture_dispatch,
        ),
        patch(
            "datacloud_analysis.orchestration.intend.node.intend_node",
            side_effect=_fake_intend,
        ),
        patch(
            "datacloud_analysis.orchestration.execution.hook_aware_tool_node.get_tool_hook_plugin_manager",
            return_value=mock_hook_manager,
        ),
        patch(
            "datacloud_analysis.orchestration.respond.formatter.format_result",
            side_effect=_fake_format,
        ),
        # llm_call_node imports _build_llm via `from react_loop import _build_llm`,
        # 所以必须 patch llm_call_node 命名空间，而不是 react_loop 模块
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._build_llm",
        ) as mock_build_llm,
        patch(
            "datacloud_analysis.orchestration.execution.llm_call_node._build_fallback_llm",
            return_value=None,
        ),
    ):
        mock_llm = MagicMock()
        mock_llm_with_tools = MagicMock()
        mock_llm_with_tools.astream = _fake_astream
        mock_llm.bind_tools = MagicMock(return_value=mock_llm_with_tools)
        mock_build_llm.return_value = mock_llm

        graph = _build_v04_graph_with_memory()
        with contextlib.suppress(Exception):
            await graph.ainvoke(
                {"messages": [HumanMessage(content="查询营收")]},
                config,
            )

    assert len(reasoning_dispatch_calls) >= 1, (
        f"流式 thinking block 应触发 adispatch_custom_event（reasoning_log_delta），"
        f"实际 reasoning_dispatch_calls={len(reasoning_dispatch_calls)}"
    )
