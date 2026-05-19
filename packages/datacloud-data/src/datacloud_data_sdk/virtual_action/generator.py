"""虚拟动作 inputSchema 生成器 + 描述文档生成器。

为 lookup / analyze / search 三种动作族生成符合设计规范的 JSON Schema 及 Markdown 描述。

协议版本（§3.2.2 / §3.2.3 属性编码版）：
- dimensions[i].field / metrics[i].field / filters[i].field / select / order_by.field
  统一使用对象或视图的属性编码（如 ``total_revenue``）。
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
        f"检索{scope_name}知识库文档。入参协议与 query 明细查询保持一致，"
        "额外必须提供 query 检索文本；支持 select、filters、filter_relation、order_by、limit、offset；"
        "不支持聚合统计。仅允许使用声明的字段。"
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


def _field_code_property(field_code: str, field_name: str) -> dict[str, Any]:
    """构建只接受属性编码的 OpenAPI field 属性 schema。"""
    return {
        "type": "string",
        "enum": [field_code],
        "description": f"属性编码，固定为 `{field_code}`（{field_name}）",
    }


def _field_code_enum_property(fields: list[Any], description: str) -> dict[str, Any]:
    """构建仅允许属性编码枚举的 field 属性 schema。"""
    return {
        "type": "string",
        "enum": [_fc(f) for f in fields],
        "description": description,
    }


def _filter_item_schema(f: Any, *, strict_field_code: bool) -> dict[str, Any]:
    """为单字段生成 filters 数组元素 schema。"""
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
            "field": _field_code_property(field_code, field_name)
            if strict_field_code
            else {
                "type": "string",
                "description": (
                    f"字段中文名（如 '{field_name}'）或字段编码（如 '{field_code}'），系统自动识别映射；"
                    "若字段名在当前对象中找不到精确对应，直接填用户原词，禁止猜测替换为相近字段名。"
                ),
            },
            "op": {"type": "string", "enum": filter_ops, "description": "过滤操作符"},
            "value": _value_schema_for_field(f),
        },
        "required": ["field", "op"],
    }


_FILTER_CATCHALL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "兜底条目：字段名在当前对象中找不到精确对应时使用",
    "properties": {
        "field": {
            "type": "string",
            "description": (
                "直接填写用户原词（如'贡献率'），禁止猜测替换为相近字段名；系统后端负责语义解析。"
            ),
        },
        "op": {
            "type": "string",
            "enum": [
                "eq",
                "neq",
                "gt",
                "gte",
                "lt",
                "lte",
                "in",
                "not_in",
                "is_null",
                "is_not_null",
                "like",
                "between",
            ],
            "description": "过滤操作符",
        },
        "value": {
            "description": "过滤值",
            "oneOf": [
                {"type": "string"},
                {"type": "number"},
                {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "number"}]}},
            ],
        },
    },
    "required": ["field", "op"],
}


def _build_filters_schema(fields: list[Any], *, strict_field_code: bool = False) -> dict[str, Any]:
    """构建 filters 数组 schema。"""
    filterable = [f for f in fields if getattr(f, "filter_ops", [])]
    if not filterable:
        return {"type": "array", "items": {"type": "object"}, "description": "过滤条件列表"}
    items = [_filter_item_schema(f, strict_field_code=strict_field_code) for f in filterable]
    if not strict_field_code:
        items.append(_FILTER_CATCHALL_SCHEMA)
    description = (
        "过滤条件列表，field 统一填写属性编码"
        if strict_field_code
        else "过滤条件列表，field 可填写字段中文名或字段编码"
    )
    return {
        "type": "array",
        "description": description,
        "items": {"oneOf": items},
    }


def _fc(f: Any) -> str:
    """取字段编码。"""
    return f.field_code if hasattr(f, "field_code") else f.property_code


def _fn(f: Any) -> str:
    """取字段中文名。"""
    return f.field_name if hasattr(f, "field_name") else getattr(f, "property_name", "")


# ── search schema 生成 ────────────────────────────────────────────────────────


def build_search_schema(scope_name: str, fields: list[Any]) -> dict[str, Any]:
    """生成 search 动作 inputSchema（知识库检索）。

    KB 检索协议与 DB query 协议保持一致，额外增加必填 ``query`` 检索文本。
    """
    filters_schema = _build_filters_schema(fields, strict_field_code=True)
    return {
        "type": "object",
        "additionalProperties": False,
        "description": (
            f"在知识库 {scope_name} 中检索文件。"
            "协议与 query 明细查询一致，额外必须填写 query 语义检索文本；"
            "select、filters.field、order_by.field 只能填写当前工具列出的属性编码。"
        ),
        "x-dc-action-family": "search",
        "x-dc-scope-type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索文本，向量相似度匹配"},
            "select": {
                "type": "array",
                "items": {"type": "string", "enum": [_fc(f) for f in fields]},
                "description": "需要返回的元数据字段列表，统一填写属性编码；为空时由服务端返回默认字段。",
                "x-dc-field-catalog": [{"name": _fn(f), "code": _fc(f)} for f in fields],
            },
            "filters": filters_schema,
            "filter_relation": {
                "type": "string",
                "enum": ["AND", "OR"],
                "default": "AND",
                "description": "过滤条件连接方式",
            },
            "order_by": {
                "type": "array",
                "description": "排序规则（field 统一填写属性编码）",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field": _field_code_enum_property(
                            fields,
                            "属性编码，只允许使用当前知识库对象中声明的属性编码。",
                        ),
                        "direction": {
                            "type": "string",
                            "enum": ["asc", "desc"],
                            "default": "asc",
                            "description": "排序方向",
                        },
                    },
                    "required": ["field"],
                },
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
        "required": ["query"],
    }


def _json_type_for_field(field: Any) -> str:
    field_type = str(getattr(field, "field_type", "") or "").upper()
    if field_type in {"NUMBER", "DECIMAL", "DOUBLE", "FLOAT", "REAL"}:
        return "number"
    if field_type in {"INTEGER", "INT", "BIGINT", "LONG", "SMALLINT"}:
        return "integer"
    if field_type == "BOOLEAN":
        return "boolean"
    if field_type == "ARRAY":
        return "array"
    if field_type == "OBJECT":
        return "object"
    return "string"


def _field_value_property(field: Any) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": _json_type_for_field(field),
        "description": getattr(field, "field_name", None) or getattr(field, "field_code", ""),
    }
    if schema["type"] == "array":
        schema["items"] = {"type": "string"}
    return schema


def _writable_fields(fields: list[Any], *, include_primary_key: bool = False) -> list[Any]:
    return [
        field
        for field in fields
        if getattr(field, "property_kind", "physical") == "physical"
        and (include_primary_key or not getattr(field, "is_primary_key", False))
    ]


def build_kb_write_schema(scope_name: str, fields: list[Any]) -> dict[str, Any]:
    """生成 write_* 知识库写入动作 inputSchema。"""
    label_properties = {_fc(field): _field_value_property(field) for field in fields}
    return {
        "type": "object",
        "additionalProperties": False,
        "description": f"写入{scope_name}知识库文档。",
        "x-dc-action-family": "write",
        "x-dc-scope-type": "object",
        "properties": {
            "labels": {
                "type": "object",
                "additionalProperties": False,
                "description": "知识库属性标签，键必须是对象属性编码。",
                "properties": label_properties,
            },
            "source_path": {
                "type": "string",
                "description": "上传到知识库后的文件全路径，以 / 开头，不包括知识库名称。",
            },
            "content": {"type": "string", "description": "源文件的文本内容。"},
            "file_description": {"type": "string", "description": "文件描述。"},
        },
        "required": ["source_path", "content"],
    }


def build_insert_schema(scope_name: str, fields: list[Any]) -> dict[str, Any]:
    """生成 insert_* 动态表新增动作 inputSchema。"""
    writable = _writable_fields(fields, include_primary_key=False)
    properties = {_fc(field): _field_value_property(field) for field in writable}
    required = [_fc(field) for field in writable if getattr(field, "required", False)]
    item_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
    }
    if required:
        item_schema["required"] = required
    return {
        "type": "object",
        "additionalProperties": False,
        "description": f"向动态表{scope_name}新增记录。records 中不能包含自动生成主键字段。",
        "x-dc-action-family": "insert",
        "x-dc-scope-type": "object",
        "properties": {
            "records": {
                "type": "array",
                "minItems": 1,
                "items": item_schema,
                "description": "待新增记录列表，字段统一填写对象属性编码。",
            }
        },
        "required": ["records"],
    }


def build_update_schema(scope_name: str, fields: list[Any]) -> dict[str, Any]:
    """生成 update_* 动态表修改动作 inputSchema。"""
    writable = _writable_fields(fields, include_primary_key=False)
    return {
        "type": "object",
        "additionalProperties": False,
        "description": f"按 filters 修改动态表{scope_name}记录。必须提供 filters。",
        "x-dc-action-family": "update",
        "x-dc-scope-type": "object",
        "properties": {
            "values": {
                "type": "object",
                "additionalProperties": False,
                "properties": {_fc(field): _field_value_property(field) for field in writable},
                "description": "需要修改的字段值，字段统一填写对象属性编码。",
            },
            "filters": _build_filters_schema(fields, strict_field_code=True),
            "filter_relation": {
                "type": "string",
                "enum": ["AND", "OR"],
                "default": "AND",
                "description": "过滤条件连接方式",
            },
        },
        "required": ["values", "filters"],
    }


def build_delete_schema(scope_name: str, fields: list[Any]) -> dict[str, Any]:
    """生成 delete_* 动态表物理删除动作 inputSchema。"""
    return {
        "type": "object",
        "additionalProperties": False,
        "description": f"按 filters 物理删除动态表{scope_name}记录。必须提供 filters。",
        "x-dc-action-family": "delete",
        "x-dc-scope-type": "object",
        "properties": {
            "filters": _build_filters_schema(fields, strict_field_code=True),
            "filter_relation": {
                "type": "string",
                "enum": ["AND", "OR"],
                "default": "AND",
                "description": "过滤条件连接方式",
            },
        },
        "required": ["filters"],
    }


# ── query_ontology schema / description 生成（字段用 field_code）────────────────


def build_query_schema(
    scope_name: str,
    fields: list[Any],
    required_filter_groups: list[str] | None = None,
    scope_type: str = "object",
    scope_code: str | None = None,
) -> dict[str, Any]:
    """生成 query_ontology 动作 inputSchema（field 统一使用属性编码）。

    协议（§3.1 属性编码版）：
    - select / filters.field / order_by.field 必须使用属性编码
    - 自动排除 property_kind=linked 的跨表关联字段
    - 支持 filter_relation 参数（AND/OR）
    """
    queryable = [f for f in fields if getattr(f, "property_kind", "physical") != "linked"]

    filters_schema = _build_filters_schema(queryable, strict_field_code=True)
    required_groups = required_filter_groups or []
    required_hint = f"；强制过滤字段：{', '.join(required_groups)}" if required_groups else ""

    scope_label = "对象" if scope_type == "object" else "视图"
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "description": (
            f"查询{scope_label}{scope_name}的明细记录。"
            "select、filters.field、order_by.field 只能填写当前工具列出的属性编码。"
            "适合查记录列表，不适合做统计汇总。"
            f"{required_hint}"
        ),
        "x-dc-action-family": "query",
        "x-dc-scope-type": scope_type,
        "properties": {
            "select": {
                "type": "array",
                "items": {"type": "string", "enum": [_fc(f) for f in queryable]},
                "description": ("返回字段列表，统一填写属性编码；为空时返回全部非关联字段。"),
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
                "description": "排序规则（field 统一填写属性编码）",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field": _field_code_enum_property(
                            queryable,
                            "属性编码，只允许使用当前对象或视图中声明的属性编码。",
                        ),
                        "direction": {
                            "type": "string",
                            "enum": ["asc", "desc"],
                            "default": "asc",
                            "description": "排序方向，只允许 'asc'（升序）或 'desc'（降序）。键名必须是 direction，不能用 sort/op/order。",
                        },
                    },
                    "required": ["field"],
                },
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
    }
    if scope_code:
        schema["x-dc-scope-code"] = scope_code
    if required_groups:
        schema["x-dc-required-filter-group"] = required_groups
    return schema


def build_query_description(
    scope_name: str,
    scope_description: str,
    fields: list[Any],
    required_filter_groups: list[str] | None = None,
    scope_type: str = "object",
) -> str:
    """生成 query_ontology 动作 Markdown 描述（§3.2.2 属性编码版）。"""
    queryable = [f for f in fields if getattr(f, "property_kind", "physical") != "linked"]
    req_groups = required_filter_groups or []
    req_hint = "必须包含账期过滤。" if "period_required" in req_groups else ""

    lines: list[str] = []
    if scope_description:
        lines.append(scope_description)
        lines.append("")
    if scope_type == "view":
        lines.append(
            f"按条件查询视图{scope_name}的明细结果。"
            "**select / filters.field / order_by.field 统一使用视图属性编码**；"
            "适合在已经定义好的视图口径下查看列表结果，不适合做聚合统计。"
            f"{req_hint}"
        )
    else:
        lines.append(
            f"按条件查询对象{scope_name}的明细记录。"
            "**select / filters.field / order_by.field 统一使用对象属性编码**；"
            "支持字段过滤、排序、分页；不支持聚合统计。"
            f"{req_hint}"
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
    lines.append("- 将中文名、口语词或模糊概念猜测替换为相近属性编码")
    lines.append("- 在 `select`、`filters.field`、`order_by.field` 中使用中文名而不是属性编码")
    lines.append("- order_by 中用了 sort/op/order 键名，应统一使用 direction")
    if req_groups:
        lines.append("- 缺少账期（period）过滤条件")

    return "\n".join(lines)


# ── compute_ontology schema / description 生成（字段用 field_code）────────────


def build_compute_schema(
    scope_name: str,
    fields: list[Any],
    required_filter_groups: list[str] | None = None,
    scope_type: str = "object",
    scope_code: str | None = None,
) -> dict[str, Any]:
    """生成 compute_ontology 动作 inputSchema（field 统一使用属性编码）。

    协议（§3.1 属性编码版）：
    - dimensions[i].field / metrics[i].field / filters[i].field 必须使用属性编码
    """
    dim_fields = [f for f in fields if getattr(f, "group_ops", [])]
    msr_fields = [
        f
        for f in fields
        if (getattr(f, "analytic_role", None) == "measure" and getattr(f, "aggregate_ops", []))
        or getattr(f, "secondary_role", None) == "measure"
    ]
    filters_schema = _build_filters_schema(fields, strict_field_code=True)

    def _dim_item(f: Any) -> dict[str, Any]:
        fcode = _fc(f)
        fname = _fn(f)
        kind = getattr(f, "analytic_kind", None)
        gops = getattr(f, "group_ops", [])
        item: dict[str, Any] = {
            "type": "object",
            "description": f"{fname}（{fcode}）[{getattr(f, 'analytic_role', '')}-{kind}] 分组维度",
            "properties": {
                "field": {
                    **_field_code_property(fcode, fname),
                },
                "group_op": {"type": "string", "enum": gops, "description": "分组方式"},
            },
            "required": ["field", "group_op"],
        }
        if "range" in gops:
            item["properties"]["buckets"] = {
                "type": "array",
                "description": "range 分组时必填，定义分桶区间",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {
                            "type": "number",
                            "nullable": True,
                            "description": "区间起始（含），null 表示无下限",
                        },
                        "to": {
                            "type": "number",
                            "nullable": True,
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
                "field": {
                    **_field_code_property(fcode, fname),
                },
                "expr": {
                    "type": "string",
                    "description": "公式表达式（与 field 互斥），系统会基于属性编码生成 SQL。",
                },
                "filters": {
                    "type": "array",
                    "description": "条件聚合过滤（CASE WHEN），field 统一填写属性编码，规则同行级 filters。",
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
            "required": ["field", "agg", "as"],
        }

    count_all_item: dict[str, Any] = {
        "type": "object",
        "description": '统计总行数（COUNT(*)），格式固定为 {"agg": "count_all", "as": "别名"}，不需要也不能填 field',
        "properties": {
            "agg": {"type": "string", "enum": ["count_all"]},
            "as": {"type": "string", "description": "结果列别名"},
        },
        "required": ["agg", "as"],
    }

    metrics_items = [_msr_item(f) for f in msr_fields] + [count_all_item]
    required_groups = required_filter_groups or []
    required_hint = f"；强制过滤字段：{', '.join(required_groups)}" if required_groups else ""

    scope_label = "对象" if scope_type == "object" else "视图"
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "description": (
            f"对{scope_label}{scope_name}执行分组统计。"
            "dimensions.field、metrics.field、filters.field 只能填写当前工具列出的属性编码。"
            "必须至少提供一个 metrics；如需看明细，请改用 query 动作。"
            f"{required_hint}"
        ),
        "x-dc-action-family": "compute",
        "x-dc-scope-type": scope_type,
        "properties": {
            "dimensions": {
                "type": "array",
                "description": "分组维度（field 统一填写属性编码；时间类须指定粒度；range 须带 buckets）",
                "items": {"oneOf": [_dim_item(f) for f in dim_fields]}
                if dim_fields
                else {"type": "object"},
                "example": [{"field": "enterprise_level_name", "group_op": "direct"}],
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
                "description": "统计指标（field 统一填写属性编码；至少一个；可用 count_all 统计行数）",
                "items": {"oneOf": metrics_items},
                "minItems": 1,
                "example": [{"field": "total_revenue", "agg": "sum", "as": "total_revenue_sum"}],
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
                "description": "聚合后过滤；field 必须是 metrics 中某项的 as 别名",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field": {"type": "string", "description": "metrics.as 别名"},
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
                    "required": ["field", "op", "value"],
                },
            },
            "order_by": {
                "type": "array",
                "description": "排序（field 可以是 metrics.as 别名或维度属性编码）",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field": {"type": "string"},
                        "direction": {
                            "type": "string",
                            "enum": ["asc", "desc"],
                            "default": "desc",
                        },
                    },
                    "required": ["field"],
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
    if scope_code:
        schema["x-dc-scope-code"] = scope_code
    if required_groups:
        schema["x-dc-required-filter-group"] = required_groups
    return schema


def build_compute_description(
    scope_name: str,
    scope_description: str,
    fields: list[Any],
    required_filter_groups: list[str] | None = None,
    scope_type: str = "object",
) -> str:
    """生成 compute_ontology 动作 Markdown 描述（§3.2.3 属性编码版）。"""
    req_groups = required_filter_groups or []
    req_hint = "必须满足账期等强制过滤规则。" if "period_required" in req_groups else ""
    view_hint = "结果来自多对象 JOIN。" if scope_type == "view" else ""

    lines: list[str] = []
    if scope_description:
        lines.append(scope_description)
        lines.append("")
    if scope_type == "view":
        lines.append(
            f"按规则对视图{scope_name}做分组统计。"
            "**dimensions.field / metrics.field / filters.field 统一使用视图属性编码**；"
            f"适合跨对象口径下的聚合分析，不适合明细输出。{req_hint}{view_hint}"
        )
    else:
        lines.append(
            f"按规则对对象{scope_name}做分组统计。"
            "**dimensions.field / metrics.field / filters.field 统一使用对象属性编码**；"
            f"支持 dimensions + metrics + filters；不适合直接查看明细。{req_hint}{view_hint}"
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
    lines.append(
        "- 在 `dimensions.field`、`metrics.field`、`filters.field` 中使用中文名而不是属性编码"
    )
    lines.append("- `having.field` 未使用 `metrics` 中的 `as` 别名")
    lines.append("- order_by 中用了 sort/op/order 键名，应统一使用 direction")
    if req_groups:
        lines.append("- 缺少账期（period）过滤条件")

    return "\n".join(lines)
