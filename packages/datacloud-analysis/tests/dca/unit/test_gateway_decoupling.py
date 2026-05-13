"""TC-GD: Gateway 解耦验证测试（先红后绿）。

验证目标（GREEN 通过标准）：
- emit 函数使用 adispatch_custom_event 而非 gateway_context.emit_chunk
- dc_stream_chunk payload 结构符合规范（event_type / content_type / message_id / content）
- react_loop.py / tool_wrapper.py / formatter.py 源码中不含 by_framework 导入

RED 失败原因：
- TC-GD-1~4：当前函数签名首参为 gateway_context，以新签名调用会触发 TypeError
- TC-GD-5~7：当前源码仍含 from by_framework import ... 懒导入
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any
from unittest.mock import patch

import pytest

# ── 辅助 ─────────────────────────────────────────────────────────────────────


def _read_module_source(module_name: str) -> str:
    """读取已导入（或按需导入）模块的 .py 源文件内容。"""
    import importlib  # noqa: PLC0415

    mod = sys.modules.get(module_name) or importlib.import_module(module_name)
    src_file = getattr(mod, "__file__", None)
    if src_file is None:
        raise RuntimeError(f"无法获取模块 {module_name!r} 的源码路径")
    return pathlib.Path(src_file).read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# TC-GD-1 & TC-GD-2: react_loop._emit_thinking_token
#   - 新签名: (token, *, message_id)，无 gateway_context
#   - 调用 adispatch_custom_event("dc_stream_chunk", {...})
#   - payload: event_type="reasoning_log_delta", content_type="think_text"
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tc_gd1_thinking_token_dispatches_custom_event() -> None:
    """TC-GD-1: _emit_thinking_token 调用 adispatch_custom_event 而非 emit_chunk。

    RED：当前签名 (gateway_context, token, *, message_id) 以新签名调用报 TypeError。
    GREEN：签名改为 (token, *, message_id)，函数触发 adispatch_custom_event。
    """
    from datacloud_analysis.orchestration.execution.react_loop import (  # noqa: PLC0415
        _emit_thinking_token,
    )

    dispatched: list[tuple[str, dict[str, Any]]] = []

    async def _fake_dispatch(name: str, data: Any, *, config: Any = None, **kw: Any) -> None:
        dispatched.append((name, dict(data) if isinstance(data, dict) else {"raw": data}))

    with patch("langchain_core.callbacks.adispatch_custom_event", side_effect=_fake_dispatch):
        await _emit_thinking_token(
            "这是一段有意义的推理内容，超过十个字符。",
            message_id="think-001",
        )

    assert len(dispatched) >= 1, "adispatch_custom_event 应至少被调用一次"
    event_name, payload = dispatched[0]
    assert event_name == "dc_stream_chunk", f"事件名应为 dc_stream_chunk，实际：{event_name!r}"


@pytest.mark.asyncio
async def test_tc_gd2_thinking_token_payload_structure() -> None:
    """TC-GD-2: _emit_thinking_token 的 dc_stream_chunk payload 结构正确。

    RED：同 TC-GD-1（TypeError 或 payload 不符合规范）。
    GREEN：payload 含正确的 event_type / content_type / message_id / content。
    """
    from datacloud_analysis.orchestration.execution.react_loop import (  # noqa: PLC0415
        _emit_thinking_token,
    )

    dispatched: list[tuple[str, dict[str, Any]]] = []

    async def _fake_dispatch(name: str, data: Any, *, config: Any = None, **kw: Any) -> None:
        dispatched.append((name, dict(data) if isinstance(data, dict) else {"raw": data}))

    token_text = "这是一段有意义的推理内容，超过十个字符。"
    msg_id = "think-002"

    with patch("langchain_core.callbacks.adispatch_custom_event", side_effect=_fake_dispatch):
        await _emit_thinking_token(token_text, message_id=msg_id)

    assert dispatched, "adispatch_custom_event 未被调用"
    _, payload = dispatched[0]
    assert payload.get("event_type") == "reasoningLogDelta", (
        f"event_type 应为 reasoningLogDelta，实际：{payload}"
    )
    assert payload.get("content_type") == "1002", f"content_type 应为 1002，实际：{payload}"
    assert payload.get("message_id") == msg_id, f"message_id 应为 {msg_id!r}，实际：{payload}"
    assert payload.get("content"), "content 不应为空"


# ═══════════════════════════════════════════════════════════════════════════════
# TC-GD-3: react_loop._emit_answer_token
#   - 新签名: (token, *, message_id)
#   - payload: event_type="answer_delta", content_type="text"
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tc_gd3_answer_token_dispatches_custom_event() -> None:
    """TC-GD-3: _emit_answer_token 调用 adispatch_custom_event（event_type=answer_delta）。

    RED：当前签名 (gateway_context, token, *, message_id) 以新签名调用报 TypeError。
    GREEN：新签名触发 adispatch_custom_event，payload 含正确字段。
    """
    from datacloud_analysis.orchestration.execution.react_loop import (  # noqa: PLC0415
        _emit_answer_token,
    )

    dispatched: list[tuple[str, dict[str, Any]]] = []

    async def _fake_dispatch(name: str, data: Any, *, config: Any = None, **kw: Any) -> None:
        dispatched.append((name, dict(data) if isinstance(data, dict) else {"raw": data}))

    with patch("langchain_core.callbacks.adispatch_custom_event", side_effect=_fake_dispatch):
        await _emit_answer_token("最终答案内容", message_id="ans-001")

    assert dispatched, "adispatch_custom_event 未被调用"
    event_name, payload = dispatched[0]
    assert event_name == "dc_stream_chunk", f"事件名应为 dc_stream_chunk，实际：{event_name!r}"
    assert payload.get("event_type") == "answerDelta", (
        f"event_type 应为 answerDelta，实际：{payload}"
    )
    assert payload.get("content_type") == "1002", f"content_type 应为 1002，实际：{payload}"
    assert payload.get("message_id") == "ans-001"


# ═══════════════════════════════════════════════════════════════════════════════
# TC-GD-4: formatter._emit_text
#   - 新签名: (text, *, message_id)
#   - payload: event_type="answer_delta", content_type="text"
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tc_gd4_emit_text_dispatches_custom_event() -> None:
    """TC-GD-4: formatter._emit_text 调用 adispatch_custom_event（event_type=answer_delta）。

    RED：当前签名 (gateway_context, text, *, message_id) 以新签名调用报 TypeError。
    GREEN：新签名触发 adispatch_custom_event，payload 含正确字段。
    """
    from datacloud_analysis.orchestration.respond.formatter import (  # noqa: PLC0415
        _emit_text,
    )

    dispatched: list[tuple[str, dict[str, Any]]] = []

    async def _fake_dispatch(name: str, data: Any, *, config: Any = None, **kw: Any) -> None:
        dispatched.append((name, dict(data) if isinstance(data, dict) else {"raw": data}))

    with patch("langchain_core.callbacks.adispatch_custom_event", side_effect=_fake_dispatch):
        await _emit_text("这是最终答案文本", message_id="text-001")

    assert dispatched, "adispatch_custom_event 未被调用"
    event_name, payload = dispatched[0]
    assert event_name == "dc_stream_chunk", f"事件名应为 dc_stream_chunk，实际：{event_name!r}"
    assert payload.get("event_type") == "answerDelta", (
        f"event_type 应为 answerDelta，实际：{payload}"
    )
    assert payload.get("content_type") == "1002", f"content_type 应为 1002，实际：{payload}"
    assert payload.get("message_id") == "text-001"
    assert payload.get("content"), "content 不应为空"


# ═══════════════════════════════════════════════════════════════════════════════
# TC-GD-5 ~ TC-GD-7: 源码无 by_framework 导入
# ═══════════════════════════════════════════════════════════════════════════════


def test_tc_gd5_react_loop_no_by_framework_import() -> None:
    """TC-GD-5: react_loop.py 源码不含 'from by_framework' 导入。

    RED：当前源码含懒导入 from by_framework import ...。
    GREEN：所有懒导入替换为 adispatch_custom_event。
    """
    source = _read_module_source("datacloud_analysis.orchestration.execution.react_loop")
    assert "from by_framework" not in source, "react_loop.py 仍含 by_framework 导入，解耦未完成"


def test_tc_gd6_tool_wrapper_no_by_framework_import() -> None:
    """TC-GD-6: tool_wrapper.py 源码不含 'from by_framework' 导入。

    RED：_emit_think / _emit_child_think 含 from by_framework import StreamChunkEvent。
    GREEN：改用 adispatch_custom_event，移除 by_framework 导入。
    """
    source = _read_module_source("datacloud_analysis.orchestration.execution.tool_wrapper")
    assert "from by_framework" not in source, "tool_wrapper.py 仍含 by_framework 导入，解耦未完成"


def test_tc_gd7_formatter_no_by_framework_import() -> None:
    """TC-GD-7: formatter.py 源码不含 'from by_framework' 导入。

    RED：_emit_text / _emit_json_as_6001 / _stream_csv_as_6001 / _emit_query_result_as_6001
         含懒导入 from by_framework import ...。
    GREEN：全部替换为 adispatch_custom_event。
    """
    source = _read_module_source("datacloud_analysis.orchestration.respond.formatter")
    assert "from by_framework" not in source, "formatter.py 仍含 by_framework 导入，解耦未完成"
