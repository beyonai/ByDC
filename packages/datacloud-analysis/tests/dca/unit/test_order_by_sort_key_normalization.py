"""T18-1 ~ T18-4：order_by.sort 键兼容 → direction 规范化。

Bug 描述：
    LLM 在 order_by 中使用 sort 键（{"sort": "asc"}）而非 Schema 定义的 direction，
    底层 SQL builder 不识别 sort，使用默认 DESC，导致"最低的前3个"实际返回最高的。

修复要求：
    在 _apply_resolved_to_params 中对 order_by 每项做规范化：
    - 若存在 sort 键且不存在 direction 键 → 将 sort 值写入 direction，删除 sort
    - 若已有 direction 键 → 不覆盖，直接保留
    - 不含 sort 的项 → 不变
"""

from __future__ import annotations

from typing import Any

# ── T18-1：sort: "asc" → direction: "asc"，sort 键被移除 ─────────────────────


def test_T18_1_sort_asc_mapped_to_direction() -> None:
    """T18-1：order_by 中 sort='asc' 应被规范化为 direction='asc'，sort 键移除。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "order_by": [{"field": "total_revenue", "sort": "asc"}],
    }

    new_params = _apply_resolved_to_params(params, {})
    ob = new_params["order_by"][0]

    assert ob.get("direction") == "asc", f"sort='asc' 应规范化为 direction='asc'，实际: {ob}"
    assert "sort" not in ob, f"规范化后不应保留 sort 键: {ob}"
    assert ob.get("field") == "total_revenue", f"field 不应改变: {ob}"


# ── T18-2：sort: "desc" → direction: "desc" ───────────────────────────────────


def test_T18_2_sort_desc_mapped_to_direction() -> None:
    """T18-2：order_by 中 sort='desc' 应被规范化为 direction='desc'。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "order_by": [{"field": "manage_grid_name", "sort": "desc"}],
    }

    new_params = _apply_resolved_to_params(params, {})
    ob = new_params["order_by"][0]

    assert ob.get("direction") == "desc", f"sort='desc' 应规范化为 direction='desc'，实际: {ob}"
    assert "sort" not in ob, f"规范化后不应保留 sort 键: {ob}"


# ── T18-3：direction 已存在时不被 sort 覆盖 ───────────────────────────────────


def test_T18_3_direction_not_overridden_when_present() -> None:
    """T18-3：若已有 direction 键，不应被 sort 覆盖。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "order_by": [{"field": "total_revenue", "direction": "desc", "sort": "asc"}],
    }

    new_params = _apply_resolved_to_params(params, {})
    ob = new_params["order_by"][0]

    assert ob.get("direction") == "desc", f"direction 已存在时不应被 sort 覆盖，实际: {ob}"
    assert "sort" not in ob, f"规范化后不应保留 sort 键: {ob}"


# ── T18-4：不含 sort 的项保持不变 ────────────────────────────────────────────


def test_T18_4_items_without_sort_unchanged() -> None:
    """T18-4：不含 sort 键的 order_by 项应保持原样。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "order_by": [
            {"field": "total_revenue", "direction": "asc"},  # 正常写法，不变
            {"field": "manage_grid_name"},  # 无排序方向，不变
        ],
    }

    new_params = _apply_resolved_to_params(params, {})

    ob0 = new_params["order_by"][0]
    assert ob0.get("direction") == "asc" and "sort" not in ob0, f"正常项不应改变: {ob0}"

    ob1 = new_params["order_by"][1]
    assert "sort" not in ob1 and "direction" not in ob1, f"无排序方向项不应改变: {ob1}"


# ── T18-5：op: "asc" → direction: "asc"（实际日志中出现的键名）─────────────────


def test_T18_5_op_asc_mapped_to_direction() -> None:
    """T18-5：order_by 中 op='asc' 应被规范化为 direction='asc'，op 键被移除。

    来源：真实日志中 LLM 使用 {"op": "asc", "field": "output_per_mu"}，
    _normalize_sort_key 原版本只处理 sort，不处理 op，导致排序方向丢失。
    """
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict = {
        "order_by": [{"field": "output_per_mu", "op": "asc"}],
    }

    new_params = _apply_resolved_to_params(params, {})
    ob = new_params["order_by"][0]

    assert ob.get("direction") == "asc", f"op='asc' 应规范化为 direction='asc'，实际: {ob}"
    assert "op" not in ob, f"规范化后不应保留 op 键: {ob}"
    assert ob.get("field") == "output_per_mu", f"field 不应改变: {ob}"


# ── T18-6：op: "desc" → direction: "desc" ────────────────────────────────────


def test_T18_6_op_desc_mapped_to_direction() -> None:
    """T18-6：order_by 中 op='desc' 应被规范化为 direction='desc'。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict = {
        "order_by": [{"field": "total_revenue", "op": "desc"}],
    }

    new_params = _apply_resolved_to_params(params, {})
    ob = new_params["order_by"][0]

    assert ob.get("direction") == "desc", f"op='desc' 应规范化为 direction='desc'，实际: {ob}"
    assert "op" not in ob, f"规范化后不应保留 op 键: {ob}"

