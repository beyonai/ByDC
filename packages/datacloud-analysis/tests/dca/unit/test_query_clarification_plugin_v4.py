"""TC-1 ~ TC-3: _analyze_clarification 缓存命中/未命中验收（方案A State 缓存）。

对应《恢复中断优化方案》§5：推荐方案详细设计。

V0.1 方案 A（已废弃，仅供历史参考）——V0.3 改用 ClarificationNeededError 替代 interrupt()。
"""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── 辅助函数 ───────────────────────────────────────────────────────────────────

TOOL = "query_ads_enterprise_analysis"
QUERY = "查询高营收的企业"

_PARADIGM_LIST: list[dict[str, Any]] = [
    {
        "paradigmCode": "P001",
        "paradigmName": "营收",
        "candidates": [{"keyword": "total_revenue", "displayName": "企业总营收（万元）"}],
    }
]

_RESUME_VALUE: dict[str, Any] = {
    "paradigmList": [
        {
            "query": QUERY,
            "paradigmList": [{"paradigmCode": "P001", "choiceKeyword": "total_revenue"}],
        }
    ],
    "metadata": {"clarify_knowledge": "营收=企业总营收（万元）"},
}


def _expected_cache_key(tool_name: str, query: str) -> str:
    """复现 _make_cache_key 算法，供测试断言用。"""
    digest = hashlib.md5(query.encode()).hexdigest()[:12]  # noqa: S324
    return f"{tool_name}:{digest}"


def _make_ctx(
    tool_name: str,
    tool_params: dict[str, Any],
    state: dict[str, Any],
    loader: Any = None,
) -> dict[str, Any]:
    """构造含 state 引用的 HookContext。"""
    return {
        "tool_name": tool_name,
        "tool_params": dict(tool_params),
        "user_query": tool_params.get("query", ""),
        "metadata": {"loader": loader, "state": state},
        "session_id": "test-session",
        "knowledge_snippets": [],
        "term_context": [],
        "knowledge_payload": {},
    }


def _make_loader() -> Any:
    """构造 loader：只有 total_revenue/企业总营收，使得 '营收' 无法精确命中。"""
    loader = MagicMock()
    f = MagicMock()
    f.field_code = "total_revenue"
    f.field_name = "企业总营收（万元）"
    f.property_kind = "physical"
    cls = MagicMock()
    cls.fields = [f]
    loader.get_ontology_class.return_value = cls
    loader._scenes = {}
    return loader


def _params_with_unresolvable_term() -> dict[str, Any]:
    """返回含未知术语 '营收' 的 tool_params，触发 NEED_CONFIRM 路径。"""
    return {
        "query": QUERY,
        "filters": [{"field_name_cn": "营收", "op": "gt", "value": "高"}],
        "complex_conditions": [],
    }


# ── TC-1：CACHE MISS → SDK 被调用，缓存在 interrupt 前写入 state ──────────────


@pytest.mark.skip(
    reason="V0.1->V0.3: before_call_back now raises ClarificationNeededError instead of interrupt()"
)
@pytest.mark.asyncio
async def test_TC1_cache_miss_sdk_called_and_cache_written_before_interrupt() -> None:
    """TC-1: state 无缓存 → _analyze_clarification 被调用 1 次，interrupt 前缓存已写入 state。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    state: dict[str, Any] = {}
    cache_at_interrupt: dict[str, Any] = {}

    def _fake_interrupt(payload: Any) -> Any:
        # 此时 state 中应已写入缓存
        cache_at_interrupt.update(state.get("_clarification_cache") or {})
        return _RESUME_VALUE

    with (
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
            "._analyze_clarification",
            return_value=(_PARADIGM_LIST, "知识库片段"),
        ) as mock_analyze,
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin.interrupt",
            side_effect=_fake_interrupt,
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
            "._format_clarification",
            return_value={"filters": [{"field": "total_revenue", "op": "gt", "value": 100}]},
        ),
    ):
        ctx = _make_ctx(TOOL, _params_with_unresolvable_term(), state, loader=_make_loader())
        await before_call_back(ctx)  # type: ignore[arg-type]

    assert mock_analyze.call_count == 1, (
        f"CACHE MISS 路径：_analyze_clarification 应被调用 1 次，实际 {mock_analyze.call_count} 次"
    )
    expected_key = _expected_cache_key(TOOL, QUERY)
    assert cache_at_interrupt.get("cache_key") == expected_key, (
        f"interrupt 调用前 state 应已写入 cache_key={expected_key!r}，"
        f"实际 cache_at_interrupt={cache_at_interrupt}"
    )


# ── TC-2：CACHE HIT → 整个分析块（414-467）全部跳过 ─────────────────────────

# 完整缓存：包含 resume 路径所需的所有字段
_FULL_CACHE: dict[str, Any] = {
    "cache_key": "",  # 由各测试用例按实际 key 填充
    "paradigm_list": _PARADIGM_LIST,
    "clarify_knowledge": "缓存的知识片段",
    "structured_input": {
        "filters": [{"field_name_cn": "营收", "op": "gt", "value": "高"}],
        "complex_conditions": [],
    },
    "is_compute": False,
    "resolved": {},
    "is_complex": False,
}


@pytest.mark.skip(
    reason="V0.1->V0.3: _clarification_cache scheme replaced by ClarificationNeededError"
)
@pytest.mark.asyncio
async def test_TC2_cache_hit_full_skip() -> None:
    """TC-2: state 已有完整缓存 → _analyze_clarification 和 _get_field_catalog 均不被调用。

    验收标准：CACHE HIT 时函数在 line 414 之前（工具名检查后）立即跳转到 resume 路径，
    跳过 catalog 加载、术语解析、SDK 分析等全部首次分析逻辑。
    """
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    cache = {**_FULL_CACHE, "cache_key": _expected_cache_key(TOOL, QUERY)}
    state: dict[str, Any] = {"_clarification_cache": cache}

    def _fake_interrupt(payload: Any) -> Any:
        return _RESUME_VALUE

    with (
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
            "._analyze_clarification",
        ) as mock_analyze,
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
            "._get_field_catalog",
        ) as mock_catalog,
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin.interrupt",
            side_effect=_fake_interrupt,
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
            "._format_clarification",
            return_value={"filters": [{"field": "total_revenue", "op": "gt", "value": 100}]},
        ),
    ):
        ctx = _make_ctx(TOOL, _params_with_unresolvable_term(), state, loader=_make_loader())
        await before_call_back(ctx)  # type: ignore[arg-type]

    assert mock_analyze.call_count == 0, (
        f"CACHE HIT 路径：_analyze_clarification 不应被调用，实际调用 {mock_analyze.call_count} 次"
    )
    assert mock_catalog.call_count == 0, (
        f"CACHE HIT 路径：_get_field_catalog 不应被调用（全跳过），实际调用 {mock_catalog.call_count} 次"
    )


# ── TC-3：format 完成后缓存从 state 清除 ─────────────────────────────────────


@pytest.mark.skip(
    reason="V0.1->V0.3: _clarification_cache scheme replaced by ClarificationNeededError"
)
@pytest.mark.asyncio
async def test_TC3_cache_cleared_after_format_clarification() -> None:
    """TC-3: format_clarification 完成后，state 中的 _clarification_cache 被清除。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    state: dict[str, Any] = {}
    cache_at_interrupt: dict[str, Any] = {}

    def _fake_interrupt(payload: Any) -> Any:
        # 记录 interrupt 时 state 的快照（此时缓存应已存在）
        existing = state.get("_clarification_cache")
        if existing:
            cache_at_interrupt.update(existing)
        return _RESUME_VALUE

    with (
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
            "._analyze_clarification",
            return_value=(_PARADIGM_LIST, "知识"),
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin.interrupt",
            side_effect=_fake_interrupt,
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin"
            "._format_clarification",
            return_value={"filters": [{"field": "total_revenue", "op": "gt", "value": 100}]},
        ),
    ):
        ctx = _make_ctx(TOOL, _params_with_unresolvable_term(), state, loader=_make_loader())
        await before_call_back(ctx)  # type: ignore[arg-type]

    # interrupt 前缓存应已写入
    assert cache_at_interrupt.get("cache_key") == _expected_cache_key(TOOL, QUERY), (
        "interrupt 调用前 state 中未发现预期缓存，说明缓存未被写入"
    )
    # format 后缓存应已清除
    assert state.get("_clarification_cache") is None, (
        f"format_clarification 完成后 _clarification_cache 应从 state 清除，"
        f"实际 state['_clarification_cache']={state.get('_clarification_cache')!r}"
    )
