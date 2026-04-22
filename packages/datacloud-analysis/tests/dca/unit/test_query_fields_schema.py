"""Schema and query-field injection contract checks."""

from __future__ import annotations

from ._field_schema_assertions import assert_required_uses_field, assert_uses_field_key


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


def test_T1_1_query_schema_has_query_and_complex_conditions() -> None:
    """T1-1: query schema remains strict and does not expose query/complex_conditions."""
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    schema = build_query_schema("企业分析", _make_fields())
    props = schema.get("properties", {})

    assert "query" not in props
    assert "complex_conditions" not in props
    assert "query" not in schema.get("required", [])

    for old_field in ("intent_reason", "extraction_confidence", "ambiguous_params"):
        assert old_field not in props


def test_T1_2_compute_schema_has_query_and_metric_extensions() -> None:
    """T1-2: compute schema keeps strict fields and metric-item extensions."""
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

    assert "query" not in props
    assert "complex_conditions" not in props
    assert "metrics" in schema.get("required", [])

    metrics_schema = props.get("metrics", {})
    one_of = metrics_schema.get("items", {}).get("oneOf", [])
    has_expr = any("expr" in item.get("properties", {}) for item in one_of)
    has_filters = any("filters" in item.get("properties", {}) for item in one_of)
    assert has_expr
    assert has_filters

    for item in one_of:
        if "expr" in item.get("properties", {}):
            assert_required_uses_field(item.get("required", []), context="compute expr item")


def test_T1_3_schema_constraints_relaxed() -> None:
    """T1-3: strict schema keeps enum constraints for field-code safety."""
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    schema = build_query_schema("企业分析", _make_fields())
    props = schema.get("properties", {})

    filters_schema = props.get("filters", {})
    items = filters_schema.get("items", {})
    one_of = items.get("oneOf", [])
    assert one_of
    first_field = one_of[0].get("properties", {}).get("field", {})
    assert "enum" in first_field or "const" in first_field
    assert_uses_field_key(one_of[0].get("properties", {}), context="query filter item")

    select_schema = props.get("select", {})
    select_items = select_schema.get("items", {})
    assert "enum" in select_items
    assert "x-dc-field-catalog" in select_schema

    order_by = props.get("order_by", {})
    ob_items = order_by.get("items", {})
    ob_field = ob_items.get("properties", {}).get("field", {})
    assert "enum" in ob_field
    assert_uses_field_key(ob_items.get("properties", {}), context="query order_by item")


def test_T1_4_inject_query_fields_replaces_inject_ambiguity_fields() -> None:
    """T1-4: inject_query_fields should inject and then strip query metadata fields."""
    import asyncio

    from datacloud_analysis.orchestration.execution.node import inject_query_fields
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel
    from pydantic import Field as PydanticField

    received: dict = {}

    async def _fake_coro(**kw: object) -> str:
        received.update(kw)
        return "ok"

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

    assert "query" in schema_fields
    assert "complex_conditions" in schema_fields
    for old in ("intent_reason", "extraction_confidence", "ambiguous_params"):
        assert old not in schema_fields

    asyncio.get_event_loop().run_until_complete(
        patched.coroutine(  # type: ignore[misc]
            select=["stat_date"],
            query="测试",
            complex_conditions=["产效含0%"],
        )
    )
    assert "query" not in received
    assert "complex_conditions" not in received
    assert "intent_reason" not in received
    assert "ambiguous_params" not in received
    assert received.get("select") == ["stat_date"]


def test_T1_5_query_tool_requires_select_and_query() -> None:
    """T1-5: query_* tools must require select and query."""
    from datacloud_analysis.orchestration.execution.node import _build_tools_list
    from datacloud_analysis.tools._agent_schema_patches import AGENT_QUERY_DESCRIPTION
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel
    from pydantic import Field as PydanticField

    class _QuerySchema(BaseModel):
        select: list[str] = PydanticField(default_factory=list, description="返回字段列表")

    async def _query_tool(**kwargs: object) -> str:
        _ = kwargs
        return "ok"

    query_tool = StructuredTool(
        name="query_demo",
        description="demo",
        args_schema=_QuerySchema,
        coroutine=_query_tool,
    )

    tools = _build_tools_list(default_tools={"query_demo": query_tool})
    patched = next(t for t in tools if t.name == "query_demo")
    schema = patched.args_schema.model_json_schema()  # type: ignore[union-attr]
    required = set(schema.get("required", []))
    props = schema.get("properties", {})

    assert "select" in required
    assert "query" in required
    assert props.get("query", {}).get("description") == AGENT_QUERY_DESCRIPTION


def test_T1_6_compute_tool_requires_query() -> None:
    """T1-6: compute_* tools must require query with AGENT_QUERY_DESCRIPTION."""
    from datacloud_analysis.orchestration.execution.node import _build_tools_list
    from datacloud_analysis.tools._agent_schema_patches import AGENT_QUERY_DESCRIPTION
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel
    from pydantic import Field as PydanticField

    class _ComputeSchema(BaseModel):
        metrics: list[str] = PydanticField(default_factory=list)

    async def _compute_tool(**kwargs: object) -> str:
        _ = kwargs
        return "ok"

    compute_tool = StructuredTool(
        name="compute_demo",
        description="demo",
        args_schema=_ComputeSchema,
        coroutine=_compute_tool,
    )

    tools = _build_tools_list(default_tools={"compute_demo": compute_tool})
    patched = next(t for t in tools if t.name == "compute_demo")
    schema = patched.args_schema.model_json_schema()  # type: ignore[union-attr]
    required = set(schema.get("required", []))
    props = schema.get("properties", {})

    assert "query" in required
    assert props.get("query", {}).get("description") == AGENT_QUERY_DESCRIPTION
