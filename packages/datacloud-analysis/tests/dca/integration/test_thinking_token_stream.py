"""流式 thinking token 适配验证（阶段三，mock-based）。

文档 1.4.5 风险二：确认 _invoke_llm_with_fallback 在新图拓扑中被正确调用，
thinking token 经 emit_chunk 推送给下游。

此测试不依赖真实 DB，使用 mock，可在 CI 中正常执行。
"""

from __future__ import annotations

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# TC-TT-1: thinking token 在新图拓扑中被 emit_chunk 推送
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tt1_thinking_token_emitted_in_new_graph() -> None:
    """TC-TT-1: 新图（V0.4）一轮推理中，thinking token 经 emit_chunk 推送。

    验证：make_llm_call_node（agent 节点）调用 _invoke_llm_with_fallback 时，
    gateway_context.emit_chunk 被调用且 event_type 包含 thinking。
    """
    # TODO(阶段三): 实现步骤
    # from datacloud_analysis.orchestration.graph_builder import build_analysis_graph
    #
    # mock_gw_ctx = MagicMock()
    # mock_gw_ctx.emit_chunk = AsyncMock()
    #
    # # mock LLM 调用，返回含 thinking block 的 AIMessage
    # thinking_block = {"type": "thinking", "thinking": "推理过程...", "index": 0}
    # text_block = {"type": "text", "text": "最终回答", "index": 1}
    # mock_ai_response = AIMessage(content=[thinking_block, text_block], tool_calls=[])
    #
    # with patch("datacloud_analysis.orchestration.execution.llm_call_node._invoke_llm_with_fallback",
    #            return_value=mock_ai_response):
    #     os.environ["DATACLOUD_USE_PREBUILT_REACT"] = "true"
    #     graph = build_analysis_graph(...).compile()
    #     state = await graph.ainvoke(
    #         {"messages": [HumanMessage(content="test query")]},
    #         {"configurable": {"gateway_context": mock_gw_ctx}},
    #     )
    #
    # # 断言 emit_chunk 被调用且含 thinking 事件
    # emit_calls = mock_gw_ctx.emit_chunk.call_args_list
    # thinking_calls = [c for c in emit_calls if c.kwargs.get("event_type") == "thinking"]
    # assert thinking_calls, "应有 thinking token emit_chunk 调用"
    pytest.skip("TODO(阶段三): 实现 thinking token stream 验证")


# ═══════════════════════════════════════════════════════════════════════════════
# TC-TT-2: 无 thinking 时 emit_chunk 不推送 thinking 事件
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tt2_no_thinking_token_when_disabled() -> None:
    """TC-TT-2: LLM 不产生 thinking block 时，emit_chunk 不应有 thinking 事件。"""
    # TODO(阶段三): 实现步骤
    pytest.skip("TODO(阶段三): 实现 no-thinking 验证")
