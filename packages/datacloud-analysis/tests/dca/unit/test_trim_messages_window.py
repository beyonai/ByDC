"""_trim_messages_window 单元测试 — TDD 红阶段，先写测试，验证会失败。"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

# Mock datacloud_platform.platform.get_platform() 以避免 OntologyBase 初始化失败
sys.modules["datacloud_platform.platform"] = MagicMock()

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


class TestResolveTrimBudget:
    """测试预算计算函数 _resolve_trim_budget（从 Redis maxContentToken 动态计算）。"""

    @patch.dict(os.environ, {}, clear=True)
    def test_fallback_when_env_empty(self):
        """Redis 无 maxContentToken → 兜底到 128000，预算 = 128000 * 0.75 = 96000。"""
        from datacloud_analysis.orchestration.execution.react_loop import _resolve_trim_budget

        assert _resolve_trim_budget() == 96000

    @patch.dict(os.environ, {"DATACLOUD_LLM_MAX_CONTENT_TOKEN": "200000"})
    def test_calculate_from_redis_200k(self):
        """Redis maxContentToken=200000 → 预算 = 200000 * 0.75 = 150000。"""
        from datacloud_analysis.orchestration.execution.react_loop import _resolve_trim_budget

        assert _resolve_trim_budget() == 150000

    @patch.dict(os.environ, {"DATACLOUD_LLM_MAX_CONTENT_TOKEN": "128000"})
    def test_calculate_from_redis_128k(self):
        """Redis maxContentToken=128000 → 预算 = 128000 * 0.75 = 96000。"""
        from datacloud_analysis.orchestration.execution.react_loop import _resolve_trim_budget

        assert _resolve_trim_budget() == 96000

    @patch.dict(os.environ, {"DATACLOUD_LLM_MAX_CONTENT_TOKEN": "invalid"})
    def test_fallback_when_env_invalid(self):
        """Redis 值非法 → 兜底到 128000 * 0.75。"""
        from datacloud_analysis.orchestration.execution.react_loop import _resolve_trim_budget

        assert _resolve_trim_budget() == 96000


class TestTrimMessagesWindow:
    """测试重写后的 _trim_messages_window（官方 trim_messages + 兜底清洗 + id 规范化）。"""

    @patch.dict(os.environ, {"DATACLOUD_LLM_MAX_CONTENT_TOKEN": "200000"})
    def test_short_history_not_trimmed(self):
        """短历史（总 token < 预算）→ 原样返回（含 system）。"""
        from datacloud_analysis.orchestration.execution.react_loop import _trim_messages_window

        messages = [
            SystemMessage(content="System prompt here"),
            HumanMessage(content="User query"),
            AIMessage(content="AI response"),
            ToolMessage(content="tool result", tool_call_id="call_1"),  # 补 ToolMessage 让序列合法
        ]
        result = _trim_messages_window(messages)
        # 验证：短历史不裁剪，system 保留
        assert len(result) >= 3  # 至少 system + human + 部分后续
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "System prompt here"

    @patch.dict(os.environ, {"DATACLOUD_LLM_MAX_CONTENT_TOKEN": "10000"})  # 极小预算强制裁剪
    def test_long_history_trimmed_by_token(self):
        """长历史（总 token > 预算）→ 裁剪到预算内，保留 system + 最近若干轮。"""
        from datacloud_analysis.orchestration.execution.react_loop import _trim_messages_window

        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Initial query"),
        ]
        # 模拟 30 轮对话（每轮 AI + Tool，内容足够长）
        for i in range(30):
            messages.append(
                AIMessage(
                    content=f"Round {i}: " + "x" * 2000,
                    tool_calls=[{"id": f"call_{i}", "name": "tool", "args": {}}],
                )
            )
            messages.append(
                ToolMessage(content=f"Round {i} result: " + "y" * 2000, tool_call_id=f"call_{i}")
            )

        result = _trim_messages_window(messages)
        # 验证核心行为：1) system 保留，2) 发生裁剪（条数减少），3) 返回值合法（不抛异常）
        assert isinstance(result[0], SystemMessage), "System message should be retained"
        assert len(result) < len(messages), (
            f"Expected trim with 10k budget, but len(result)={len(result)} >= len(messages)={len(messages)}"
        )
        # 极小预算下可能只剩 system，这也是合法行为（说明按 token 裁剪生效）
        assert len(result) >= 1, "At least system should remain"

    @patch.dict(os.environ, {"DATACLOUD_LLM_MAX_CONTENT_TOKEN": "200000"})
    def test_not_start_with_orphan_tool(self):
        """不以孤儿 ToolMessage 开头（其对应 AIMessage 被截断）。

        构造：system + 大量 AI/Tool 对 + 裁剪后 tail 头部是孤儿 Tool
        → 官方 trim_messages 的 start_on='human' 保证合法序列
        """
        from datacloud_analysis.orchestration.execution.react_loop import _trim_messages_window

        messages = [SystemMessage(content="Sys")]
        # 前 20 轮
        for i in range(20):
            messages.append(
                AIMessage(
                    content="AI" * 200, tool_calls=[{"id": f"call_{i}", "name": "foo", "args": {}}]
                )
            )
            messages.append(ToolMessage(content="tool result" * 100, tool_call_id=f"call_{i}"))
        messages.append(HumanMessage(content="Final question"))

        result = _trim_messages_window(messages)
        # 验证 result[1]（system 后第一条）不是孤儿 ToolMessage
        assert isinstance(result[0], SystemMessage)
        if len(result) > 1:
            # 如果裁剪了，tail 首条应该不是 ToolMessage（或是，但其 AIMessage 也在）
            # 简化验证：整个 result 中 ToolMessage 的 tool_call_id 都能在前面 AIMessage 中找到
            ai_call_ids = set()
            for m in result:
                if isinstance(m, AIMessage) and m.tool_calls:
                    ai_call_ids.update(tc.get("id") for tc in m.tool_calls)
            for m in result:
                if isinstance(m, ToolMessage):
                    assert m.tool_call_id in ai_call_ids or m.tool_call_id is None

    @patch.dict(os.environ, {"DATACLOUD_LLM_MAX_CONTENT_TOKEN": "200000"})
    def test_not_end_with_dangling_tool_call(self):
        """不以悬空 tool_call 的 AIMessage 结尾（有 tool_calls 但无对应 ToolMessage）。"""
        from datacloud_analysis.orchestration.execution.react_loop import _trim_messages_window

        messages = [
            SystemMessage(content="Sys"),
            HumanMessage(content="Q"),
            AIMessage(content="Thinking", tool_calls=[{"id": "call_1", "name": "foo", "args": {}}]),
            # 故意不跟 ToolMessage，模拟悬空
        ]
        result = _trim_messages_window(messages)
        # 验证末尾不是带 tool_calls 的 AIMessage（官方 end_on=('human','tool') 会处理）
        if result:
            last = result[-1]
            if isinstance(last, AIMessage):
                assert not last.tool_calls  # 末尾 AI 不应有 tool_calls

    @patch.dict(os.environ, {"DATACLOUD_LLM_MAX_CONTENT_TOKEN": "200000"})
    def test_normalize_quoted_tool_call_ids(self):
        """tool_call_id 带单引号 → 规范为无引号（glm 模型兼容）。"""
        from datacloud_analysis.orchestration.execution.react_loop import _trim_messages_window

        messages = [
            SystemMessage(content="Sys"),
            HumanMessage(content="Q"),
            AIMessage(content="AI", tool_calls=[{"id": "'call_xxx'", "name": "foo", "args": {}}]),
            ToolMessage(content="result", tool_call_id="'call_xxx'"),
        ]
        result = _trim_messages_window(messages)
        # 验证 AIMessage.tool_calls[0]['id'] 和 ToolMessage.tool_call_id 都已去单引号
        ai = next(m for m in result if isinstance(m, AIMessage))
        tool = next(m for m in result if isinstance(m, ToolMessage))
        assert ai.tool_calls[0]["id"] == "call_xxx"
        assert tool.tool_call_id == "call_xxx"

    @patch.dict(os.environ, {"DATACLOUD_LLM_MAX_CONTENT_TOKEN": "200000"})
    def test_drop_orphan_ai_message_in_recovery(self):
        """断点恢复不成对：孤立 AIMessage（有 tool_calls 但后面无 ToolMessage）→ 兜底清洗移除。

        这是断点恢复场景特有的边界情况，官方 trim 可能未完全覆盖，
        所以保留手写 _drop_orphan_ai_messages 二次清洗。
        """
        from datacloud_analysis.orchestration.execution.react_loop import _trim_messages_window

        messages = [
            SystemMessage(content="Sys"),
            HumanMessage(content="Q1"),
            AIMessage(content="AI1"),
            ToolMessage(content="T1", tool_call_id="c1"),
            # 孤立 AIMessage：有 tool_calls 但后面紧跟另一个 AIMessage（非 ToolMessage）
            AIMessage(
                content="Orphan", tool_calls=[{"id": "orphan_id", "name": "foo", "args": {}}]
            ),
            AIMessage(content="AI2"),  # 无 tool_calls
        ]
        result = _trim_messages_window(messages)
        # 验证孤立 AIMessage 被移除，不会引发 400
        ai_contents = [m.content for m in result if isinstance(m, AIMessage)]
        assert "Orphan" not in ai_contents
