"""respond_node L2/L3 兜底逻辑单元测试。

验收目标（文档 1.4.4 阶段二）：
- TC-RN-1: react_final 已设置 → 直接透传给 format_result，不覆盖
- TC-RN-2: react_final 为空 + 有 AIMessage 文字 → 从 AIMessage 构建 react_final
- TC-RN-3: react_final 为空 + 无 AIMessage → answer 为空字符串
- TC-RN-4: react_final 为空 + answer_streamed=True → answer_streamed 被保留
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from datacloud_analysis.orchestration.respond.node import respond_node
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig


def _make_config() -> RunnableConfig:
    return {"configurable": {}}  # type: ignore[return-value]


# ═══════════════════════════════════════════════════════════════════════════════
# TC-RN-1: react_final 已设置 → 直接透传
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rn1_react_final_set_passthrough() -> None:
    """TC-RN-1: react_final 已有内容时，format_result 应收到原始 react_final，不被覆盖。"""
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="q"), AIMessage(content="直接回答")],
        "react_final": {"result_type": "text", "answer": "已有答案", "answer_streamed": False},
    }
    captured: list[dict[str, Any]] = []

    async def _fake_format(
        rf: dict[str, Any], gw_ctx: Any, workspace_dir: Any, config: Any = None
    ) -> None:
        captured.append(dict(rf))

    with patch(
        "datacloud_analysis.orchestration.respond.node.format_result",
        side_effect=_fake_format,
    ):
        await respond_node(state, _make_config())

    assert len(captured) == 1
    assert captured[0]["answer"] == "已有答案", (
        f"react_final 已设置时不应被覆盖，实际 answer={captured[0]['answer']!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TC-RN-2: react_final 为空 + AIMessage 有文字 → 从 AIMessage 构建
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rn2_l2_fallback_extracts_ai_message_text() -> None:
    """TC-RN-2: react_final 为空时，从最后一条 AIMessage 提取文字构建兜底 react_final。"""
    state: dict[str, Any] = {
        "messages": [
            HumanMessage(content="q"),
            AIMessage(content="L2 直接文字回答"),
        ],
        "react_final": None,
    }
    captured: list[dict[str, Any]] = []

    async def _fake_format(
        rf: dict[str, Any], gw_ctx: Any, workspace_dir: Any, config: Any = None
    ) -> None:
        captured.append(dict(rf))

    with patch(
        "datacloud_analysis.orchestration.respond.node.format_result",
        side_effect=_fake_format,
    ):
        await respond_node(state, _make_config())

    assert len(captured) == 1
    rf = captured[0]
    assert rf.get("result_type") == "text", (
        f"result_type 应为 'text'，实际: {rf.get('result_type')!r}"
    )
    assert rf.get("answer") == "L2 直接文字回答", (
        f"answer 应为 AIMessage content，实际: {rf.get('answer')!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TC-RN-3: react_final 为空 + 无 AIMessage → answer 空字符串
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rn3_l3_fallback_no_ai_message_empty_answer() -> None:
    """TC-RN-3: react_final 为空且无 AIMessage 时，answer 应为空字符串。"""
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="q")],
        "react_final": {},
    }
    captured: list[dict[str, Any]] = []

    async def _fake_format(
        rf: dict[str, Any], gw_ctx: Any, workspace_dir: Any, config: Any = None
    ) -> None:
        captured.append(dict(rf))

    with patch(
        "datacloud_analysis.orchestration.respond.node.format_result",
        side_effect=_fake_format,
    ):
        await respond_node(state, _make_config())

    assert len(captured) == 1
    assert captured[0].get("answer") == "", (
        f"无 AIMessage 时 answer 应为空字符串，实际: {captured[0].get('answer')!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TC-RN-4: react_final 为空 + answer_streamed=True → 保留 answer_streamed
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rn4_l2_fallback_preserves_answer_streamed() -> None:
    """TC-RN-4: 兜底构建 react_final 时，answer_streamed 从 state 读取并保留。"""
    state: dict[str, Any] = {
        "messages": [
            HumanMessage(content="q"),
            AIMessage(content="流式回答内容"),
        ],
        "react_final": None,
        "answer_streamed": True,
    }
    captured: list[dict[str, Any]] = []

    async def _fake_format(
        rf: dict[str, Any], gw_ctx: Any, workspace_dir: Any, config: Any = None
    ) -> None:
        captured.append(dict(rf))

    with patch(
        "datacloud_analysis.orchestration.respond.node.format_result",
        side_effect=_fake_format,
    ):
        await respond_node(state, _make_config())

    assert len(captured) == 1
    assert captured[0].get("answer_streamed") is True, (
        f"answer_streamed 应为 True，实际: {captured[0].get('answer_streamed')!r}"
    )
