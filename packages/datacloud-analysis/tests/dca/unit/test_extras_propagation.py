"""extras 透传链路测试（chatbi 对接方案）。

覆盖：
1. ``dispatch_tool`` 从 ``gateway_context.extras`` 读出 extras 并写入 ``InvocationContext``
2. 工具运行时通过 ``get_current_context().extras`` 能读到调用方传入的原始 dict
3. ``gateway_context`` 没有 ``extras`` 属性时不应崩溃
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from datacloud_data_sdk.context import get_current_context
from langchain_core.tools import tool

_captured_extras: list[Any] = []


@tool("__test_capture_extras")
async def _capture_extras_tool(reason: str = "") -> str:  # noqa: ARG001
    """测试专用：记录调用时刻 InvocationContext.extras。"""
    ctx = get_current_context()
    _captured_extras.append(getattr(ctx, "extras", "<missing>"))
    return "captured"


def _make_tool_call() -> dict[str, Any]:
    return {
        "name": "__test_capture_extras",
        "args": {"reason": "for-test"},
        "id": "tc_extras_001",
    }


@pytest.mark.asyncio
async def test_dispatch_tool_propagates_extras_from_gateway_context() -> None:
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    _captured_extras.clear()
    extras_input = {"cookie": "JSESSIONID=abc", "biz_token": ["x", "y"], "nested": {"k": 1}}
    gateway_context = SimpleNamespace(
        user_id="u1",
        session_id="s1",
        extras=extras_input,
    )

    await dispatch_tool(
        _make_tool_call(),
        {"__test_capture_extras": _capture_extras_tool},
        state={},
        gateway_context=gateway_context,
        loader=None,
    )

    assert _captured_extras == [extras_input]


@pytest.mark.asyncio
async def test_dispatch_tool_extras_none_when_gateway_context_lacks_attribute() -> None:
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    _captured_extras.clear()
    gateway_context = SimpleNamespace(user_id="u1", session_id="s1")  # 没有 extras

    await dispatch_tool(
        _make_tool_call(),
        {"__test_capture_extras": _capture_extras_tool},
        state={},
        gateway_context=gateway_context,
        loader=None,
    )

    assert _captured_extras == [None]


@pytest.mark.asyncio
async def test_dispatch_tool_extras_none_when_gateway_context_is_none() -> None:
    from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

    _captured_extras.clear()

    await dispatch_tool(
        _make_tool_call(),
        {"__test_capture_extras": _capture_extras_tool},
        state={},
        gateway_context=None,
        loader=None,
    )

    assert _captured_extras == [None]
