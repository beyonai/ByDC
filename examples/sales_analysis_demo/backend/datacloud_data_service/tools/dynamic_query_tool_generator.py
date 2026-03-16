"""DynamicQueryToolGenerator: 为 DB/KB 对象生成虚拟查询动作。"""

from __future__ import annotations

from typing import Any

from datacloud_data.ontology.loader import OntologyLoader


def _ops_for_field(field: Any, has_term: bool) -> list[str]:
    """根据字段类型和是否绑定术语返回允许的操作符。含 is_null、is_not_null。"""
    null_ops = ["is_null", "is_not_null"]
    if has_term:
        return ["eq", "in", *null_ops]
    ft = (field.field_type or "").upper()
    if ft in ("NUMBER", "INTEGER", "BIGINT", "DECIMAL", "DATE", "DATETIME"):
        return ["eq", "in", "gt", "gte", "lt", "lte", *null_ops]
    return ["eq", "in", "like", *null_ops]


def _aggregate_funcs_for_field(field: Any) -> list[str]:
    """根据字段类型返回允许的聚合函数。"""
    ft = (field.field_type or "").upper()
    if ft in ("NUMBER", "INTEGER", "BIGINT", "DECIMAL", "DATE", "DATETIME"):
        return ["count", "sum", "avg", "min", "max"]
    return ["count"]


class DynamicQueryToolGenerator:
    """为 source_type=DB 或 KNOWLEDGE_BASE 的对象生成 query_{object_code} 虚拟动作。"""

    def __init__(self, loader: OntologyLoader) -> None:
        self._loader = loader

    def generate_ontology_action(self, object_code: str) -> Any | None:
        """为 DB/KB 对象生成虚拟 OntologyAction。description = 对象描述 + 动作说明。"""
        from datacloud_data.ontology.models import OntologyAction

        tool = self.generate(object_code)
        if tool is None:
            return None
        cls = self._loader.get_ontology_class(object_code)
        obj_desc = cls.description or cls.object_name or ""
        action_suffix = (
            "按条件查询，支持过滤、聚合、分组"
            if cls.source_type == "DB"
            else "向量检索，支持 query 和按字段过滤"
        )
        description = f"{obj_desc}。{action_suffix}" if obj_desc else action_suffix
        return OntologyAction(
            action_code=tool["name"],
            action_name=tool.get("title", tool["name"]),
            description=description,
            belong_class=object_code,
            params=[],
            function_refs=[],
            action_type="query",
            script=None,
            is_virtual=True,
            input_schema=tool.get("inputSchema"),
            output_schema={
                "type": "object",
                "properties": {
                    "records": {"type": "array", "items": {"type": "object"}},
                    "total": {"type": "integer"},
                },
            },
        )

    def generate(self, object_code: str) -> dict[str, Any] | None:
        """生成虚拟动作的工具定义，非 DB/KB 返回 None。"""
        try:
            cls = self._loader.get_ontology_class(object_code)
        except Exception:
            return None
        if cls.source_type == "DB":
            return self._generate_db_tool(cls)
        if cls.source_type == "KNOWLEDGE_BASE":
            return self._generate_kb_tool(cls)
        return None

    def _generate_db_tool(self, cls: Any) -> dict[str, Any]:
        """DB 对象：filters 对象（每字段独立 schema）+ aggregates + group_by。"""
        field_codes = [f.field_code for f in cls.fields]
        filters_schema = self._build_filters_object_schema(cls.fields)
        return {
            "name": f"query_{cls.object_code}",
            "title": f"查询{cls.object_name}",
            "description": f"按条件查询 {cls.object_name} 数据，支持过滤、聚合、分组",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filters": filters_schema,
                    "aggregates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {
                                    "type": "string",
                                    "enum": field_codes,
                                    "description": "聚合字段",
                                },
                                "func": {
                                    "type": "string",
                                    "enum": ["count", "sum", "avg", "min", "max"],
                                    "description": "聚合函数",
                                },
                                "as": {
                                    "type": "string",
                                    "description": "返回列的名称/描述，供模型理解；如「KPI汇总」「记录数」；未填时使用默认列名",
                                },
                            },
                            "required": ["field", "func"],
                        },
                        "description": "聚合函数列表",
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string", "enum": field_codes},
                        "description": "分组字段列表",
                    },
                },
            },
            "_meta": {"object_code": cls.object_code, "action_type": "query", "source_type": "DB"},
        }

    def _build_filters_object_schema(self, fields: list) -> dict[str, Any]:
        """构建 filters 的 object schema，每字段独立 property（方案 C）。"""
        term_loader = None
        if hasattr(self._loader, "_config"):
            term_loader = getattr(self._loader._config, "term_loader", None)
        properties: dict[str, Any] = {}
        for f in fields:
            has_term = bool(f.term_set)
            ops = _ops_for_field(f, has_term)
            ft = (f.field_type or "").upper()
            desc = f"{f.field_name} ({ft})"
            enum_codes: list[str] = []
            if has_term and term_loader and f.term_set:
                try:
                    enum_codes = term_loader.get_codes(f.term_set)
                except Exception:
                    pass
            if enum_codes:
                desc += f"，可选值: {','.join(enum_codes)}"
            elif has_term:
                desc += "，术语字段"

            if enum_codes:
                value_schema: dict[str, Any] = {
                    "type": "string",
                    "enum": enum_codes,
                    "description": "eq/in 时必填；is_null/is_not_null 时无需填写",
                }
            elif ft in ("NUMBER", "INTEGER", "BIGINT", "DECIMAL"):
                value_schema = {
                    "type": "number",
                    "description": "eq/in/gt/gte/lt/lte 时必填；is_null/is_not_null 时无需填写",
                }
            elif ft in ("DATE", "DATETIME", "TIMESTAMP"):
                value_schema = {
                    "type": "string",
                    "description": "日期格式；eq/in/gt/gte/lt/lte 时必填；is_null/is_not_null 时无需填写",
                }
            else:
                value_schema = {
                    "description": "eq/in/like 时必填；in 为数组；is_null/is_not_null 时无需填写",
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                }

            properties[f.field_code] = {
                "type": "object",
                "description": desc,
                "properties": {
                    "op": {
                        "type": "string",
                        "enum": ops,
                        "description": "操作符；is_null/is_not_null 时无需 value",
                    },
                    "value": value_schema,
                },
                "required": ["op"],
            }
        return {
            "type": "object",
            "description": "按字段过滤，key 为字段编码",
            "properties": properties,
            "additionalProperties": False,
        }

    def _generate_kb_tool(self, cls: Any) -> dict[str, Any]:
        """KB 对象：query + filters 对象（每字段独立 schema），无 aggregates。"""
        filters_schema = self._build_filters_object_schema(cls.fields)
        return {
            "name": f"query_{cls.object_code}",
            "title": f"检索{cls.object_name}",
            "description": f"向量检索 {cls.object_name}，支持 query 和按字段过滤",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索文本",
                    },
                    "filters": filters_schema,
                },
            },
            "_meta": {
                "object_code": cls.object_code,
                "action_type": "query",
                "source_type": "KNOWLEDGE_BASE",
            },
        }
