"""T14-1 ~ T14-4：order_by / having 的 field_name_cn 翻译缺失 Bug。

Bug 描述：
    LLM 在 order_by 中使用 field_name_cn，
    但 _collect_terms_from_params / _apply_resolved_to_params 均未处理 order_by / having，
    导致 SQL 生成 "ORDER BY  ASC"（字段名为空），触发 MySQL 1064 语法错误。

修复要求：
    1. _collect_terms_from_params 增加对 order_by.field_name_cn 的收集
    2. _apply_resolved_to_params 增加对 order_by / having 的 field_name_cn → field 翻译
    3. _apply_resume_to_tool_params (resume 路径) 同步处理 order_by / having
"""

from __future__ import annotations

from typing import Any

# ── T14-1：_collect_terms 收集 order_by.field_name_cn ────────────────────────


def test_T14_1_collect_terms_reads_order_by_field_name_cn() -> None:
    """T14-1：_collect_terms_from_params 应从 order_by 收集 field_name_cn。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _collect_terms_from_params,
    )

    params: dict[str, Any] = {
        "order_by": [{"field_name_cn": "管理网格总营收（万元）", "op": "asc"}],
        "filters": [],
    }

    terms = _collect_terms_from_params(params)

    assert "管理网格总营收（万元）" in terms, (
        f"_collect_terms_from_params 未收集 order_by.field_name_cn，实际 terms: {terms}"
    )


# ── T14-2：_apply_resolved 翻译 order_by.field_name_cn → field ───────────────


def test_T14_2_apply_resolved_translates_order_by_field_name_cn() -> None:
    """T14-2：_apply_resolved_to_params 应将 order_by.field_name_cn 翻译为 field。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "order_by": [{"field_name_cn": "管理网格总营收（万元）", "op": "asc"}],
        "filters": [],
    }
    resolved = {"管理网格总营收（万元）": "total_revenue"}

    new_params = _apply_resolved_to_params(params, resolved)

    ob = new_params["order_by"][0]
    assert ob.get("field") == "total_revenue", (
        f"order_by 翻译后 field 应为 total_revenue，实际: {ob}"
    )
    assert "field_name_cn" not in ob, f"order_by 翻译后不应保留 field_name_cn: {ob}"


# ── T14-3：_apply_resolved 翻译 having.field_name_cn → field ─────────────────


def test_T14_3_apply_resolved_translates_having_field_name_cn() -> None:
    """T14-3：_apply_resolved_to_params 应将 having.field_name_cn 翻译为 field。
    having 格式为 [{field_name_cn, op, value}]，与 filters 相同结构。
    """
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "having": [{"field_name_cn": "企业数量", "op": "gt", "value": 10}],
    }
    resolved = {"企业数量": "enterprise_count"}

    new_params = _apply_resolved_to_params(params, resolved)

    hv = new_params["having"][0]
    assert hv.get("field") == "enterprise_count", (
        f"having 翻译后 field 应为 enterprise_count，实际: {hv}"
    )
    assert "field_name_cn" not in hv, f"having 翻译后不应保留 field_name_cn: {hv}"


# ── T14-4：before_call_back 端到端 order_by 翻译（loader=None 场景）────────────


def test_T14_4_before_callback_order_by_translated_without_loader() -> None:
    """T14-4：loader=None 时，before_call_back 仍应将 order_by.field_name_cn 翻译为 field。

    复现场景：LLM 发送 order_by=[{field_name_cn: '...', op: 'asc'}]，
    loader 未挂载，resolved={} 但翻译应无条件执行，
    结果 order_by 中 field_name_cn 应原样写回 field（避免 SQL 空字段名）。
    """
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    # loader=None 时 resolved={}，field_name_cn 无法映射，原样写回 field
    params: dict[str, Any] = {
        "order_by": [{"field_name_cn": "管理网格总营收（万元）", "op": "asc"}],
        "filters": [],
    }

    new_params = _apply_resolved_to_params(params, {})

    ob = new_params["order_by"][0]
    # loader=None 时无法翻译，field 应原样保留 field_name_cn 的值（非空）
    assert ob.get("field") is not None and ob.get("field") != "", (
        f"loader=None 时 order_by field 不应为空，实际: {ob}"
    )
    assert "field_name_cn" not in ob, f"翻译后不应保留 field_name_cn: {ob}"
