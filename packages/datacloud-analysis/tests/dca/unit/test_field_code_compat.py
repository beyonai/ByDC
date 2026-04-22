"""T16-1 ~ T16-9：field 键同时兼容字段编码和中文名。

Bug 描述：
    LLM 传 field: "total_revenue"（字段编码）时，
    _collect_terms_from_params 将其收入 terms，
    catalog 无此 key（catalog key 均为中文名）→ 进入 unresolved → 触发歧义打断。

修复要求：
    1. 新增 _is_field_code(term) 辅助：纯 ASCII identifier → True，含中文 → False
    2. _collect_terms_from_params：跳过字段编码，只收集需要 catalog 查询的中文名
    3. _apply_resolved_to_params 的 _translate_field：
       - 字段编码 → 直接写回 field（透传）
       - 中文名 → catalog 映射后写回 field
       - 同时兼容 field_name_cn 和 field 两个键名
    4. select 数组：字段编码直通，中文名走 _map 映射
    5. order_by / having 同样兼容字段编码透传
"""

from __future__ import annotations

from typing import Any

# ── T16-1 / T16-2：_is_field_code 基础逻辑 ────────────────────────────────────


def test_T16_1_is_field_code_true_for_ascii_identifier() -> None:
    """T16-1：纯 ASCII snake_case → 字段编码 → True。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _is_field_code,
    )

    for code in ["total_revenue", "manage_grid_name", "stat_date", "energy_efficiency_Index"]:
        assert _is_field_code(code) is True, f"'{code}' 应被识别为字段编码"


def test_T16_2_is_field_code_false_for_chinese_name() -> None:
    """T16-2：包含中文或特殊字符 → 字段中文名 → False。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _is_field_code,
    )

    for name in [
        "管理网格总营收（万元）",
        "管理网格名称",
        "企业等级",
        "总营收",
        "亩产效益（万元/亩）",
    ]:
        assert _is_field_code(name) is False, f"'{name}' 不应被识别为字段编码"


# ── T16-3 / T16-4：_collect_terms_from_params 跳过字段编码 ────────────────────


def test_T16_3_collect_terms_skips_field_code_in_filter() -> None:
    """T16-3：filters.field = 字段编码 时不收入 terms（避免 catalog 找不到触发打断）。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _collect_terms_from_params,
    )

    params: dict[str, Any] = {
        "filters": [{"field": "total_revenue", "op": "gt", "value": 100}],
    }
    terms, _ = _collect_terms_from_params(params)

    assert "total_revenue" not in terms, (
        f"字段编码 'total_revenue' 不应被收入 terms（它不需要 catalog 查询），实际: {terms}"
    )


def test_T16_4_collect_terms_includes_chinese_name_in_filter() -> None:
    """T16-4：filters.field = 中文名 时正常收入 terms（需要 catalog 查询）。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _collect_terms_from_params,
    )

    params: dict[str, Any] = {
        "filters": [{"field": "管理网格总营收（万元）", "op": "gt", "value": 100}],
    }
    terms, _ = _collect_terms_from_params(params)

    assert "管理网格总营收（万元）" in terms, (
        f"中文名 '管理网格总营收（万元）' 应被收入 terms，实际: {terms}"
    )


# ── T16-5 / T16-6：_apply_resolved_to_params 字段编码透传 + 中文名映射 ──────────


def test_T16_5_apply_resolved_passthrough_field_code_in_filter() -> None:
    """T16-5：field = 字段编码时，_apply_resolved_to_params 直接透传，不查 resolved。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "filters": [{"field": "total_revenue", "op": "gt", "value": 100}],
    }
    # resolved 为空（catalog 未命中），字段编码应直接透传
    new_params = _apply_resolved_to_params(params, {})

    f = new_params["filters"][0]
    assert f.get("field") == "total_revenue", f"字段编码应透传，实际: {f}"


def test_T16_6_apply_resolved_maps_chinese_field_in_filter() -> None:
    """T16-6：field = 中文名时，_apply_resolved_to_params 通过 resolved 映射为字段编码。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "filters": [{"field": "管理网格总营收（万元）", "op": "gt", "value": 100}],
    }
    resolved = {"管理网格总营收（万元）": "total_revenue"}

    new_params = _apply_resolved_to_params(params, resolved)

    f = new_params["filters"][0]
    assert f.get("field") == "total_revenue", f"中文名应映射为 total_revenue，实际: {f}"
    assert "field_name_cn" not in f, f"翻译后不应保留 field_name_cn: {f}"


# ── T16-7 / T16-8：select 数组字段编码直通 + 中文名映射 ──────────────────────


def test_T16_7_select_field_code_passes_through() -> None:
    """T16-7：select 中的字段编码直接透传，不经过 _map（避免 unresolved 打断）。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "select": ["manage_grid_name", "total_revenue"],
    }
    # resolved 为空，字段编码应直通
    new_params = _apply_resolved_to_params(params, {})

    assert new_params["select"] == ["manage_grid_name", "total_revenue"], (
        f"字段编码应直通，实际: {new_params['select']}"
    )


def test_T16_8_select_chinese_name_mapped() -> None:
    """T16-8：select 中的中文名通过 resolved 映射为字段编码。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "select": ["管理网格名称", "管理网格总营收（万元）"],
    }
    resolved = {
        "管理网格名称": "manage_grid_name",
        "管理网格总营收（万元）": "total_revenue",
    }
    new_params = _apply_resolved_to_params(params, resolved)

    assert new_params["select"] == ["manage_grid_name", "total_revenue"], (
        f"中文名应映射为字段编码，实际: {new_params['select']}"
    )


# ── T16-9：order_by 字段编码直通 ────────────────────────────────────────────


def test_T16_9_order_by_field_code_passes_through() -> None:
    """T16-9：order_by.field = 字段编码时直接透传，不触发 catalog 查询或打断。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
        _collect_terms_from_params,
    )

    params: dict[str, Any] = {
        "order_by": [{"field": "total_revenue", "op": "asc"}],
    }

    # 1. 不收入 terms
    terms, _ = _collect_terms_from_params(params)
    assert "total_revenue" not in terms, f"order_by 字段编码不应收入 terms，实际: {terms}"

    # 2. 直接透传
    new_params = _apply_resolved_to_params(params, {})
    ob = new_params["order_by"][0]
    assert ob.get("field") == "total_revenue", f"order_by 字段编码应透传，实际: {ob}"
