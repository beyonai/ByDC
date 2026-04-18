"""T1-1 ~ T1-4：query / complex_conditions 新字段 + inject_query_fields 验收。

对应 §3.1 generator.py 变更 + §3.2 node.py inject_query_fields。
"""

from __future__ import annotations

import pytest


# ── 辅助：构造最简字段对象 ────────────────────────────────────────────────────

class _FakeField:
    def __init__(
        self,
        code: str,
        name: str,
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


# ── T1-1：build_query_schema 包含 query(required) + complex_conditions ────────

def test_T1_1_query_schema_has_query_and_complex_conditions() -> None:
    """T1-1：query_{code} Schema 包含 query 必填字段和 complex_conditions。"""
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    schema = build_query_schema("企业分析", _make_fields())

    props = schema.get("properties", {})
    assert "query" in props, "Schema 缺少 query 字段"
    assert "complex_conditions" in props, "Schema 缺少 complex_conditions 字段"

    # query 必填
    required = schema.get("required", [])
    assert "query" in required, "query 未加入 required"

    # complex_conditions 默认空列表
    cc = props["complex_conditions"]
    assert cc.get("type") == "array", "complex_conditions 应为 array"
    assert cc.get("default") == [], "complex_conditions 默认值应为 []"

    # 旧元字段不应出现
    for old_field in ("intent_reason", "extraction_confidence", "ambiguous_params"):
        assert old_field not in props, f"旧元字段 {old_field!r} 不应出现在 Schema 中"


# ── T1-2：build_compute_schema 包含 query(required) + MetricItem 扩展 ─────────

def test_T1_2_compute_schema_has_query_and_metric_extensions() -> None:
    """T1-2：compute_{code} Schema 包含 query 必填、MetricItem 包含 expr/filters。"""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    fields = [
        _FakeField(
            "total_revenue",
            "总营收",
            filter_ops=["gt", "lt"],
            group_ops=[],
            aggregate_ops=["sum", "avg"],
            analytic_role="measure",
            analytic_kind="basic_metric",
        ),
        _FakeField(
            "manage_grid_name",
            "管理网格",
            filter_ops=["eq"],
            group_ops=["direct"],
        ),
    ]

    schema = build_compute_schema("网格分析", fields)
    props = schema.get("properties", {})

    assert "query" in props, "compute Schema 缺少 query 字段"
    assert "query" in schema.get("required", []), "query 未加入 compute required"
    assert "complex_conditions" in props, "compute Schema 缺少 complex_conditions"

    # MetricItem 中 expr 和 filters 字段存在
    metrics_schema = props.get("metrics", {})
    items = metrics_schema.get("items", {})
    one_of = items.get("oneOf", [])
    # 至少有一个 metric item 含 expr
    has_expr = any("expr" in item.get("properties", {}) for item in one_of)
    has_filters = any("filters" in item.get("properties", {}) for item in one_of)
    assert has_expr, "MetricItem 缺少 expr 字段"
    assert has_filters, "MetricItem 缺少 filters 字段"

    # MetricItem required 不包含 field（field/expr 二选一）
    for item in one_of:
        if "expr" in item.get("properties", {}):
            assert "field" not in item.get("required", []), (
                "含 expr 的 MetricItem required 不应包含 field"
            )


# ── T1-3：Schema 字段约束放开，允许填中文 ─────────────────────────────────────

def test_T1_3_schema_constraints_relaxed() -> None:
    """T1-3：filters.field_name_cn 无 const；select 无 enum；x-dc-field-catalog 保留。"""
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    schema = build_query_schema("企业分析", _make_fields())
    props = schema.get("properties", {})

    # filters：field_name_cn 不含 const（已改名，旧 field 不再存在）
    filters_schema = props.get("filters", {})
    items = filters_schema.get("items", {})
    for fitem in items.get("oneOf", []):
        fn_cn_prop = fitem.get("properties", {}).get("field_name_cn", {})
        assert "const" not in fn_cn_prop, (
            f"filters.field_name_cn 仍含 const 约束: {fn_cn_prop}"
        )

    # select：无 enum 约束
    select_schema = props.get("select", {})
    select_items = select_schema.get("items", {})
    assert "enum" not in select_items, "select.items 仍含 enum 约束，应放开"

    # x-dc-field-catalog 保留
    assert "x-dc-field-catalog" in select_schema, (
        "select 缺少 x-dc-field-catalog 字段目录"
    )

    # order_by.field_name_cn 无 enum（已改名）
    order_by = props.get("order_by", {})
    ob_items = order_by.get("items", {})
    ob_fn_cn = ob_items.get("properties", {}).get("field_name_cn", {})
    assert "enum" not in ob_fn_cn, "order_by.field_name_cn 仍含 enum 约束，应放开"


# ── T1-4：inject_query_fields 替代 inject_ambiguity_fields ────────────────────

def test_T1_4_inject_query_fields_replaces_inject_ambiguity_fields() -> None:
    """T1-4：inject_query_fields 注入 query/complex_conditions；底层不收到这两个字段。"""
    from datacloud_analysis.orchestration.execution.node import inject_query_fields

    received: dict = {}

    async def _fake_coro(**kw: object) -> str:
        received.update(kw)
        return "ok"

    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field as PydanticField

    class _BaseSchema(BaseModel):
        select: list[str] = PydanticField(default_factory=list)

    tool = StructuredTool(
        name="query_test",
        description="test",
        args_schema=_BaseSchema,
        coroutine=_fake_coro,
    )

    patched = inject_query_fields(tool)
    schema_fields = patched.args_schema.model_fields  # type: ignore[union-attr]

    # 注入了 query 和 complex_conditions
    assert "query" in schema_fields, "inject_query_fields 未注入 query"
    assert "complex_conditions" in schema_fields, "inject_query_fields 未注入 complex_conditions"

    # 旧元字段不应出现
    for old in ("intent_reason", "extraction_confidence", "ambiguous_params"):
        assert old not in schema_fields, f"旧元字段 {old!r} 不应被注入"

    # 调用底层时，query/complex_conditions 被剥除
    import asyncio

    asyncio.get_event_loop().run_until_complete(
        patched.coroutine(  # type: ignore[misc]
            select=["stat_date"],
            query="测试",
            complex_conditions=["亩产效益后30%"],
        )
    )
    assert "query" not in received, "query 未被剥除，底层不应收到"
    assert "complex_conditions" not in received, "complex_conditions 未被剥除，底层不应收到"
    # 旧字段同样不应出现
    assert "intent_reason" not in received
    assert "ambiguous_params" not in received
    # 业务字段正常传递
    assert received.get("select") == ["stat_date"]
