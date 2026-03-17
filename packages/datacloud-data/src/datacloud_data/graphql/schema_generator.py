"""从本体（OntologyClass 列表）生成 GraphQL Schema。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_data.ontology.models import OntologyClass, OntologyRelation

# field_type -> GraphQL 标量
_FIELD_TYPE_MAP = {
    "STRING": "String",
    "NUMBER": "Float",
    "INTEGER": "Int",
    "BOOLEAN": "Boolean",
    "DATE": "String",
    "DATETIME": "String",
    "ARRAY": "String",
    "OBJECT": "String",
}


def _to_pascal_case(snake: str) -> str:
    """snake_case -> PascalCase。"""
    components = snake.split("_")
    return "".join(x.title() for x in components if x)


def _field_type_to_graphql(field_type: str) -> str:
    """本体 field_type 映射到 GraphQL 标量。"""
    return _FIELD_TYPE_MAP.get(field_type.upper(), "String")


def generate_schema(
    classes: list[OntologyClass],
    relations: list[OntologyRelation],
) -> str:
    """从 OntologyClass 列表生成 GraphQL SDL 字符串。

    Args:
        classes: 本体类列表
        relations: 关联关系列表（linked 字段可后续扩展）

    Returns:
        GraphQL schema 字符串
    """
    lines: list[str] = []
    for cls in classes:
        type_name = _to_pascal_case(cls.object_code)
        field_lines: list[str] = []
        for f in cls.fields:
            gql_type = _field_type_to_graphql(f.field_type)
            field_lines.append(f"  {f.field_code}: {gql_type}")
        lines.append(f"type {type_name} {{\n" + "\n".join(field_lines) + "\n}")
    return "\n".join(lines)
