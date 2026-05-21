"""Tests for virtual_action.generator — inputSchema / description 生成器。

覆盖协议变更（§3.2.2 / §3.2.3 改动点）：
  build_query_schema / build_compute_schema 中所有 field 参数均改为 field_code，
  不再使用 field_name 中文名。

验收项：
  Schema 层面：
    Q1  query select.items.enum 全部为 field_code，不含中文名
    Q2  query filters.items 中每个 field 的 enum 单值为 field_code
    Q3  query order_by.items.field.enum 全部为 field_code
    Q4  query schema description 不含"中文名"字样
    Q5  query select description 不含"中文名"字样
    C1  compute dimensions[i].field.enum 单值为 field_code
    C2  compute metrics[i].field.enum 单值为 field_code
    C3  compute filters 中 field.enum 单值为 field_code
    C4  compute schema description 不含"中文名"字样
    C5  compute dimensions description 不含"中文名"字样
    C6  compute metrics description 不含"中文名"字样

  Description 层面（Markdown 文本）：
    D1  query description 不含"字段统一使用中文名"
    D2  query description 常见错误不含"field 填了字段编码而非中文名"（旧提示）
    D3  compute description 不含"字段统一使用中文名"
    D4  compute description 常见错误不含"field 填了字段编码而非中文名"（旧提示）

  x-dc 扩展字段（field catalog）：
    X1  query select x-dc-field-catalog 中的 code 为 field_code
    X2  compute x-dc-dimension-fields 中的 field 为 field_code（主键）
    X3  compute x-dc-measure-fields 中的 field 为 field_code（主键）
"""

from __future__ import annotations

from typing import Any

import pytest
from datacloud_data_sdk.virtual_action.generator import (
    build_compute_description,
    build_compute_schema,
    build_kb_write_schema,
    build_query_description,
    build_query_schema,
)

# ─────────────────────────────────────────────────────────────────────────────
# 测试用字段 stub（模拟 OntologyField）
# ─────────────────────────────────────────────────────────────────────────────


class _F:
    """轻量 OntologyField stub。"""

    def __init__(
        self,
        field_code: str,
        field_name: str,
        analytic_role: str = "dimension",
        analytic_kind: str = "name",
        filter_ops: list[str] | None = None,
        group_ops: list[str] | None = None,
        aggregate_ops: list[str] | None = None,
        property_kind: str = "physical",
        required_filter_group: str | None = None,
        secondary_role: str | None = None,
    ) -> None:
        self.field_code = field_code
        self.field_name = field_name
        self.field_type = "STRING"
        self.analytic_role = analytic_role
        self.analytic_kind = analytic_kind
        self.filter_ops = filter_ops or []
        self.group_ops = group_ops or []
        self.aggregate_ops = aggregate_ops or []
        self.property_kind = property_kind
        self.required_filter_group = required_filter_group
        self.secondary_role = secondary_role
        self.is_primary_key = False


# 三个典型字段
_REGION = _F(
    "region_name",
    "区域名称",
    analytic_role="dimension",
    analytic_kind="name",
    filter_ops=["eq", "in"],
    group_ops=["self"],
)
_PERIOD = _F(
    "period",
    "账期",
    analytic_role="dimension",
    analytic_kind="period",
    filter_ops=["eq", "between"],
    group_ops=["month", "year"],
    required_filter_group="period_required",
)
_REVENUE = _F(
    "revenue",
    "企业收入",
    analytic_role="measure",
    analytic_kind="basic_metric",
    filter_ops=["eq", "gt", "gte", "lt", "lte"],
    aggregate_ops=["sum", "avg", "min", "max"],
)

FIELDS = [_REGION, _PERIOD, _REVENUE]
KB_FIELDS = [
    _F("doc_id", "文档主键", property_kind="physical"),
    _F("status", "状态", property_kind="physical"),
]
KB_FIELDS[0].is_primary_key = True


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _collect_filter_field_codes(schema: dict[str, Any]) -> list[str]:
    """从 filters schema 中收集所有 field 单值 enum。"""
    codes: list[str] = []
    items = schema.get("properties", {}).get("filters", {}).get("items", {})
    for one_of_item in items.get("oneOf", []):
        field_prop = one_of_item.get("properties", {}).get("field", {})
        enum_vals = field_prop.get("enum")
        if isinstance(enum_vals, list) and len(enum_vals) == 1:
            codes.append(enum_vals[0])
    return codes


def _collect_dim_field_codes(schema: dict[str, Any]) -> list[str]:
    """从 dimensions schema 中收集所有 field 单值 enum。"""
    codes: list[str] = []
    items = schema.get("properties", {}).get("dimensions", {}).get("items", {})
    for one_of_item in items.get("oneOf", []):
        field_prop = one_of_item.get("properties", {}).get("field", {})
        enum_vals = field_prop.get("enum")
        if isinstance(enum_vals, list) and len(enum_vals) == 1:
            codes.append(enum_vals[0])
    return codes


def _collect_metric_field_codes(schema: dict[str, Any]) -> list[str]:
    """从 metrics schema 中收集所有 field 单值 enum（排除 count_all）。"""
    codes: list[str] = []
    items = schema.get("properties", {}).get("metrics", {}).get("items", {})
    for one_of_item in items.get("oneOf", []):
        field_prop = one_of_item.get("properties", {}).get("field", {})
        enum_vals = field_prop.get("enum")
        if isinstance(enum_vals, list) and len(enum_vals) == 1:
            codes.append(enum_vals[0])
    return codes


# ─────────────────────────────────────────────────────────────────────────────
# Q 系列：build_query_schema
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def query_schema() -> dict[str, Any]:
    return build_query_schema("企业基础信息", FIELDS, required_filter_groups=["period_required"])


def test_q1_select_enum_uses_field_code(query_schema: dict[str, Any]) -> None:
    """Q1: select.items.enum 全部是 field_code，不含中文名。"""
    select_prop = query_schema["properties"]["select"]
    enum_vals: list[str] = select_prop["items"]["enum"]
    # 必须包含三个 field_code
    assert "region_name" in enum_vals, f"select enum 缺少 region_name，实际：{enum_vals}"
    assert "period" in enum_vals, f"select enum 缺少 period，实际：{enum_vals}"
    assert "revenue" in enum_vals, f"select enum 缺少 revenue，实际：{enum_vals}"
    # 不能含中文名
    assert "区域名称" not in enum_vals, f"select enum 不应含中文名，实际：{enum_vals}"
    assert "账期" not in enum_vals, f"select enum 不应含中文名，实际：{enum_vals}"
    assert "企业收入" not in enum_vals, f"select enum 不应含中文名，实际：{enum_vals}"


def test_q2_filter_field_enum_uses_field_code(query_schema: dict[str, Any]) -> None:
    """Q2: filters 中每个 oneOf 项的 field.enum 单值为 field_code。"""
    codes = _collect_filter_field_codes(query_schema)
    assert len(codes) > 0, "filters oneOf 为空，没有找到任何 field enum"
    for c in codes:
        assert not any(ch > "\x7f" for ch in c), (
            f"filter field.enum '{c}' 含非 ASCII 字符（中文名），应为 field_code"
        )
    assert "region_name" in codes, f"缺少 region_name，实际 codes={codes}"
    assert "period" in codes, f"缺少 period，实际 codes={codes}"
    assert "revenue" in codes, f"缺少 revenue，实际 codes={codes}"


def test_q3_order_by_field_enum_uses_field_code(query_schema: dict[str, Any]) -> None:
    """Q3: order_by.items.properties.field.enum 全部为 field_code。"""
    order_items = query_schema["properties"]["order_by"]["items"]
    field_enum: list[str] = order_items["properties"]["field"]["enum"]
    assert "region_name" in field_enum, f"order_by field enum 缺少 region_name，实际：{field_enum}"
    for v in field_enum:
        assert not any(ch > "\x7f" for ch in v), (
            f"order_by field enum 项 '{v}' 含中文，应为 field_code"
        )


def test_q4_schema_description_no_chinese_name(query_schema: dict[str, Any]) -> None:
    """Q4: schema 顶层 description 不含"中文名"字样。"""
    desc = query_schema.get("description", "")
    assert "中文名" not in desc, f"schema description 含'中文名'：{desc}"


def test_q5_select_description_no_chinese_name(query_schema: dict[str, Any]) -> None:
    """Q5: select description 不含"中文名"字样。"""
    select_desc = query_schema["properties"]["select"].get("description", "")
    assert "中文名" not in select_desc, f"select description 含'中文名'：{select_desc}"


def test_x1_select_catalog_code_is_field_code(query_schema: dict[str, Any]) -> None:
    """X1: select x-dc-field-catalog 中 code 值为 field_code。"""
    catalog = query_schema["properties"]["select"].get("x-dc-field-catalog", [])
    assert len(catalog) > 0, "x-dc-field-catalog 为空"
    codes = [item["code"] for item in catalog]
    assert "region_name" in codes, f"catalog code 缺少 region_name，实际：{codes}"
    for item in catalog:
        assert item["code"] == item["code"].replace(" ", "_") or True  # 只需验证是 field_code
        # name 才是中文名，code 应是 ASCII
        assert not any(ch > "\x7f" for ch in item["code"]), (
            f"catalog code '{item['code']}' 含中文，应为 field_code"
        )


# ─────────────────────────────────────────────────────────────────────────────
# C 系列：build_compute_schema
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def compute_schema() -> dict[str, Any]:
    return build_compute_schema("企业基础信息", FIELDS, required_filter_groups=["period_required"])


def test_c1_dimension_field_enum_uses_field_code(compute_schema: dict[str, Any]) -> None:
    """C1: dimensions 中每个 oneOf 项的 field.enum 单值为 field_code。"""
    codes = _collect_dim_field_codes(compute_schema)
    assert len(codes) > 0, "dimensions oneOf 为空"
    for c in codes:
        assert not any(ch > "\x7f" for ch in c), (
            f"dimensions field.enum '{c}' 含中文，应为 field_code"
        )
    assert "region_name" in codes, f"缺少 region_name，实际：{codes}"
    assert "period" in codes, f"缺少 period，实际：{codes}"


def test_c2_metric_field_enum_uses_field_code(compute_schema: dict[str, Any]) -> None:
    """C2: metrics 中每个 oneOf 项的 field.enum 单值为 field_code。"""
    codes = _collect_metric_field_codes(compute_schema)
    assert len(codes) > 0, "metrics oneOf（非 count_all）为空"
    for c in codes:
        assert not any(ch > "\x7f" for ch in c), f"metrics field.enum '{c}' 含中文，应为 field_code"
    assert "revenue" in codes, f"缺少 revenue，实际：{codes}"


def test_c3_compute_filter_enum_uses_field_code(compute_schema: dict[str, Any]) -> None:
    """C3: compute filters 中 field.enum 单值为 field_code。"""
    codes = _collect_filter_field_codes(compute_schema)
    assert len(codes) > 0, "compute filters oneOf 为空"
    for c in codes:
        assert not any(ch > "\x7f" for ch in c), (
            f"compute filter field.enum '{c}' 含中文，应为 field_code"
        )


def test_c4_compute_schema_description_no_chinese_name(compute_schema: dict[str, Any]) -> None:
    """C4: compute schema 顶层 description 不含"中文名"。"""
    desc = compute_schema.get("description", "")
    assert "中文名" not in desc, f"compute schema description 含'中文名'：{desc}"


def test_c5_dimensions_description_no_chinese_name(compute_schema: dict[str, Any]) -> None:
    """C5: dimensions description 不含"中文名"。"""
    dim_desc = compute_schema["properties"]["dimensions"].get("description", "")
    assert "中文名" not in dim_desc, f"dimensions description 含'中文名'：{dim_desc}"


def test_c6_metrics_description_no_chinese_name(compute_schema: dict[str, Any]) -> None:
    """C6: metrics description 不含"中文名"。"""
    mtr_desc = compute_schema["properties"]["metrics"].get("description", "")
    assert "中文名" not in mtr_desc, f"metrics description 含'中文名'：{mtr_desc}"


def test_x2_dimension_catalog_field_is_field_code(compute_schema: dict[str, Any]) -> None:
    """X2: x-dc-dimension-fields 中的主键 field 为 field_code。"""
    catalog = compute_schema["properties"]["dimensions"].get("x-dc-dimension-fields", [])
    assert len(catalog) > 0, "x-dc-dimension-fields 为空"
    for item in catalog:
        assert not any(ch > "\x7f" for ch in item["field"]), (
            f"x-dc-dimension-fields field '{item['field']}' 含中文，应为 field_code"
        )


def test_x3_measure_catalog_field_is_field_code(compute_schema: dict[str, Any]) -> None:
    """X3: x-dc-measure-fields 中的主键 field 为 field_code。"""
    catalog = compute_schema["properties"]["metrics"].get("x-dc-measure-fields", [])
    assert len(catalog) > 0, "x-dc-measure-fields 为空"
    for item in catalog:
        assert not any(ch > "\x7f" for ch in item["field"]), (
            f"x-dc-measure-fields field '{item['field']}' 含中文，应为 field_code"
        )


def test_kb_write_schema_excludes_primary_key_field() -> None:
    """KB write schema 的 labels 不应暴露主键字段。"""
    schema = build_kb_write_schema("知识库对象", KB_FIELDS)
    labels_props = schema["properties"]["labels"]["properties"]
    assert "status" in labels_props
    assert "doc_id" not in labels_props


# ─────────────────────────────────────────────────────────────────────────────
# D 系列：description 文本
# ─────────────────────────────────────────────────────────────────────────────


def test_d1_query_description_no_chinese_name_phrase() -> None:
    desc = build_query_description(
        "企业基础信息", "企业信息对象", FIELDS, required_filter_groups=["period_required"]
    )
    assert "字段统一使用中文名" not in desc, "query description 仍含旧提示[字段统一使用中文名]"


def test_d2_query_description_no_wrong_error_hint() -> None:
    desc = build_query_description(
        "企业基础信息", "企业信息对象", FIELDS, required_filter_groups=["period_required"]
    )
    assert "field 填了字段编码而非中文名" not in desc, "query description 常见错误仍含旧提示"


def test_d3_compute_description_no_chinese_name_phrase() -> None:
    desc = build_compute_description(
        "企业基础信息", "企业信息对象", FIELDS, required_filter_groups=["period_required"]
    )
    assert "字段统一使用中文名" not in desc, "compute description 仍含旧提示[字段统一使用中文名]"


def test_d4_compute_description_no_wrong_error_hint() -> None:
    desc = build_compute_description(
        "企业基础信息", "企业信息对象", FIELDS, required_filter_groups=["period_required"]
    )
    assert "field 填了字段编码而非中文名" not in desc, "compute description 常见错误仍含旧提示"


# ─────────────────────────────────────────────────────────────────────────────
# G 系列：贪心阶段优化（§5.1）验收
# 对应验收用例：TC-01 ~ TC-11
# ─────────────────────────────────────────────────────────────────────────────


# ── G1-G3: filters 触发条件 2 修复（§5.1.1）──────────────────────────────────


def test_g1_query_complex_conditions_no_unknown_field_trigger(
    query_schema: dict[str, Any],
) -> None:
    """G1: query filters.description 不含旧的字段命中提示。"""
    desc = query_schema["properties"]["filters"]["description"]
    assert "字段名在当前对象字段列表中找不到精确对应" not in desc
    assert "非标准词），需系统做语义推断" not in desc


def test_g2_query_complex_conditions_explains_field_not_in_list(
    query_schema: dict[str, Any],
) -> None:
    """G2: query filters.description 明确要求使用属性编码。"""
    desc = query_schema["properties"]["filters"]["description"]
    assert "属性编码" in desc, f"filters.description 未明确要求属性编码: {desc!r}"


def test_g3_compute_complex_conditions_no_unknown_field_trigger(
    compute_schema: dict[str, Any],
) -> None:
    """G3: compute filters.description 同样不含旧的字段命中提示。"""
    desc = compute_schema["properties"]["filters"]["description"]
    assert "字段名在当前对象字段列表中找不到精确对应" not in desc
    assert "非标准词），需系统做语义推断" not in desc


# ── G4-G6: 严格属性编码约束（§5.1.3）────────────────────────────────────────


def test_g4_filters_oneOf_has_no_catchall_item(query_schema: dict[str, Any]) -> None:
    """G4: query filters.items.oneOf 不再包含原词透传 catch-all 条目。"""
    items = query_schema["properties"]["filters"]["items"]
    one_of = items.get("oneOf", [])
    assert len(one_of) > 0, "filters oneOf 为空"
    for item in one_of:
        field_prop = item.get("properties", {}).get("field", {})
        enum_vals = field_prop.get("enum", [])
        assert isinstance(enum_vals, list) and len(enum_vals) == 1, (
            f"filters oneOf 中存在非固定属性编码条目，应全部使用单值 enum 约束: {field_prop}"
        )
        assert "原词" not in field_prop.get("description", ""), (
            f"filters.field.description 不应再提示原词透传: {field_prop}"
        )


def test_g5_filter_array_description_mentions_field_code_only(query_schema: dict[str, Any]) -> None:
    """G5: query filters.description 只允许属性编码，不再提示中文名/原词。"""
    desc = query_schema["properties"]["filters"].get("description", "")
    assert "属性编码" in desc, f"filters.description 未明确属性编码要求: {desc!r}"
    assert "中文名" not in desc, f"filters.description 不应再允许中文名: {desc!r}"
    assert "原词" not in desc and "原始词" not in desc, (
        f"filters.description 不应再提示原词透传: {desc!r}"
    )


def test_g6_filter_item_field_desc_contains_fixed_field_code_instruction(
    query_schema: dict[str, Any],
) -> None:
    """G6: 已知字段 filter 条目的 field.description 明确固定为属性编码。"""
    items = query_schema["properties"]["filters"]["items"]
    one_of = items.get("oneOf", [])
    assert len(one_of) > 0, "没有已知字段的 filter 条目"
    found = any(
        "固定为" in item.get("properties", {}).get("field", {}).get("description", "")
        and "属性编码" in item.get("properties", {}).get("field", {}).get("description", "")
        for item in one_of
    )
    assert found, "所有已知字段 filter 条目的 field.description 均未明确固定属性编码"


# ── G7-G9: 常见错误描述修正（§5.1.6）────────────────────────────────────────


def test_g7_query_description_no_map_error_hint() -> None:
    """G7: query 常见错误不含误导性"系统无法映射时会报错"描述。"""
    desc = build_query_description("企业基础信息", "企业信息对象", FIELDS)
    assert "系统无法映射时会报错" not in desc


def test_g8_query_description_has_no_guess_replace_warning() -> None:
    """G8: query 常见错误含正确的"猜测替换"警告（正向验收）。"""
    desc = build_query_description("企业基础信息", "企业信息对象", FIELDS)
    assert "猜测替换" in desc


def test_g9_compute_description_no_map_error_hint() -> None:
    """G9: compute 常见错误不含误导性"系统无法映射时会报错"描述。"""
    desc = build_compute_description("企业基础信息", "企业信息对象", FIELDS)
    assert "系统无法映射时会报错" not in desc
