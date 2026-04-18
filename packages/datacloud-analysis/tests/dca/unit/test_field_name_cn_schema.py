"""T9-1 ~ T9-8：field → field_name_cn 改名 + plugin 翻译逻辑验收。

覆盖：
  T9-1  query_* filters.field_name_cn 存在，旧 field 不存在
  T9-2  compute_* dimensions.field_name_cn 存在，旧 field 不存在
  T9-3  compute_* metrics.field_name_cn 存在，旧 field 不存在
  T9-4  query_* / compute_* order_by.field_name_cn 存在，旧 field 不存在
  T9-5  field_name_cn description 含"中文名"字样
  T9-6  dimensions / metrics arrays 带 examples（防 JSON string 混淆）
  T9-7  _collect_terms_from_params 读 field_name_cn
  T9-8  _apply_resolved_to_params 翻译 field_name_cn → field(field_code)
"""

from __future__ import annotations

from typing import Any

# ── 辅助 ──────────────────────────────────────────────────────────────────────


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


def _query_fields() -> list[_FakeField]:
    return [
        _FakeField("stat_date", "统计日期", filter_ops=["eq", "between"]),
        _FakeField("total_revenue", "企业总营收（万元）", filter_ops=["gt", "lt"]),
        _FakeField("enterprise_level_name", "企业等级", filter_ops=["eq", "in"]),
    ]


def _compute_fields() -> list[_FakeField]:
    return [
        _FakeField(
            "enterprise_level_name",
            "企业等级",
            filter_ops=["eq", "in"],
            group_ops=["direct"],
        ),
        _FakeField(
            "total_revenue",
            "企业总营收（万元）",
            filter_ops=["gt", "lt"],
            aggregate_ops=["sum", "avg", "count_distinct"],
            analytic_role="measure",
            analytic_kind="basic_metric",
        ),
        _FakeField(
            "enterprise_id",
            "企业唯一ID",
            filter_ops=[],
            aggregate_ops=["count_distinct"],
            analytic_role="measure",
            analytic_kind="basic_metric",
        ),
    ]


# ── T9-1：query_* filters 使用 field_name_cn ─────────────────────────────────


def test_T9_1_query_filter_item_uses_field_name_cn() -> None:
    """T9-1：build_query_schema 的 filters.items.oneOf[*].properties 含 field_name_cn，不含旧 field。"""
    from datacloud_data_sdk.virtual_action.generator import build_query_schema

    schema = build_query_schema("企业分析", _query_fields())
    filter_items = schema["properties"]["filters"]["items"]["oneOf"]

    for item in filter_items:
        props = item.get("properties", {})
        assert "field_name_cn" in props, f"filters item 缺少 field_name_cn: {list(props.keys())}"
        assert "field" not in props, f"filters item 仍含旧 field 键: {list(props.keys())}"
        required = item.get("required", [])
        assert "field_name_cn" in required, "filters item required 应含 field_name_cn"
        assert "field" not in required, "filters item required 不应含旧 field"


# ── T9-2：compute_* dimensions 使用 field_name_cn ────────────────────────────


def test_T9_2_compute_dim_item_uses_field_name_cn() -> None:
    """T9-2：build_compute_schema 的 dimensions.items.oneOf[*].properties 含 field_name_cn，不含旧 field。"""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema("企业分析", _compute_fields())
    dim_schema = schema["properties"].get("dimensions", {})
    items_schema = dim_schema.get("items", {})
    one_of = items_schema.get("oneOf", [])

    assert one_of, "dimensions.items.oneOf 为空"
    for item in one_of:
        props = item.get("properties", {})
        assert "field_name_cn" in props, f"dimensions item 缺少 field_name_cn: {list(props.keys())}"
        assert "field" not in props, f"dimensions item 仍含旧 field 键: {list(props.keys())}"


# ── T9-3：compute_* metrics 使用 field_name_cn ───────────────────────────────


def test_T9_3_compute_metric_item_uses_field_name_cn() -> None:
    """T9-3：build_compute_schema 的 metrics.items.oneOf 普通指标项含 field_name_cn，不含旧 field。"""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema("企业分析", _compute_fields())
    metric_items = schema["properties"]["metrics"]["items"]["oneOf"]

    # 排除 count_all_item（它不需要 field_name_cn，通过 agg.const 识别）
    regular_items = [
        item
        for item in metric_items
        if item.get("properties", {}).get("agg", {}).get("const") != "count_all"
    ]
    assert regular_items, "没有普通指标项（非 count_all）"

    for item in regular_items:
        props = item.get("properties", {})
        assert "field_name_cn" in props, f"metrics item 缺少 field_name_cn: {list(props.keys())}"
        assert "field" not in props, f"metrics item 仍含旧 field 键: {list(props.keys())}"


# ── T9-4：query_* / compute_* order_by 使用 field_name_cn ───────────────────


def test_T9_4_order_by_uses_field_name_cn() -> None:
    """T9-4：query_* / compute_* 的 order_by.items.properties 含 field_name_cn，不含旧 field。"""
    from datacloud_data_sdk.virtual_action.generator import (
        build_compute_schema,
        build_query_schema,
    )

    for schema in [
        build_query_schema("企业分析", _query_fields()),
        build_compute_schema("企业分析", _compute_fields()),
    ]:
        ob_schema = schema["properties"].get("order_by", {})
        ob_item = ob_schema.get("items", {})
        ob_props = ob_item.get("properties", {})
        assert "field_name_cn" in ob_props, (
            f"order_by item 缺少 field_name_cn: {list(ob_props.keys())}"
        )
        assert "field" not in ob_props, f"order_by item 仍含旧 field: {list(ob_props.keys())}"


# ── T9-5：field_name_cn description 含"中文名"字样 ───────────────────────────


def test_T9_5_field_name_cn_description_mentions_chinese_name() -> None:
    """T9-5：field_name_cn 的 description 须提示"中文名"，引导 LLM 填中文。"""
    from datacloud_data_sdk.virtual_action.generator import (
        build_compute_schema,
        build_query_schema,
    )

    # query filters
    q_schema = build_query_schema("企业分析", _query_fields())
    q_filter_item = q_schema["properties"]["filters"]["items"]["oneOf"][0]
    q_fn_cn_desc = q_filter_item["properties"]["field_name_cn"].get("description", "")
    assert "中文名" in q_fn_cn_desc, (
        f"query filters.field_name_cn description 缺少'中文名': {q_fn_cn_desc!r}"
    )

    # compute dimensions
    c_schema = build_compute_schema("企业分析", _compute_fields())
    c_dim_item = c_schema["properties"]["dimensions"]["items"]["oneOf"][0]
    c_dim_desc = c_dim_item["properties"]["field_name_cn"].get("description", "")
    assert "中文名" in c_dim_desc, (
        f"compute dimensions.field_name_cn description 缺少'中文名': {c_dim_desc!r}"
    )


# ── T9-6：dimensions / metrics arrays 带 examples ────────────────────────────


def test_T9_6_arrays_have_examples_to_prevent_json_string_confusion() -> None:
    """T9-6：dimensions / metrics 数组 Schema 带 examples，防止 LLM 把数组序列化成 JSON string。"""
    from datacloud_data_sdk.virtual_action.generator import build_compute_schema

    schema = build_compute_schema("企业分析", _compute_fields())
    dims = schema["properties"]["dimensions"]
    mets = schema["properties"]["metrics"]

    assert "examples" in dims, "dimensions 缺少 examples"
    assert "examples" in mets, "metrics 缺少 examples"

    # examples 的第一个元素必须是 list（展示正确的数组结构）
    assert isinstance(dims["examples"][0], list), (
        f"dimensions examples[0] 应为 list，实际为 {type(dims['examples'][0])}"
    )
    assert isinstance(mets["examples"][0], list), (
        f"metrics examples[0] 应为 list，实际为 {type(mets['examples'][0])}"
    )
    # examples 中的 item 必须含 field_name_cn（不是 JSON string）
    dim_example_item = dims["examples"][0][0]
    assert isinstance(dim_example_item, dict), "dimensions examples[0][0] 应为 dict"
    assert "field_name_cn" in dim_example_item, "dimensions examples[0][0] 应含 field_name_cn"


# ── T9-7：_collect_terms_from_params 读 field_name_cn ────────────────────────


def test_T9_7_collect_terms_reads_field_name_cn() -> None:
    """T9-7：_collect_terms_from_params 优先读 field_name_cn，收集到 terms 列表。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _collect_terms_from_params,
    )

    params: dict[str, Any] = {
        "filters": [{"field_name_cn": "营收", "op": "gt", "value": 100}],
        "dimensions": [{"field_name_cn": "企业等级", "group_op": "direct"}],
        "metrics": [{"field_name_cn": "企业唯一ID", "agg": "count_distinct", "as": "企业数量"}],
    }

    terms = _collect_terms_from_params(params)

    assert "营收" in terms, f"未从 field_name_cn 收集到 '营收'，实际: {terms}"
    assert "企业等级" in terms, f"未从 field_name_cn 收集到 '企业等级'，实际: {terms}"
    assert "企业唯一ID" in terms, f"未从 field_name_cn 收集到 '企业唯一ID'，实际: {terms}"


def test_T9_7b_collect_terms_fallback_to_field() -> None:
    """T9-7b：无 field_name_cn 时 fallback 读 field（中文名）——向后兼容。

    注意：field 值为字段编码（ASCII）时不收入 terms（T16-3 验证），
    field 值为中文名时应正常收入 terms（本测试验证）。
    """
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _collect_terms_from_params,
    )

    params: dict[str, Any] = {
        "filters": [{"field": "管理网格总营收（万元）", "op": "gt", "value": 100}],
    }

    terms = _collect_terms_from_params(params)
    assert "管理网格总营收（万元）" in terms, f"fallback 未读到 field 中的中文名: {terms}"


# ── T9-8：_apply_resolved_to_params 翻译 field_name_cn → field ───────────────


def test_T9_8_apply_resolved_translates_field_name_cn_to_field() -> None:
    """T9-8：_apply_resolved_to_params 将 field_name_cn 解析为 field_code 后，写为 field，移除 field_name_cn。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "filters": [{"field_name_cn": "营收", "op": "gt", "value": 100}],
        "dimensions": [{"field_name_cn": "企业等级", "group_op": "direct"}],
        "metrics": [{"field_name_cn": "企业数量", "agg": "count_distinct", "as": "数量"}],
    }
    resolved = {
        "营收": "total_revenue",
        "企业等级": "enterprise_level_name",
        "企业数量": "enterprise_id",
    }

    new_params = _apply_resolved_to_params(params, resolved)

    # filters
    f = new_params["filters"][0]
    assert f.get("field") == "total_revenue", f"filters.field 应为 total_revenue，实际: {f}"
    assert "field_name_cn" not in f, f"filters 翻译后不应保留 field_name_cn: {f}"

    # dimensions
    d = new_params["dimensions"][0]
    assert d.get("field") == "enterprise_level_name", (
        f"dimensions.field 应为 enterprise_level_name，实际: {d}"
    )
    assert "field_name_cn" not in d, f"dimensions 翻译后不应保留 field_name_cn: {d}"

    # metrics
    m = new_params["metrics"][0]
    assert m.get("field") == "enterprise_id", f"metrics.field 应为 enterprise_id，实际: {m}"
    assert "field_name_cn" not in m, f"metrics 翻译后不应保留 field_name_cn: {m}"


def test_T9_8b_apply_resolved_keeps_field_when_no_field_name_cn() -> None:
    """T9-8b：无 field_name_cn 时，旧 field 按原逻辑解析（向后兼容）。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "filters": [{"field": "营收_old", "op": "gt", "value": 100}],
    }
    resolved = {"营收_old": "total_revenue"}

    new_params = _apply_resolved_to_params(params, resolved)
    assert new_params["filters"][0].get("field") == "total_revenue"
