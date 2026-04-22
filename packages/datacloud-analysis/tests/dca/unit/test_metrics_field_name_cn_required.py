"""Checks compute metric-item required fields under current schema contract."""

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


def test_T15_1_regular_metric_item_required_includes_field_name_cn() -> None:
    """T15-1: regular metric items require `field` (not field_name_cn)."""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema(
        "测试",
        [_FakeField("total_revenue", "总营收", ["sum", "avg", "count_distinct"])],
    )
    metric_items = schema["properties"]["metrics"]["items"]["oneOf"]

    regular_items = [
        item
        for item in metric_items
        if item.get("properties", {}).get("agg", {}).get("enum") != ["count_all"]
    ]
    assert regular_items, "没有普通指标项（非 count_all）"

    for item in regular_items:
        required = item.get("required", [])
        assert "field" in required, (
            f"普通指标项 required 未包含 field\n"
            f"当前 required: {required}\n"
            f"当前 properties: {list(item.get('properties', {}).keys())}"
        )
        assert "field_name_cn" not in required


def test_T15_2_count_all_item_required_does_not_include_field_name_cn() -> None:
    """T15-2: count_all item should not require any field key."""
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
        assert "field_name_cn" not in required
        assert "field" not in required
