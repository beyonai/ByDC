"""Checks compute metric-item required fields under current schema contract."""

from __future__ import annotations

from ._field_schema_assertions import assert_required_uses_field


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


def test_T15_1_metric_item_properties_include_field_not_field_name_cn() -> None:
    """T15-1: metric item exposes `field` (not field_name_cn)."""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema(
        "测试",
        [_FakeField("total_revenue", "总营收", ["sum", "avg", "count_distinct"])],
    )
    metric_item = schema["properties"]["metrics"]["items"]

    props = metric_item.get("properties", {})
    assert "field" in props
    assert "field_name_cn" not in props
    assert_required_uses_field(["field"], context="普通指标项")


def test_T15_2_count_all_item_required_does_not_include_field_name_cn() -> None:
    """T15-2: flattened metric item should not require field, so count_all remains valid."""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema(
        "测试",
        [_FakeField("total_revenue", "总营收", ["sum", "count_distinct"])],
    )
    metric_item = schema["properties"]["metrics"]["items"]

    required = metric_item.get("required", [])
    assert "field_name_cn" not in required
    assert "field" not in required
    assert "count_all" in metric_item.get("properties", {}).get("agg", {}).get("enum", [])
