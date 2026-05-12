"""T10-1 ~ T10-4：field_name_cn 无条件翻译 Bug 回归测试。

Bug 描述：
    before_call_back 中 `_apply_resolved_to_params` 被包在 `if catalog and terms:` 内。
    当 loader=None（catalog={}）时，即使 tool_params 含 field_name_cn，
    该块被跳过 → field_name_cn 原样透传到 SQL builder → `WHERE  IN (...)` SQL 语法错误。

修复要求：
    无论 catalog 是否为空，只要 tool_params 含 field_name_cn，
    before_call_back 必须将其翻译为 field 键（catalog 为空时原样透传值，
    至少保证 SQL 不报语法错误）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _make_ctx(tool_name: str, tool_params: dict[str, Any], loader: Any = None) -> dict[str, Any]:
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


# ── T10-1：loader=None，filters 含 field_name_cn → 必须翻译为 field ─────────


@pytest.mark.skip(reason="需要数据库连接（DATACLOUD_DB_SCHEMA），属于集成测试")
@pytest.mark.asyncio
async def test_T10_1_loader_none_filter_field_name_cn_translated() -> None:
    """T10-1（Bug 复现）：loader=None 时 filters.field_name_cn 必须被翻译为 field，不得留空。

    这是对真实报错场景的直接复现：
      入参 filters=[{"field_name_cn": "管理网格名称", "op": "in", "value": [...]}]
      期望出参 filters=[{"field": "管理网格名称", "op": "in", "value": [...]}]
      当前 Bug: catalog={} → if catalog and terms 短路 → 跳过翻译 → field 键缺失
               → SQL: WHERE  IN (...) → 语法错误
    """
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    ctx = _make_ctx(
        "query_ads_manage_grid_analysis",
        {
            "query": "查询3个管理网格的车流、人流明细数据",
            "filters": [
                {
                    "field_name_cn": "管理网格名称",
                    "op": "in",
                    "value": ["荣华街道", "亦庄地区", "瀛海地区"],
                }
            ],
            "complex_conditions": [],
        },
        loader=None,  # ← 关键：无 loader，catalog={}
    )

    await before_call_back(ctx)  # type: ignore[arg-type]

    f = ctx["tool_params"]["filters"][0]

    # field 键必须存在（不能是缺失状态，否则 SQL builder 生成 WHERE  IN (...) 语法错误）
    assert "field" in f, (
        f"loader=None 时 field_name_cn 未翻译为 field，filters[0]={f}\n"
        "Bug: `if catalog and terms:` 短路跳过了 _apply_resolved_to_params"
    )
    # field_name_cn 必须被移除（已翻译，不应残留）
    assert "field_name_cn" not in f, f"翻译后 field_name_cn 未被移除，filters[0]={f}"
    # catalog 为空时，field 值等于原始 field_name_cn（原样透传，至少结构正确）
    assert f["field"] == "管理网格名称", (
        f"catalog 为空时 field 值应等于原始中文名（原样透传），实际={f['field']!r}"
    )


# ── T10-2：loader=None，dimensions + metrics 含 field_name_cn → 全部翻译 ─────


@pytest.mark.skip(reason="需要数据库连接（DATACLOUD_DB_SCHEMA），属于集成测试")
@pytest.mark.asyncio
async def test_T10_2_loader_none_dim_and_metric_field_name_cn_translated() -> None:
    """T10-2：loader=None 时 dimensions 和 metrics 的 field_name_cn 也必须翻译为 field。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    ctx = _make_ctx(
        "compute_ads_enterprise_analysis",
        {
            "query": "统计各等级企业数量",
            "dimensions": [{"field_name_cn": "企业等级", "group_op": "direct"}],
            "metrics": [{"field_name_cn": "企业唯一ID", "agg": "count_distinct", "as": "企业数量"}],
            "complex_conditions": [],
        },
        loader=None,
    )

    await before_call_back(ctx)  # type: ignore[arg-type]

    tp = ctx["tool_params"]

    # dimensions
    d = tp["dimensions"][0]
    assert "field" in d, f"dimensions[0] 缺少 field 键: {d}"
    assert "field_name_cn" not in d, f"dimensions[0] field_name_cn 未移除: {d}"
    assert d["field"] == "企业等级"

    # metrics
    m = tp["metrics"][0]
    assert "field" in m, f"metrics[0] 缺少 field 键: {m}"
    assert "field_name_cn" not in m, f"metrics[0] field_name_cn 未移除: {m}"
    assert m["field"] == "企业唯一ID"


# ── T10-3：catalog 有值但 field_name_cn 不在 catalog → 原样透传（不崩溃）──


@pytest.mark.asyncio
async def test_T10_3_catalog_populated_unknown_term_passthrough() -> None:
    """T10-3：catalog 有其他字段，但 field_name_cn 值不在 catalog 中 → NEED_CONFIRM 路径。

    NEED_CONFIRM 路径由 interrupt 处理，测试仅验证当 interrupt 返回空结果时
    翻译仍然发生（field_name_cn → field 原样透传），不产生 SQL 语法错误。
    """
    from unittest.mock import MagicMock

    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    loader = MagicMock()
    f = MagicMock()
    f.field_code = "enterprise_level_name"
    f.field_name = "企业等级"
    f.property_kind = "physical"
    cls = MagicMock()
    cls.fields = [f]
    loader.get_ontology_class.return_value = cls
    loader._scenes = {}

    ctx = _make_ctx(
        "query_ads_enterprise_analysis",
        {
            "query": "查询管理网格",
            "filters": [
                {
                    "field_name_cn": "未知字段XYZ",  # 不在 catalog
                    "op": "eq",
                    "value": "测试",
                }
            ],
            "complex_conditions": [],
        },
        loader=loader,
    )

    with patch(
        "datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin._analyze_clarification",
        return_value=([], "知识", False),
    ):
        await before_call_back(ctx)  # type: ignore[arg-type]

    # 无论如何，filters[0] 必须有 field 键（不能缺失导致 SQL 语法错误）
    result_f = ctx["tool_params"]["filters"][0]
    assert "field" in result_f, f"interrupt 返回空 paradigmList 后仍缺少 field 键: {result_f}"


# ── T10-4：无 field_name_cn 的场景不受影响（回归保护）────────────────────────


@pytest.mark.asyncio
async def test_T10_4_no_field_name_cn_no_regression() -> None:
    """T10-4：params 中无 field_name_cn 时，before_call_back 正常放行，不引入 field 键。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        before_call_back,
    )

    ctx = _make_ctx(
        "query_ads_enterprise_analysis",
        {
            "query": "查询全部企业",
            "filters": [],
            "complex_conditions": [],
        },
        loader=None,
    )

    decision = await before_call_back(ctx)  # type: ignore[arg-type]

    # filters 为空，不应引入任何 field 键
    assert ctx["tool_params"]["filters"] == [], (
        f"空 filters 不应被修改: {ctx['tool_params']['filters']}"
    )
    # 非 complex → 返回 None（CLEAR 放行）
    assert decision is None or decision.get("action") != "redirect", "无复杂条件时不应 redirect"
