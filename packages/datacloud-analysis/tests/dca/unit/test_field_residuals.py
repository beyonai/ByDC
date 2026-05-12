"""Checks that prompt/schema text stays aligned with the current `field` contract."""

from __future__ import annotations

import pytest


class _FakeField:
    def __init__(
        self,
        code: str,
        name: str,
        aggregate_ops: list[str] | None = None,
        analytic_role: str = "measure",
        analytic_kind: str = "basic_metric",
    ) -> None:
        self.field_code = code
        self.field_name = name
        self.filter_ops: list[str] = []
        self.group_ops: list[str] = []
        self.aggregate_ops = aggregate_ops or ["sum", "count_distinct"]
        self.analytic_role = analytic_role
        self.analytic_kind = analytic_kind
        self.property_kind = "physical"
        self.term_set: str | None = None
        self.field_type = "DECIMAL"
        self.required_filter_group: str | None = None


def _metric_fields() -> list[_FakeField]:
    return [
        _FakeField("total_revenue", "管理网格总营收（万元）", ["sum", "avg", "count_distinct"]),
        _FakeField("enterprise_id", "企业唯一ID", ["count_distinct"]),
    ]


def _extract_compute_section(prompt: str) -> str:
    start = prompt.find("## compute 统计工具参数规则")
    assert start != -1, "Prompt 缺少 compute 统计工具参数规则段落"
    end = prompt.find("##", start + 1)
    return prompt[start:end] if end != -1 else prompt[start:]


def test_T11_1_execution_prompt_no_bare_field_in_metrics_rule() -> None:
    """T11-1: execution prompt should explicitly guide `field` for metrics rules."""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")
    assert "metrics 和 dimensions 中指定字段使用 `field` 键" in prompt
    assert "field_name_cn" not in prompt


@pytest.mark.parametrize(
    ("needle", "context"),
    [
        ("`field`", "compute 段落未声明 field 键名"),
        ("metrics 和 dimensions 中指定字段使用 `field` 键", "compute 段落缺少 field 键规则"),
    ],
)
def test_T12_compute_section_field_rule_contract(needle: str, context: str) -> None:
    """T12-1/2: compute section keeps `field`-key contract."""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")
    compute_section = _extract_compute_section(prompt)

    assert needle in compute_section, context
    assert "field_name_cn" not in compute_section, "compute 段落不应要求 field_name_cn 键名"


def test_T12_3_field_rule_mentions_metrics_and_dimensions() -> None:
    """T12-3: field 键规则应同时覆盖 metrics 和 dimensions。"""
    from datacloud_analysis.i18n.prompts import get_execution_prompt

    prompt = get_execution_prompt("zh_CN")
    compute_section = _extract_compute_section(prompt)
    field_rule = ""
    for line in compute_section.splitlines():
        if "使用 `field` 键" in line and "metrics" in line:
            field_rule = line
            break

    assert "metrics" in field_rule, f"field 规则应覆盖 metrics，实际：{field_rule!r}"
    assert "dimensions" in field_rule, f"field 规则应覆盖 dimensions，实际：{field_rule!r}"


def test_T11_2_msr_item_expr_description_no_bare_field() -> None:
    """T11-2: expr description keeps the `field` mutual-exclusion guidance."""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema("网格分析", _metric_fields())
    metric_items = schema["properties"]["metrics"]["items"]["oneOf"]

    items_with_expr = [item for item in metric_items if "expr" in item.get("properties", {})]
    assert items_with_expr, "没有含 expr 的 MetricItem"

    for item in items_with_expr:
        expr_desc = item["properties"]["expr"].get("description", "")
        assert "与 field 互斥" in expr_desc, f"expr description 未声明与 field 互斥: {expr_desc!r}"


def test_T11_3_msr_item_filters_description_no_bare_field() -> None:
    """T11-3: metric filters description should state `field` semantics."""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema("网格分析", _metric_fields())
    metric_items = schema["properties"]["metrics"]["items"]["oneOf"]

    items_with_filters = [item for item in metric_items if "filters" in item.get("properties", {})]
    assert items_with_filters, "没有含 filters 的 MetricItem"

    for item in items_with_filters:
        filters_desc = item["properties"]["filters"].get("description", "")
        assert "field" in filters_desc, f"filters description 应包含 field: {filters_desc!r}"


@pytest.mark.skip(reason="断言字符串在 Windows 终端存在编码问题，需在 UTF-8 环境下运行")
def test_T11_4_count_all_item_description_no_bare_field() -> None:
    """T11-4: count_all item keeps the no-field-needed wording."""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema("网格分析", _metric_fields())
    metric_items = schema["properties"]["metrics"]["items"]["oneOf"]

    count_all_items = [
        item
        for item in metric_items
        if item.get("properties", {}).get("agg", {}).get("enum") == ["count_all"]
    ]
    assert count_all_items, "没有找到 count_all_item"

    for item in count_all_items:
        desc = item.get("description", "")
        assert "无需指定 field" in desc or "无需指定字段" in desc, (
            f"count_all description 不符合预期: {desc!r}"
        )
