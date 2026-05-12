"""方案 B：react_loop 辅助函数单元测试（红 → 绿）。

覆盖设计文档 §4.3 单元测试 13 条：
  _extract_content_text / _extract_thinking_text / _is_meaningful_thinking / _emit_thinking_token
"""

from __future__ import annotations

import asyncio
import sys
import types
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ── 被测目标（尚未实现，导入会失败 → 红）────────────────────────────────────
from datacloud_analysis.orchestration.execution.react_loop import (
    _emit_thinking_token,
    _extract_content_text,
    _extract_thinking_text,
    _is_meaningful_thinking,
)

# ===========================================================================
# _extract_content_text
# ===========================================================================


class TestExtractContentText:
    # B-TC-04 & 单测1
    def test_str_input(self) -> None:
        assert _extract_content_text("hello") == "hello"

    # B-TC-04 & 单测2
    def test_none_input(self) -> None:
        assert _extract_content_text(None) == ""

    # B-TC-04 & 单测3
    def test_empty_str(self) -> None:
        assert _extract_content_text("") == ""

    # 单测4：list 中包含 TextBlock（dict 形式）
    def test_list_text_block_dict(self) -> None:
        content = [{"type": "text", "text": "text content"}]
        assert _extract_content_text(content) == "text content"

    # 单测5：list 中只有 ThinkingBlock → 返回空（ThinkingBlock 不是 TextBlock）
    def test_list_thinking_block_ignored(self) -> None:
        content = [{"type": "thinking", "thinking": "inner thought"}]
        assert _extract_content_text(content) == ""

    # 混合：ThinkingBlock + TextBlock → 只取 text
    def test_list_mixed_blocks(self) -> None:
        content = [
            {"type": "thinking", "thinking": "hidden thought"},
            {"type": "text", "text": "visible text"},
        ]
        assert _extract_content_text(content) == "visible text"

    # 多个 TextBlock 拼接
    def test_list_multiple_text_blocks(self) -> None:
        content = [
            {"type": "text", "text": "part1"},
            {"type": "text", "text": "part2"},
        ]
        assert _extract_content_text(content) == "part1part2"

    # 对象形式的 TextBlock（attr 访问）
    def test_list_text_block_object(self) -> None:
        block = MagicMock()
        block.type = "text"
        block.text = "attr text"
        assert _extract_content_text([block]) == "attr text"

    # 意外类型兜底：不报错
    def test_unexpected_type_no_error(self) -> None:
        result = _extract_content_text(12345)  # type: ignore[arg-type]
        assert isinstance(result, str)


# ===========================================================================
# _extract_thinking_text
# ===========================================================================


class TestExtractThinkingText:
    # B-TC-06 & 单测6：str 输入（非 list）→ 返回空
    def test_str_input_returns_empty(self) -> None:
        assert _extract_thinking_text("some text") == ""

    # 单测7：None → 返回空
    def test_none_input_returns_empty(self) -> None:
        assert _extract_thinking_text(None) == ""

    # 单测8：ThinkingBlock list（dict 形式）
    def test_list_thinking_block_dict(self) -> None:
        content = [{"type": "thinking", "thinking": "chain of thought"}]
        assert _extract_thinking_text(content) == "chain of thought"

    # 单测9：未知类型 block → 返回空（B-TC-06）
    def test_list_unknown_block_type(self) -> None:
        content = [{"type": "unknown", "data": "..."}]
        assert _extract_thinking_text(content) == ""

    # TextBlock 不提取
    def test_list_text_block_not_extracted(self) -> None:
        content = [{"type": "text", "text": "visible text"}]
        assert _extract_thinking_text(content) == ""

    # 对象形式 ThinkingBlock
    def test_list_thinking_block_object(self) -> None:
        block = MagicMock()
        block.type = "thinking"
        block.thinking = "object thought"
        assert _extract_thinking_text([block]) == "object thought"

    # 多个 ThinkingBlock 拼接
    def test_list_multiple_thinking_blocks(self) -> None:
        content = [
            {"type": "thinking", "thinking": "part1"},
            {"type": "thinking", "thinking": "part2"},
        ]
        assert _extract_thinking_text(content) == "part1part2"


# ===========================================================================
# _is_meaningful_thinking
# ===========================================================================


class TestIsMeaningfulThinking:
    # 单测10：空字符串
    def test_empty_string(self) -> None:
        assert _is_meaningful_thinking("") is False

    # 单测11：过短（< 10字符）
    def test_too_short(self) -> None:
        assert _is_meaningful_thinking("好的") is False
        assert _is_meaningful_thinking("OK") is False

    # 单测12：短句客套话（以前缀开头且 < 30字符）
    def test_short_filler_phrase(self) -> None:
        assert _is_meaningful_thinking("好的，我来帮您查询一下") is False
        assert _is_meaningful_thinking("当然，没问题") is False
        assert _is_meaningful_thinking("根据您的需求") is False

    # 单测13：有实质内容的推理
    def test_valid_reasoning(self) -> None:
        assert _is_meaningful_thinking("用户想查当季营收，需要过滤时间范围并按区域分组统计") is True

    # 边界：以客套前缀开头但超过30字符 → 不过滤（内容可能有价值）
    def test_long_text_starting_with_filler_not_filtered(self) -> None:
        long_text = "好的，让我来分析一下用户的查询需求，用户希望获取本季度各大区的营收合计数据"
        assert _is_meaningful_thinking(long_text) is True

    # 英文有意义内容
    def test_english_meaningful(self) -> None:
        assert _is_meaningful_thinking("The user wants quarterly revenue grouped by region") is True

    # 恰好10字符边界
    def test_exactly_ten_chars(self) -> None:
        # 10 个中文字符应通过长度检查
        assert _is_meaningful_thinking("用户想查营收数据统计") is True


# ===========================================================================
# _emit_thinking_token
# ===========================================================================


@contextmanager
def _mock_emit_runtime_modules() -> Any:
    """Mock runtime-only modules used by _emit_thinking_token."""

    by_framework = types.ModuleType("by_framework")
    by_framework_core = types.ModuleType("by_framework.core")
    by_framework_protocol = types.ModuleType("by_framework.core.protocol")
    by_framework_content_type = types.ModuleType("by_framework.core.protocol.content_type")

    class _ReasoningLogDelta:
        value = "reasoningLogDelta"

    class _EventType:
        REASONING_LOG_DELTA = _ReasoningLogDelta()

    class _ThinkText:
        value = "1002"

    class _SseReasonMessageType:
        think_text = _ThinkText()

    class _StreamChunkEvent:
        def __init__(self, content: str) -> None:
            self.content = content

    by_framework.EventType = _EventType
    by_framework.StreamChunkEvent = _StreamChunkEvent
    by_framework_content_type.SseReasonMessageType = _SseReasonMessageType

    datacloud_data_sdk = types.ModuleType("datacloud_data_sdk")
    datacloud_stream_text = types.ModuleType("datacloud_data_sdk.stream_text")
    datacloud_stream_text.coerce_stream_chunk_text = lambda x: x
    datacloud_data_sdk.stream_text = datacloud_stream_text

    with patch.dict(
        sys.modules,
        {
            "by_framework": by_framework,
            "by_framework.core": by_framework_core,
            "by_framework.core.protocol": by_framework_protocol,
            "by_framework.core.protocol.content_type": by_framework_content_type,
            "datacloud_data_sdk": datacloud_data_sdk,
            "datacloud_data_sdk.stream_text": datacloud_stream_text,
        },
    ):
        yield


class TestEmitThinkingToken:
    # 单测：token 为空 → 不调用 adispatch_custom_event
    def test_no_gateway_no_error(self) -> None:
        asyncio.get_event_loop().run_until_complete(
            _emit_thinking_token("some thought", message_id="test_msg")
        )

    # 单测：token 为空 → 不调用 emit_chunk
    def test_empty_token_no_emit(self) -> None:
        with patch("langchain_core.callbacks.adispatch_custom_event") as mock_dispatch:
            asyncio.get_event_loop().run_until_complete(
                _emit_thinking_token("", message_id="test_msg")
            )
            mock_dispatch.assert_not_called()

    # 单测：emit 抛异常 → 静默降级，不向上传播（B-TC-07）
    def test_emit_chunk_exception_silent(self) -> None:
        async def _raise(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("network error")

        with patch("langchain_core.callbacks.adispatch_custom_event", side_effect=_raise):
            asyncio.get_event_loop().run_until_complete(
                _emit_thinking_token("some thought", message_id="test_msg")
            )

    # 正常推送：adispatch_custom_event 被调用一次
    def test_normal_emit_called(self) -> None:
        dispatched: list = []

        async def _capture(name: str, data: Any, **kw: Any) -> None:
            dispatched.append((name, data))

        with patch("langchain_core.callbacks.adispatch_custom_event", side_effect=_capture):
            asyncio.get_event_loop().run_until_complete(
                _emit_thinking_token("用户想查营收数据", message_id="test_msg")
            )
        assert len(dispatched) == 1

    # 推送时使用正确的 event_type
    def test_emit_uses_reasoning_log_delta_event_type(self) -> None:
        captured: dict = {}

        async def _capture(name: str, data: Any, **kw: Any) -> None:
            captured.update(data if isinstance(data, dict) else {})

        with patch("langchain_core.callbacks.adispatch_custom_event", side_effect=_capture):
            asyncio.get_event_loop().run_until_complete(
                _emit_thinking_token("推理过程文字", message_id="test_msg")
            )
        assert captured.get("event_type") == "reasoningLogDelta"
        assert captured.get("content_type") == "1002"

    # 推送时 message_id 按传入值透传
    def test_emit_uses_passed_message_id(self) -> None:
        captured: dict = {}

        async def _capture(name: str, data: Any, **kw: Any) -> None:
            captured.update(data if isinstance(data, dict) else {})

        with patch("langchain_core.callbacks.adispatch_custom_event", side_effect=_capture):
            asyncio.get_event_loop().run_until_complete(
                _emit_thinking_token("推理过程文字", message_id="round_abc123")
            )
        assert captured.get("message_id") == "round_abc123", (
            "adispatch_custom_event 收到的 message_id 应与传入值完全一致"
        )
