"""方案 A：query_clarification_plugin 改造后的验收用例（红 → 绿）。

新行为：读取 ambiguous_params 而非 knowledge_payload，按需触发知识增强。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    before_call_back,
)
from datacloud_analysis.tool_hook_plugins.types import HookContext


def _make_ctx(
    tool_name: str = "data_query_grid",
    tool_params: dict | None = None,
    user_query: str = "查询营收",
    # 新字段（改造后 LLM 填写）
    intent_reason: str = "用户查询营收",
    extraction_confidence: float = 0.9,
    ambiguous_params: list | None = None,
) -> HookContext:
    params = dict(tool_params or {"query": "查询营收"})
    # 模拟 LLM 填写了三个元字段（inject_ambiguity_fields 注入后 LLM 会填）
    params["intent_reason"] = intent_reason
    params["extraction_confidence"] = extraction_confidence
    params["ambiguous_params"] = ambiguous_params if ambiguous_params is not None else []
    return {
        "tool_name": tool_name,
        "tool_params": params,
        "user_query": user_query,
        "knowledge_snippets": [],
        "term_context": [],
        # 旧字段保留但不再依赖
        "knowledge_payload": {},
    }


# ---------------------------------------------------------------------------
# A-TC-01：ambiguous_params=[] → 直接跳过，不触发知识增强
# ---------------------------------------------------------------------------


def test_atc01_no_ambiguous_params_skips_clarification() -> None:
    ctx = _make_ctx(ambiguous_params=[])

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
        "._call_query_clarification",
        new=AsyncMock(),
    ) as mock_clarify:
        result = asyncio.get_event_loop().run_until_complete(before_call_back(ctx))

    mock_clarify.assert_not_called()
    assert result is None, f"无歧义时应返回 None（直接执行），实际：{result}"


# ---------------------------------------------------------------------------
# A-TC-05：元字段被 pop 剔除，tool_params 不含三个元字段
# ---------------------------------------------------------------------------


def test_atc05_meta_fields_popped_from_tool_params() -> None:
    ctx = _make_ctx(
        ambiguous_params=[],
        intent_reason="查营收",
        extraction_confidence=0.95,
    )
    asyncio.get_event_loop().run_until_complete(before_call_back(ctx))

    remaining = ctx["tool_params"]
    assert "intent_reason" not in remaining, "intent_reason 应被 pop"
    assert "extraction_confidence" not in remaining, "extraction_confidence 应被 pop"
    assert "ambiguous_params" not in remaining, "ambiguous_params 应被 pop"


# ---------------------------------------------------------------------------
# A-TC-02：ambiguous_params 非空 → 触发 _call_query_clarification
#          needs_clarification=False → 注入 contextKnowledge
# ---------------------------------------------------------------------------


def test_atc02_ambiguous_triggers_clarification_and_injects_knowledge() -> None:
    ctx = _make_ctx(
        tool_name="data_query_grid",
        tool_params={"query": "查询营收", "contextKnowledge": ""},
        ambiguous_params=["time_range"],
    )

    mock_result = MagicMock()
    mock_result.needs_clarification = False
    mock_result.form = ""
    mock_result.knowledge = "营收 → 企业总营收（万元）"

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
        "._call_query_clarification",
        new=AsyncMock(return_value=mock_result),
    ):
        result = asyncio.get_event_loop().run_until_complete(before_call_back(ctx))

    assert result is not None
    assert result.get("action") == "patch"
    patched = result["patch"]["tool_params"]
    assert patched.get("contextKnowledge") == "营收 → 企业总营收（万元）"


# ---------------------------------------------------------------------------
# A-TC-03：ambiguous_params 非空 + needs_clarification=True → interrupt
# ---------------------------------------------------------------------------


def test_atc03_ambiguous_triggers_interrupt_when_needs_clarification() -> None:
    ctx = _make_ctx(
        tool_name="data_query_grid",
        ambiguous_params=["target_object", "time_range"],
    )

    paradigm_list = [{"name": "营收", "fieldName": "企业总营收（万元）"}]

    mock_result = MagicMock()
    mock_result.needs_clarification = True
    mock_result.form = '{"paradigmList": [{"name": "营收", "fieldName": "企业总营收（万元）"}]}'
    mock_result.knowledge = ""

    with (
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
            "._call_query_clarification",
            new=AsyncMock(return_value=mock_result),
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin.interrupt",
            return_value={"paradigmList": paradigm_list},
        ),
    ):
        result = asyncio.get_event_loop().run_until_complete(before_call_back(ctx))

    # 追问场景：返回 patch（重建 tool_params）
    assert result is not None
    assert result.get("action") == "patch"


# ---------------------------------------------------------------------------
# 日志记录：ambiguous_params 信息应写入日志（A-TC-05）
# ---------------------------------------------------------------------------


def test_atc05_log_contains_ambiguous_info(caplog) -> None:
    import logging

    ctx = _make_ctx(
        ambiguous_params=["time_range"],
        intent_reason="查本季度营收",
        extraction_confidence=0.6,
    )

    mock_result = MagicMock()
    mock_result.needs_clarification = False
    mock_result.form = ""
    mock_result.knowledge = ""

    with (
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
            "._call_query_clarification",
            new=AsyncMock(return_value=mock_result),
        ),
        caplog.at_level(logging.INFO, logger="datacloud_analysis"),
    ):
        asyncio.get_event_loop().run_until_complete(before_call_back(ctx))

    combined = " ".join(caplog.messages)
    assert "time_range" in combined or "ambiguous" in combined.lower() or "triggered" in combined, (
        f"日志应包含歧义参数信息，实际日志：{combined}"
    )


# ---------------------------------------------------------------------------
# 非数据工具：不处理（兼容现有行为）
# ---------------------------------------------------------------------------


def test_non_data_tool_returns_none_with_ambiguous_fields() -> None:
    ctx = _make_ctx(tool_name="send_email", ambiguous_params=["recipient"])
    result = asyncio.get_event_loop().run_until_complete(before_call_back(ctx))
    assert result is None


# ---------------------------------------------------------------------------
# _call_query_clarification 异常：静默降级，返回 None
# ---------------------------------------------------------------------------


def test_clarification_exception_silent_fallback() -> None:
    ctx = _make_ctx(ambiguous_params=["time_range"])

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
        "._call_query_clarification",
        new=AsyncMock(side_effect=RuntimeError("network error")),
    ):
        result = asyncio.get_event_loop().run_until_complete(before_call_back(ctx))

    # 异常时不中断流程，返回 None
    assert result is None


# ---------------------------------------------------------------------------
# query_* 工具（非 data_query_*）：有歧义时触发澄清，但不注入 contextKnowledge
# ---------------------------------------------------------------------------


def test_query_star_tool_no_context_knowledge_injection() -> None:
    ctx = _make_ctx(
        tool_name="query_order",
        tool_params={"select": [], "filters": []},
        ambiguous_params=["time_range"],
    )

    mock_result = MagicMock()
    mock_result.needs_clarification = False
    mock_result.form = ""
    mock_result.knowledge = "有知识内容"

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
        "._call_query_clarification",
        new=AsyncMock(return_value=mock_result),
    ):
        result = asyncio.get_event_loop().run_until_complete(before_call_back(ctx))

    # query_* 不支持 contextKnowledge，返回 None 或 patch 中不含 contextKnowledge
    if result is not None:
        patched = result.get("patch", {}).get("tool_params", {})
        assert "contextKnowledge" not in patched, "query_* 工具不应注入 contextKnowledge"
