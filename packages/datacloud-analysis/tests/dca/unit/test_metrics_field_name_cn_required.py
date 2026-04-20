"""T15-1 ~ T15-2：metrics oneOf 普通指标项 field_name_cn 必须在 required 中。

Bug 描述：
    compute_* metrics 的 oneOf 普通指标项（非 count_all），
    field_name_cn 未在 required 列表中，
    LLM 视为可选字段，回退到训练先验键名 field。

修复要求：
    _msr_item 的 required 列表加入 field_name_cn：
    required: ["field_name_cn", "agg", "as"]
    （count_all_item 不含 field_name_cn，不受影响）
"""

from __future__ import annotations


class _FakeField:
    def __init__(
        self,
        code: str,
        name: str,
        aggregate_ops: list[str] | None = None,
    ) -> None:
        self.field_code = code
        self.field_name = name
        self.analytic_role = "measure"
        self.analytic_kind = "basic_metric"
        self.filter_ops: list[str] = ["gt", "lt"]
        self.group_ops: list[str] = []
        self.aggregate_ops = aggregate_ops or ["sum", "count_distinct"]
        self.property_kind = "physical"
        self.term_set: str | None = None
        self.field_type = "DECIMAL"
        self.required_filter_group: str | None = None


# ── T15-1：普通指标项 required 含 field_name_cn ───────────────────────────────


def test_T15_1_regular_metric_item_required_includes_field_name_cn() -> None:
    """T15-1：compute_* metrics 普通指标 oneOf 项的 required 列表必须包含 field_name_cn。

    field_name_cn 不在 required 时，LLM 视为可选并回退到训练先验 field 键名。
    """
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema(
        "测试",
        [_FakeField("total_revenue", "总营收", ["sum", "avg", "count_distinct"])],
    )
    metric_items = schema["properties"]["metrics"]["items"]["oneOf"]

    # 排除 count_all_item（它无需 field_name_cn）
    regular_items = [
        item
        for item in metric_items
        if item.get("properties", {}).get("agg", {}).get("enum") != ["count_all"]
    ]
    assert regular_items, "没有普通指标项（非 count_all）"

    for item in regular_items:
        required = item.get("required", [])
        assert "field_name_cn" in required, (
            f"普通指标项 required 未包含 field_name_cn，LLM 会回退到 field 键名\n"
            f"当前 required: {required}\n"
            f"当前 properties: {list(item.get('properties', {}).keys())}"
        )


# ── T15-2：count_all_item required 不强制 field_name_cn ───────────────────────


def test_T15_2_count_all_item_required_does_not_include_field_name_cn() -> None:
    """T15-2：count_all_item 不需要 field_name_cn，required 中不应包含它（避免 LLM 必填报错）。"""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema(
        "测试",
        [_FakeField("total_revenue", "总营收", ["sum", "count_distinct"])],
    )
    metric_items = schema["properties"]["metrics"]["items"]["oneOf"]

    count_all_items = [
        item
        for item in metric_items
        if item.get("properties", {}).get("agg", {}).get("enum") == ["count_all"]
    ]
    assert count_all_items, "没有 count_all_item"

    for item in count_all_items:
        required = item.get("required", [])
        assert "field_name_cn" not in required, (
            f"count_all_item required 不应包含 field_name_cn: {required}"
        )
