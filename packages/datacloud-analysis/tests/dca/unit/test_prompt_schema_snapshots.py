"""Snapshot guards for prompt/schema stability."""

from __future__ import annotations

import hashlib
import json

from datacloud_analysis.i18n.prompts import get_execution_prompt


class _FakeField:
    def __init__(
        self,
        code: str,
        name: str,
        *,
        filter_ops: list[str] | None = None,
        group_ops: list[str] | None = None,
        aggregate_ops: list[str] | None = None,
        analytic_role: str = "dimension",
        analytic_kind: str = "name",
        property_kind: str = "physical",
    ) -> None:
        self.field_code = code
        self.field_name = name
        self.filter_ops = filter_ops or ["eq", "in"]
        self.group_ops = group_ops or []
        self.aggregate_ops = aggregate_ops or []
        self.analytic_role = analytic_role
        self.analytic_kind = analytic_kind
        self.property_kind = property_kind
        self.term_set: str | None = None
        self.field_type = "STRING"
        self.required_filter_group: str | None = None


def _make_fields() -> list[_FakeField]:
    return [
        _FakeField("stat_date", "统计日期", filter_ops=["eq", "between"]),
        _FakeField(
            "total_revenue",
            "企业总营收（万元）",
            filter_ops=["eq", "gt", "lt"],
            aggregate_ops=["sum", "avg"],
            analytic_role="measure",
            analytic_kind="basic_metric",
        ),
        _FakeField(
            "enterprise_level_name",
            "企业等级",
            filter_ops=["eq", "in"],
            group_ops=["direct"],
        ),
    ]


def _schema_snapshot_payload() -> dict[str, object]:
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema, build_query_schema

    query_schema = build_query_schema("企业分析", _make_fields())
    compute_schema = build_compute_schema("企业分析", _make_fields())
    return {
        "query_required": query_schema.get("required", []),
        "query_properties": sorted((query_schema.get("properties") or {}).keys()),
        "query_examples": {
            "select": (query_schema.get("properties") or {}).get("select", {}).get("example"),
            "filters": (query_schema.get("properties") or {}).get("filters", {}).get("example"),
        },
        "compute_required": compute_schema.get("required", []),
        "compute_properties": sorted((compute_schema.get("properties") or {}).keys()),
        "compute_examples": {
            "dimensions": (compute_schema.get("properties") or {})
            .get("dimensions", {})
            .get("example"),
            "metrics": (compute_schema.get("properties") or {}).get("metrics", {}).get("example"),
        },
    }


def test_prompt_rule_snapshot_hash_stable() -> None:
    """Snapshot: key prompt contract fragments should remain stable."""
    prompt = get_execution_prompt("zh_CN")
    anchor_lines = []
    for line in prompt.splitlines():
        if any(
            token in line
            for token in (
                "metrics 和 dimensions 中指定字段使用 `field` 键",
                "⚠️ 字段名在字段列表中找不到时，不触发 complex_conditions",
                "工具选择引导",
                "query（必填）",
                "complex_conditions（溢出过滤区）",
            )
        ):
            anchor_lines.append(line.strip())
    payload = "\n".join(anchor_lines).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    assert digest == "f9634ed5eb715c146a737b03e7c9fabc562e376509d7b198691702279a2adf6e"


def test_schema_snapshot_hash_stable() -> None:
    """Snapshot: query/compute schema required/properties/examples should remain stable."""
    snapshot_payload = _schema_snapshot_payload()
    encoded = json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    assert digest == "8cca81e303399ed1c84e27189d6e991178de02ec4a7cc6932403356ce82dbe0f"
