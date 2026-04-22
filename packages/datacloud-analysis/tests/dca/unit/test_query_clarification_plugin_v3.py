"""T3-1 ~ T8-2：before_callback 全路径验收（Step1/Step2/redirect/resume/模式废弃）。

对应 §3.4 query_clarification_plugin.py + §3.5 types/tool_wrapper + §3.6 react_loop + §3.7。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── 辅助：构造最简字段和 HookContext ─────────────────────────────────────────


def _make_ctx(
    tool_name: str,
    tool_params: dict[str, Any],
    loader: Any = None,
) -> dict[str, Any]:
    """构造最简 HookContext。"""
    return {
        "tool_name": tool_name,
        "tool_params": dict(tool_params),
        "user_query": tool_params.get("query", ""),
        "metadata": {"loader": loader} if loader else {},
        "session_id": "test",
        "knowledge_snippets": [],
        "term_context": [],
        "knowledge_payload": {},
    }


def _make_loader_with_fields(field_specs: list[tuple[str, str]]) -> Any:
    """构造带字段的假 OntologyLoader。"""
    loader = MagicMock()
    fields = []
    for code, name in field_specs:
        f = MagicMock()
        f.field_code = code
        f.field_name = name
        f.property_kind = "physical"
        fields.append(f)

    cls = MagicMock()
    cls.fields = fields
    loader.get_ontology_class.return_value = cls
    loader._scenes = {}
    return loader


# ── T3-1：complex_conditions 非空 → 触发 redirect ─────────────────────────────


@pytest.mark.asyncio
async def test_T3_1_complex_conditions_triggers_redirect() -> None:
    """T3-1：complex_conditions 非空 → before_call_back 返回 redirect 到 data_query_*。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    ctx = _make_ctx(
        "query_ads_enterprise_analysis",
        {
            "query": "统计各管理网格中亩产效益后30%物理网格的平均总营收",
            "filters": [{"field": "stat_date", "op": "eq", "value": "2026-03"}],
            "complex_conditions": ["亩产效益后30%物理网格"],
        },
    )

    decision = await before_call_back(ctx)  # type: ignore[arg-type]

    assert decision is not None, "complex_conditions 非空时应返回 HookDecision"
    assert decision.get("action") == "redirect", (
        f"期望 action=redirect，实际={decision.get('action')}"
    )
    assert decision.get("tool", "").startswith("data_query_"), (
        f"redirect 目标应为 data_query_*，实际={decision.get('tool')}"
    )


# ── T3-2：complex_conditions 为空 → 不触发 redirect（进入 Step 2）────────────


@pytest.mark.asyncio
async def test_T3_2_empty_complex_conditions_no_redirect() -> None:
    """T3-2：complex_conditions=[] 时不触发 redirect；返回 None 或 patch（CLEAR）。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    loader = _make_loader_with_fields(
        [
            ("stat_date", "统计日期"),
            ("enterprise_level_name", "企业等级"),
            ("total_revenue", "企业总营收（万元）"),
        ]
    )

    ctx = _make_ctx(
        "query_ads_enterprise_analysis",
        {
            "query": "查询龙头企业",
            "filters": [
                {"field": "stat_date", "op": "eq", "value": "2026-03"},
                {"field": "enterprise_level_name", "op": "eq", "value": "龙头企业"},
            ],
            "complex_conditions": [],
        },
        loader=loader,
    )

    decision = await before_call_back(ctx)  # type: ignore[arg-type]

    # 不应 redirect
    if decision is not None:
        assert decision.get("action") != "redirect", "complex_conditions=[] 时不应 redirect"


# ── T3-3：complex_conditions 字段缺失 → 视为空列表，正常处理 ─────────────────


@pytest.mark.asyncio
async def test_T3_3_missing_complex_conditions_treated_as_empty() -> None:
    """T3-3：调用时未传 complex_conditions → 默认空列表，不崩溃。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    ctx = _make_ctx(
        "query_ads_enterprise_analysis",
        {
            "query": "查询龙头企业",
            "filters": [{"field": "stat_date", "op": "eq", "value": "2026-03"}],
            # 无 complex_conditions
        },
    )

    # 不应抛出异常
    decision = await before_call_back(ctx)  # type: ignore[arg-type]
    if decision is not None:
        assert decision.get("action") != "redirect"


# ── T4 系列：_get_field_catalog 术语映射 ──────────────────────────────────────


def test_T4_1_field_chinese_name_maps_to_code() -> None:
    """T4-1：中文名 1:1 命中 catalog → 返回 field_code。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _get_field_catalog,
    )

    loader = _make_loader_with_fields(
        [
            ("total_revenue", "企业总营收（万元）"),
            ("stat_date", "统计日期"),
        ]
    )

    ctx = _make_ctx("query_ads_enterprise_analysis", {}, loader=loader)
    catalog = _get_field_catalog("query_ads_enterprise_analysis", ctx)  # type: ignore[arg-type]

    # field_code 自身应在目录中
    assert "total_revenue" in catalog, "field_code 本身应在 catalog 中"
    assert catalog["total_revenue"] == "total_revenue"

    # 中文名应在目录中
    assert "企业总营收（万元）" in catalog, "中文名应在 catalog 中"
    assert catalog["企业总营收（万元）"] == "total_revenue"


def test_T4_3_field_code_direct_passthrough() -> None:
    """T4-3：field_code 直接填写 → 原样通过，catalog 含 code→code 映射。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _get_field_catalog,
    )

    loader = _make_loader_with_fields(
        [
            ("energy_efficiency_Index", "企业经济效益等级（高、中、低）"),
        ]
    )

    ctx = _make_ctx("query_ads_enterprise_analysis", {}, loader=loader)
    catalog = _get_field_catalog("query_ads_enterprise_analysis", ctx)  # type: ignore[arg-type]

    assert "energy_efficiency_Index" in catalog
    assert catalog["energy_efficiency_Index"] == "energy_efficiency_Index"


def test_T4_4_loader_none_returns_empty_catalog() -> None:
    """T4-4：loader=None 时 _get_field_catalog 返回空 dict，不崩溃。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _get_field_catalog,
    )

    ctx = _make_ctx("query_ads_enterprise_analysis", {}, loader=None)
    catalog = _get_field_catalog("query_ads_enterprise_analysis", ctx)  # type: ignore[arg-type]
    assert isinstance(catalog, dict)
    assert len(catalog) == 0


def test_T4_5_short_alias_not_in_catalog() -> None:
    """T4-5：无短别名（'营收'不在 catalog），只有完整中文名和 field_code。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _get_field_catalog,
    )

    loader = _make_loader_with_fields(
        [
            ("total_revenue", "企业总营收（万元）"),
        ]
    )

    ctx = _make_ctx("query_ads_enterprise_analysis", {}, loader=loader)
    catalog = _get_field_catalog("query_ads_enterprise_analysis", ctx)  # type: ignore[arg-type]

    # "营收" 短词条不应出现
    assert "营收" not in catalog, "'营收' 是短词条，不应出现在 catalog 中（无别名机制）"


# ── T5 系列：歧义判断与 interrupt ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_T5_1_unknown_term_triggers_interrupt() -> None:
    """T5-1：unknown term should raise ClarificationNeededError in v0.3."""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        ClarificationNeededError,
        before_call_back,
    )

    loader = _make_loader_with_fields(
        [
            ("total_revenue", "企业总营收（万元）"),
            ("stat_date", "统计日期"),
        ]
    )

    ctx = _make_ctx(
        "query_ads_enterprise_analysis",
        {
            "query": "查询高营收的企业",
            "filters": [{"field_name_cn": "营收", "op": "gt", "value": "高"}],
            "complex_conditions": [],
        },
        loader=loader,
    )

    with (
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._resolve_via_aliases",
            return_value=None,
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._analyze_clarification",
            return_value=(
                [{"paradigmId": "P1", "paradigmResult": [{"keyword": "营收"}]}],
                "knowledge",
                True,
            ),
        ),
        pytest.raises(ClarificationNeededError) as exc_info,
    ):
        await before_call_back(ctx)  # type: ignore[arg-type]

    assert exc_info.value.context.get("tool_name") == "query_ads_enterprise_analysis"
    assert exc_info.value.context.get("is_complex") is False


@pytest.mark.asyncio
async def test_T5_2_after_resume_no_second_interrupt() -> None:
    """T5-2：恢复后 tool_params 已写为 field_code → 通道1 CLEAR，不再触发 interrupt。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    interrupt_count = 0

    def _fake_interrupt(payload: object) -> dict[str, Any]:
        nonlocal interrupt_count
        interrupt_count += 1
        return {"paradigmList": []}

    loader = _make_loader_with_fields(
        [
            ("total_revenue", "企业总营收（万元）"),
            ("stat_date", "统计日期"),
        ]
    )

    # 恢复后 tool_params 已是 field_code（用户选择已写回）
    ctx = _make_ctx(
        "query_ads_enterprise_analysis",
        {
            "query": "查询高营收的企业",
            "filters": [{"field": "total_revenue", "op": "gt", "value": 1000}],
            "complex_conditions": [],
        },
        loader=loader,
    )

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin.interrupt",
        side_effect=_fake_interrupt,
    ):
        await before_call_back(ctx)  # type: ignore[arg-type]

    assert interrupt_count == 0, f"恢复后不应再触发 interrupt，实际触发了 {interrupt_count} 次"


@pytest.mark.asyncio
async def test_T5_3_complex_need_confirm_restores_complex_conditions() -> None:
    """T5-3：COMPLEX + NEED_CONFIRM should raise ClarificationNeededError with complex context."""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        ClarificationNeededError,
        before_call_back,
    )

    loader = _make_loader_with_fields(
        [
            ("energy_efficiency_Index", "企业经济效益等级（高、中、低）"),
            ("stat_date", "统计日期"),
        ]
    )

    ctx = _make_ctx(
        "query_ads_enterprise_analysis",
        {
            "query": "找出亩产效益后30%网格上经济效益好的企业",
            "filters": [{"field": "经济效益", "op": "eq", "value": "好"}],
            "complex_conditions": ["亩产效益后30%的物理网格"],
        },
        loader=loader,
    )

    with (
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._resolve_via_aliases",
            return_value=None,
        ),
        patch(
            "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._analyze_clarification",
            return_value=([{"keyword": "经济效益"}], "知识", True),
        ),
        pytest.raises(ClarificationNeededError) as exc_info,
    ):
        await before_call_back(ctx)  # type: ignore[arg-type]

    context = exc_info.value.context
    assert context.get("is_complex") is True
    assert context.get("tool_name") == "query_ads_enterprise_analysis"
    structured_input = context.get("structured_input") or {}
    assert structured_input.get("complex_conditions") == ["亩产效益后30%的物理网格"]


# ── T6 系列：redirect HookDecision ───────────────────────────────────────────


def test_T6_1_redirect_decision_structure() -> None:
    """T6-1：redirect HookDecision 含 action/tool/params 三个字段。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _build_redirect_decision,
    )

    decision = _build_redirect_decision(
        tool_name="query_ads_enterprise_analysis",
        query="测试",
        tool_params={"filters": [{"field": "stat_date", "op": "eq", "value": "2026-03"}]},
    )

    assert decision.get("action") == "redirect"
    assert decision.get("tool") == "data_query_ads_enterprise_analysis"
    assert "params" in decision
    assert "contextKnowledge" in decision["params"] or "query" in decision["params"], (
        "redirect params 应含 query 或 contextKnowledge"
    )


def test_T6_2_redirect_action_in_hook_action_type() -> None:
    """T6-2：types.py HookAction 包含 'redirect' 字面量。"""
    # HookAction 是 Literal，检查其 __args__
    import typing

    from datacloud_analysis.tool_hook_plugins.types import HookAction

    args = typing.get_args(HookAction)
    assert "redirect" in args, f"HookAction 缺少 'redirect'，当前值: {args}"


def test_T6_3_hook_decision_has_tool_and_params_fields() -> None:
    """T6-3：HookDecision TypedDict 包含 tool 和 params 字段（支持 redirect）。"""
    from datacloud_analysis.tool_hook_plugins.types import HookDecision

    annotations = HookDecision.__annotations__
    assert "tool" in annotations, "HookDecision 缺少 tool 字段"
    assert "params" in annotations, "HookDecision 缺少 params 字段"


# ── T7：react_loop resume 写回 ────────────────────────────────────────────────


def test_T7_1_merge_resume_writes_field_code_back() -> None:
    """T7-1：resolved mapping should write field_code back to filters."""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    tool_params = {"filters": [{"field_name_cn": "营收", "op": "gt", "value": "高"}]}
    patched = _apply_resolved_to_params(tool_params, {"营收": "total_revenue"})

    updated_filters = patched.get("filters", [])
    f = updated_filters[0]
    assert f.get("field") == "total_revenue", (
        f"resolved 后 filters.field 应为 total_revenue，实际: {f}"
    )
    assert "field_name_cn" not in f, f"resolved 后 filters 不应保留 field_name_cn，实际: {f}"


# ── T8：模式开关废弃 ──────────────────────────────────────────────────────────


def test_T8_1_no_env_mode_dependency_in_tool_registration() -> None:
    """T8-1：init_agent_conf 或 node.py 不依赖 DATACLOUD_ONTOLOGY_LOAD_MODE 决定注册哪类工具。"""
    import os

    from datacloud_analysis.orchestration.execution.node import _is_data_tool_name

    # 无论环境变量如何，data tool 识别规则固定
    for env_val in ("ontology_query", "db_query", "", "unknown"):
        os.environ["DATACLOUD_ONTOLOGY_LOAD_MODE"] = env_val
        # query_* 和 compute_* 始终应被识别为数据工具
        assert _is_data_tool_name("query_ads_enterprise_analysis"), (
            f"env={env_val}: query_ads_enterprise_analysis 应被识别为数据工具"
        )
        assert _is_data_tool_name("compute_ads_grid_analysis"), (
            f"env={env_val}: compute_ads_grid_analysis 应被识别为数据工具"
        )
        assert _is_data_tool_name("data_query_ads_enterprise_analysis"), (
            f"env={env_val}: data_query_* 应被识别为数据工具"
        )
        assert not _is_data_tool_name("call_agent"), (
            f"env={env_val}: call_agent 不应被识别为数据工具"
        )

    os.environ.pop("DATACLOUD_ONTOLOGY_LOAD_MODE", None)


def test_T8_2_non_query_tool_skipped_by_before_callback() -> None:
    """T8-2（改为 T6-3 逻辑）：非 query_*/compute_* 工具 → before_callback 直接返回 None。"""

    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    ctx = _make_ctx("call_agent", {"query": "something"})
    decision = asyncio.get_event_loop().run_until_complete(
        before_call_back(ctx)  # type: ignore[arg-type]
    )
    assert decision is None, "非数据工具 before_callback 应返回 None"
