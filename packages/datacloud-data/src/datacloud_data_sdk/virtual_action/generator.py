"""虚拟动作 inputSchema 生成器 + 描述文档生成器。

为 lookup / analyze / search 三种动作族生成符合设计规范的 JSON Schema 及 Markdown 描述。

协议版本（§3.2.2 / §3.2.3 字段映射版）：
- dimensions[i].field_name_cn / metrics[i].field_name_cn / filters[i].field_name_cn / select / order_by.field_name_cn
  支持字段中文名（优先）或 field_code（字段编码），系统自动映射；不确定时优先填中文业务术语。
"""

from __future__ import annotations

from typing import Any

# ── 描述文档生成（§6 / §7 模板）────────────────────────────────────────────────


def _field_table_row(f: Any) -> str:
    """生成字段能力表的单行 Markdown。"""
    fc = f.field_code if hasattr(f, "field_code") else f.property_code
    fn = f.field_name if hasattr(f, "field_name") else getattr(f, "property_name", fc)
    role = getattr(f, "analytic_role", "-") or "-"
    kind = getattr(f, "analytic_kind", "-") or "-"
    filter_ops = "/".join(getattr(f, "filter_ops", []) or []) or "-"
    group_ops = "/".join(getattr(f, "group_ops", []) or []) or "-"
    agg_ops = "/".join(getattr(f, "aggregate_ops", []) or []) or "-"
    req = "必须过滤" if getattr(f, "required_filter_group", None) else ""
    return f"| {fc} | {fn} | {role} | {kind} | {filter_ops} | {group_ops} | {agg_ops} | {req} |"


def _required_restrictions(required_filter_groups: list[str]) -> str:
    """仅返回账期类强制约束描述（适用于 query 和 compute 两种描述）。"""
    if not required_filter_groups:
        return ""
    lines = ["\n**强制限制**："]
    if "period_required" in required_filter_groups:
        lines.append("- 必须在 `filters` 中传入账期（period）字段过滤条件")
    return "\n".join(lines)


def build_search_description(
    scope_name: str,
    scope_description: str,
    fields: list[Any],
) -> str:
    """生成 search 动作 Markdown 描述（§6/§7 模板）。"""
    lines: list[str] = []
    if scope_description:
        lines.append(scope_description)
        lines.append("")
    lines.append(
        f"检索{scope_name}知识库文档。支持 query 与结构化过滤；"
        "不支持聚合统计。仅允许使用声明的筛选字段。"
    )
    lines.append("")
    lines.append("**何时使用**：语义相似度检索时使用；不适用于精确 SQL 查询。")

    filterable = [f for f in fields if getattr(f, "filter_ops", [])]
    if filterable:
        lines.append("")
        lines.append("**可过滤字段**：")
        lines.append("| 字段 | 业务名 | 可过滤操作 |")
        lines.append("| --- | --- | --- |")
        for f in filterable:
            fc = f.field_code if hasattr(f, "field_code") else f.property_code
            fn = f.field_name if hasattr(f, "field_name") else getattr(f, "property_name", fc)
            ops = "/".join(getattr(f, "filter_ops", []))
            lines.append(f"| {fc} | {fn} | {ops} |")

    lines.append("")
    lines.append("**常见错误**：")
    lines.append("- query 为空或过短，导致向量相似度差")
    lines.append("- 使用了字段不支持的过滤操作符")

    return "\n".join(lines)


# ── 通用工具 ──────────────────────────────────────────────────────────────────


def _infer_value_type(f: Any) -> str:
    """推断 filters.value 的基础类型，兼容视图字段缺失 field_type 的情况。"""
    ft = (getattr(f, "field_type", "") or "").upper()
    if ft in ("NUMBER", "INTEGER", "BIGINT", "DECIMAL", "DOUBLE", "FLOAT"):
        return "number"
    if ft in ("DATE", "DATETIME", "TIMESTAMP"):
        return "date"

    kind = getattr(f, "analytic_kind", None)
    if kind in (
        "numeric",
        "raw_number",
        "basic_metric",
        "snapshot_metric",
        "derived_metric",
        "formula_metric",
    ):
        return "number"
    if kind in ("datetime", "period"):
        return "date"
    return "string"


def _value_schema_for_field(f: Any) -> dict[str, Any]:
    """根据字段类型构建 value JSON Schema（用于 filters 条目）。"""
    term_set = getattr(f, "term_set", None)
    if term_set:
        return {
            "description": "eq/in 时填写术语值；in 传数组；is_null/is_not_null 不需要",
            "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
        }
    value_type = _infer_value_type(f)
    if value_type == "number":
        return {
            "description": "数值；in 传数组；is_null/is_not_null 不需要",
            "oneOf": [{"type": "number"}, {"type": "array", "items": {"type": "number"}}],
        }
    if value_type == "date":
        return {
            "description": "日期字符串（yyyy-MM-dd）；between 传 [from, to] 数组",
            "oneOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
            ],
        }
    return {
        "description": "eq/in 填字符串或数组；is_null/is_not_null 不需要",
        "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
    }


def _filter_item_schema(f: Any) -> dict[str, Any]:
    """为单字段生成 filters 数组元素 schema（field_name_cn 支持中文名或 field_code）。"""
    field_code = f.field_code if hasattr(f, "field_code") else f.property_code
    field_name = (
        f.field_name if hasattr(f, "field_name") else getattr(f, "property_name", field_code)
    )
    filter_ops = getattr(f, "filter_ops", ["eq", "in", "is_null", "is_not_null"])
    role = getattr(f, "analytic_role", None)
    kind = getattr(f, "analytic_kind", None)
    role_hint = f"[{role}-{kind}]" if role else ""
    return {
        "type": "object",
        "description": f"{field_name}（{field_code}）{role_hint}过滤条件",
        "properties": {
            "field_name_cn": {
                "type": "string",
                "description": (
                    f"字段中文名，如 '{field_name}'；也可填字段编码 '{field_code}'，系统自动识别映射。"
                ),
            },
            "op": {"type": "string", "enum": filter_ops, "description": "过滤操作符"},
            "value": _value_schema_for_field(f),
        },
        "required": ["field_name_cn", "op"],
    }


def _build_filters_schema(fields: list[Any]) -> dict[str, Any]:
    """构建 filters 数组 schema，oneOf 按 field_code 列出每个字段的过滤条目。"""
    filterable = [f for f in fields if getattr(f, "filter_ops", [])]
    if not filterable:
        return {"type": "array", "items": {"type": "object"}, "description": "过滤条件列表"}
    return {
        "type": "array",
        "description": "过滤条件列表，field_name_cn 填字段中文名",
        "items": {"oneOf": [_filter_item_schema(f) for f in filterable]},
        "x-dc-filterable-fields": [
            {
                "field": f.field_code if hasattr(f, "field_code") else f.property_code,
                "ops": getattr(f, "filter_ops", []),
                "role": getattr(f, "analytic_role", None),
                "kind": getattr(f, "analytic_kind", None),
            }
            for f in filterable
        ],
    }


def _fc(f: Any) -> str:
    """取字段编码。"""
    return f.field_code if hasattr(f, "field_code") else f.property_code


def _fn(f: Any) -> str:
    """取字段中文名。"""
    return f.field_name if hasattr(f, "field_name") else getattr(f, "property_name", "")


# ── search schema 生成 ────────────────────────────────────────────────────────


def build_search_schema(scope_name: str, fields: list[Any]) -> dict[str, Any]:
    """生成 search 动作 inputSchema（知识库检索）。"""
    filters_schema = _build_filters_schema(fields)
    return {
        "type": "object",
        "description": f"在知识库 {scope_name} 中检索",
        "properties": {
            "query": {"type": "string", "description": "检索文本，向量相似度匹配"},
            "filters": filters_schema,
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        },
        "required": ["query"],
    }


# ── query_ontology schema / description 生成（字段用 field_code）────────────────


def build_query_schema(
    scope_name: str,
    fields: list[Any],
    required_filter_groups: list[str] | None = None,
) -> dict[str, Any]:
    """生成 query_ontology 动作 inputSchema（field_name_cn 填字段中文名）。

    协议（§3.1 字段映射版）：
    - select / filters.field_name_cn / order_by.field_name_cn 填字段中文名，系统自动映射
    - 自动排除 property_kind=linked 的跨表关联字段
    - 支持 filter_relation 参数（AND/OR）
    """
    queryable = [f for f in fields if getattr(f, "property_kind", "physical") != "linked"]

    filters_schema = _build_filters_schema(queryable)
    required_groups = required_filter_groups or []
    required_hint = f"；强制过滤字段：{', '.join(required_groups)}" if required_groups else ""

    schema: dict[str, Any] = {
        "type": "object",
        "description": f"查询 {scope_name} 明细数据（field_name_cn 填字段中文名）{required_hint}",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "【必填】用户原始查询意图的完整自然语言描述。"
                    "用于歧义判断、复杂查询路由及参数缺失时的兜底推断。"
                    "不得为空，不得使用通配符代替。"
                ),
            },
            "complex_conditions": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": (
                    "溢出过滤区：每个元素用自然语言描述一个"
                    "「过滤条件的值无法在填参时确定为字面常量」的条件，"
                    "例如 '亩产效益后30%的地块'、'营收高于行业平均'。"
                    "能写成字面值的过滤条件仍放入 filters；"
                    "此列表非空时系统自动路由到全能查询路径（data_query）。"
                ),
            },
            "select": {
                "type": "array",
                "items": {"type": "string"},
                "description": "返回字段列表（可填 field_code 或中文名，系统自动映射）；为空时返回全部非关联字段",
                "x-dc-field-catalog": [{"name": _fn(f), "code": _fc(f)} for f in queryable],
            },
            "filters": filters_schema,
            "filter_relation": {
                "type": "string",
                "enum": ["AND", "OR"],
                "default": "AND",
                "description": "过滤条件连接方式；含账期强制约束时禁止用 OR",
            },
            "order_by": {
                "type": "array",
                "description": "排序规则（field_name_cn 填字段中文名或字段编码）",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_name_cn": {
                            "type": "string",
                            "description": "字段中文名或字段编码，系统自动映射",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["asc", "desc"],
                            "default": "asc",
                        },
                    },
                    "required": ["field_name_cn"],
                },
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
    }
    if required_groups:
        schema["x-dc-required-filter-group"] = required_groups
    schema["required"] = ["query"]
    return schema


def build_query_description(
    scope_name: str,
    scope_description: str,
    fields: list[Any],
    required_filter_groups: list[str] | None = None,
    scope_type: str = "object",
) -> str:
    """生成 query_ontology 动作 Markdown 描述（§3.2.2 字段编码版）。"""
    queryable = [f for f in fields if getattr(f, "property_kind", "physical") != "linked"]
    req_groups = required_filter_groups or []
    req_hint = "必须包含账期过滤。" if "period_required" in req_groups else ""

    lines: list[str] = []
    if scope_description:
        lines.append(scope_description)
        lines.append("")
    lines.append(
        f"按条件查询{scope_name}明细。**field 统一使用字段编码（field_code）**；"
        f"支持字段过滤、排序、分页；不支持聚合统计。{req_hint}"
    )
    lines.append("")
    lines.append(
        "**何时使用**：查看具体记录列表时使用；不适用于统计汇总，如需统计请用 compute 动作。"
    )

    restrictions = _required_restrictions(req_groups)
    if restrictions:
        lines.append(restrictions)

    lines.append("")
    lines.append("**可用字段**：")
    lines.append("| 字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for f in queryable:
        lines.append(_field_table_row(f))

    lines.append("")
    lines.append("**常见错误**：")
    lines.append("- 使用了字段不支持的 op 操作符")
    lines.append("- field 填了字段中文名而非字段编码（field_code）")
    if req_groups:
        lines.append("- 缺少账期（period）过滤条件")

    return "\n".join(lines)


# ── compute_ontology schema / description 生成（字段用 field_code）────────────


def build_compute_schema(
    scope_name: str,
    fields: list[Any],
    required_filter_groups: list[str] | None = None,
) -> dict[str, Any]:
    """生成 compute_ontology 动作 inputSchema（field_name_cn 填字段中文名）。

    协议（§3.1 字段映射版）：
    - dimensions[i].field_name_cn / metrics[i].field_name_cn / filters[i].field_name_cn 填字段中文名
    """
    dim_fields = [f for f in fields if getattr(f, "group_ops", [])]
    msr_fields = [
        f
        for f in fields
        if (getattr(f, "analytic_role", None) == "measure" and getattr(f, "aggregate_ops", []))
        or getattr(f, "secondary_role", None) == "measure"
    ]
    filters_schema = _build_filters_schema(fields)

    def _dim_item(f: Any) -> dict[str, Any]:
        fcode = _fc(f)
        fname = _fn(f)
        kind = getattr(f, "analytic_kind", None)
        gops = getattr(f, "group_ops", [])
        item: dict[str, Any] = {
            "type": "object",
            "description": f"{fname}（{fcode}）[{getattr(f, 'analytic_role', '')}-{kind}] 分组维度",
            "properties": {
                "field_name_cn": {
                    "type": "string",
                    "description": (
                        f"字段中文名，如 '{fname}'；也可填字段编码 '{fcode}'，系统自动识别。"
                    ),
                },
                "group_op": {"type": "string", "enum": gops, "description": "分组方式"},
            },
            "required": ["field_name_cn", "group_op"],
        }
        if "range" in gops:
            item["properties"]["buckets"] = {
                "type": "array",
                "description": "range 分组时必填，定义分桶区间",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {
                            "type": ["number", "null"],
                            "description": "区间起始（含），null 表示无下限",
                        },
                        "to": {
                            "type": ["number", "null"],
                            "description": "区间终止（不含），null 表示无上限",
                        },
                        "label": {"type": "string", "description": "桶标签"},
                    },
                    "required": ["label"],
                },
            }
        return item

    def _msr_item(f: Any) -> dict[str, Any]:
        fcode = _fc(f)
        fname = _fn(f)
        agg_ops = getattr(f, "aggregate_ops", []) or ["count", "count_distinct"]
        return {
            "type": "object",
            "description": (
                f"{fname}（{fcode}）[{getattr(f, 'analytic_role', '')}-{getattr(f, 'analytic_kind', '')}] 统计指标"
            ),
            "properties": {
                "field_name_cn": {
                    "type": "string",
                    "description": (
                        f"字段中文名，如 '{fname}'；也可填字段编码 '{fcode}'，与 expr 互斥。"
                    ),
                },
                "expr": {
                    "type": "string",
                    "description": "公式表达式（与 field_name_cn 互斥），可填中文运算式，系统映射后生成 SQL。",
                },
                "filters": {
                    "type": "array",
                    "description": "条件聚合过滤（CASE WHEN），field_name_cn/value 可填中文，规则同行级 filters。",
                    "items": {"type": "object"},
                },
                "agg": {
                    "type": "string",
                    "enum": agg_ops,
                    "description": (
                        "聚合函数（协议键名必须为 agg，如 count_distinct；禁止使用 func 键）"
                    ),
                },
                "as": {"type": "string", "description": "结果列别名，用于 having/order_by 引用"},
            },
            "required": ["agg", "as"],
        }

    count_all_item: dict[str, Any] = {
        "type": "object",
        "description": "内建行数统计，无需指定 field_name_cn",
        "properties": {
            "agg": {"type": "string", "const": "count_all"},
            "as": {"type": "string", "description": "结果列别名"},
        },
        "required": ["agg", "as"],
    }

    metrics_items = [_msr_item(f) for f in msr_fields] + [count_all_item]
    required_groups = required_filter_groups or []
    required_hint = f"；强制过滤字段：{', '.join(required_groups)}" if required_groups else ""

    schema: dict[str, Any] = {
        "type": "object",
        "description": f"统计分析 {scope_name}（field_name_cn 填字段中文名）{required_hint}",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "【必填】用户原始查询意图的完整自然语言描述。"
                    "用于歧义判断、复杂查询路由及参数缺失时的兜底推断。"
                    "不得为空，不得使用通配符代替。"
                ),
            },
            "complex_conditions": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": (
                    "溢出过滤区：每个元素用自然语言描述一个"
                    "「过滤条件的值无法在填参时确定为字面常量」的条件，"
                    "例如 '亩产效益后30%的地块'、'营收高于行业平均'。"
                    "能写成字面值的过滤条件仍放入 filters；"
                    "此列表非空时系统自动路由到全能查询路径（data_query）。"
                ),
            },
            "dimensions": {
                "type": "array",
                "description": "分组维度（field_name_cn 填字段中文名；时间类须指定粒度；range 须带 buckets）",
                "items": {"oneOf": [_dim_item(f) for f in dim_fields]}
                if dim_fields
                else {"type": "object"},
                "examples": [[{"field_name_cn": "企业等级", "group_op": "direct"}]],
                "x-dc-dimension-fields": [
                    {
                        "field": _fc(f),
                        "field_name": _fn(f),
                        "group_ops": getattr(f, "group_ops", []),
                        "kind": getattr(f, "analytic_kind", None),
                    }
                    for f in dim_fields
                ],
            },
            "metrics": {
                "type": "array",
                "description": "统计指标（field_name_cn 填字段中文名；至少一个；可用 count_all 统计行数）",
                "items": {"oneOf": metrics_items},
                "minItems": 1,
                "examples": [
                    [{"field_name_cn": "企业总营收（万元）", "agg": "sum", "as": "总营收"}]
                ],
                "x-dc-measure-fields": [
                    {
                        "field": _fc(f),
                        "field_name": _fn(f),
                        "agg_ops": getattr(f, "aggregate_ops", []),
                        "kind": getattr(f, "analytic_kind", None),
                    }
                    for f in msr_fields
                ],
            },
            "filters": filters_schema,
            "having": {
                "type": "array",
                "description": "聚合后过滤；field_name_cn 必须是 metrics 中某项的 as 别名",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_name_cn": {"type": "string", "description": "metrics.as 别名"},
                        "op": {
                            "type": "string",
                            "enum": ["eq", "gt", "gte", "lt", "lte", "between"],
                        },
                        "value": {
                            "oneOf": [
                                {"type": "number"},
                                {
                                    "type": "array",
                                    "items": {"type": "number"},
                                    "minItems": 2,
                                    "maxItems": 2,
                                },
                            ]
                        },
                    },
                    "required": ["field_name_cn", "op", "value"],
                },
            },
            "order_by": {
                "type": "array",
                "description": "排序（field_name_cn 可以是 metrics.as 别名或维度字段中文名/编码）",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_name_cn": {"type": "string"},
                        "direction": {
                            "type": "string",
                            "enum": ["asc", "desc"],
                            "default": "desc",
                        },
                    },
                    "required": ["field_name_cn"],
                },
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
            "filter_relation": {
                "type": "string",
                "enum": ["AND", "OR"],
                "default": "AND",
                "description": "过滤条件连接方式；含账期强制约束时禁止用 OR",
            },
        },
        "required": ["metrics"],
    }
    if required_groups:
        schema["x-dc-required-filter-group"] = required_groups
    schema["required"] = ["metrics", "query"]
    return schema


def build_compute_description(
    scope_name: str,
    scope_description: str,
    fields: list[Any],
    required_filter_groups: list[str] | None = None,
    scope_type: str = "object",
) -> str:
    """生成 compute_ontology 动作 Markdown 描述（§3.2.3 字段编码版）。"""
    req_groups = required_filter_groups or []
    req_hint = "必须满足账期等强制过滤规则。" if "period_required" in req_groups else ""
    view_hint = "结果来自多对象 JOIN。" if scope_type == "view" else ""

    lines: list[str] = []
    if scope_description:
        lines.append(scope_description)
        lines.append("")
    lines.append(
        f"按规则对{scope_name}做分组统计。**field 统一使用字段编码（field_code）**；"
        f"支持 dimensions + metrics + filters；不支持明细输出。{req_hint}{view_hint}"
    )
    lines.append("")
    lines.append(
        "**何时使用**：需要分组统计、聚合指标时使用；"
        "不适用于查看明细列表，如需明细请用 query 动作。"
    )

    restrictions = _required_restrictions(req_groups)
    if restrictions:
        lines.append(restrictions)
        # compute 专有约束接续在同一"强制限制"块后
        lines.append("- 度量字段只能出现在 `metrics` 中，不能作为维度")
        lines.append("- `metrics` 不能为空")
    else:
        lines.append("\n**强制限制**：")
        lines.append("- 度量字段只能出现在 `metrics` 中，不能作为维度")
        lines.append("- `metrics` 不能为空")

    # 拍照指标特殊说明
    snapshot_fields = [f for f in fields if getattr(f, "analytic_kind", None) == "snapshot_metric"]
    if snapshot_fields:
        names = "、".join(_fn(f) for f in snapshot_fields)
        lines.append(f"- 拍照指标（{names}）跨账期时不支持 SUM，请改用 MAX/MIN")

    lines.append("")
    lines.append("**字段能力**：")
    lines.append("| 字段编码 | 中文名 | 角色 | 类型 | 可过滤 | 可分组 | 可聚合 | 特殊说明 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for f in fields:
        lines.append(_field_table_row(f))

    lines.append("")
    lines.append("**常见错误**：")
    lines.append("- `metrics` 为空（必须至少一个指标）")
    lines.append(
        '- `metrics` 项误用 `func` 表示聚合：必须使用键名 **`agg`**（如 `"agg": "count_distinct"`）'
    )
    lines.append("- field 填了字段中文名而非字段编码（field_code）")
    lines.append("- `having.field` 未使用 `metrics` 中的 `as` 别名")
    if req_groups:
        lines.append("- 缺少账期（period）过滤条件")

    return "\n".join(lines)
