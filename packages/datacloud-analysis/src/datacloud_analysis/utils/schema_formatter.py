"""
Schema 格式化工具函数

用于将本体对象的元数据格式化为 Markdown Schema
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


def format_object_schema(
    ontology_class: Any,  # OntologyClass
    all_relations: list[Any],  # list[OntologyRelation]
    ontology_loader: Any
) -> str:
    """格式化单个对象的完整 Schema。

    Args:
        ontology_class: OntologyClass 实例
        all_relations: 所有关系列表
        ontology_loader: OntologyLoader 实例

    Returns:
        格式化的 Schema 字符串
    """
    lines = []

    # 1. 对象基本信息（名称、编码、描述）
    lines.append(f"### 对象类型：{ontology_class.object_name}")
    lines.append(f"**object_type**: `{ontology_class.object_code}`")

    # 判断是否为视图
    is_view = "view" in ontology_class.object_code.lower() or "ads_" in ontology_class.object_code
    if is_view:
        lines.append("**类型**: 预定义视图")

    if ontology_class.description:
        lines.append(f"**描述**: {ontology_class.description}")
    lines.append("")

    # 2. 属性列表（属性名称、属性编码、类型、说明、别名）
    if hasattr(ontology_class, 'fields') and ontology_class.fields:
        lines.append("#### 属性列表")
        lines.append("| 属性名称 | 属性编码 | 类型 | 说明 | 别名 |")
        lines.append("|---------|---------|------|------|------|")

        for field in ontology_class.fields[:10]:  # 最多显示10个属性
            field_name = field.field_name
            field_code = field.field_code
            field_type = field.field_type
            description = field.description or ""
            aliases = ", ".join(field.aliases[:3]) if hasattr(field, 'aliases') and field.aliases else ""

            lines.append(f"| {field_name} | {field_code} | {field_type} | {description} | {aliases} |")

        lines.append("")

    # 3. 关联关系（仅对象，视图不显示关系）
    if not is_view:
        object_relations = filter_object_relations(
            ontology_class.object_code,
            all_relations,
            ontology_loader
        )
        if object_relations:
            lines.append("#### 关联关系")
            for rel in object_relations[:5]:  # 最多显示5个关系
                source_name = rel["source_name"]
                target_name = rel["target_name"]
                rel_type = rel["relation_type"]
                desc = rel["description"] or rel["relation_name"]

                lines.append(f"- **{source_name} → {target_name}** ({rel_type}): {desc}")
            lines.append("")

    # 4. 可用动作（动作名称、动作编码、参数列表）
    if hasattr(ontology_class, 'actions') and ontology_class.actions:
        lines.append("#### 可用动作")
        for action in ontology_class.actions[:5]:  # 最多显示5个动作
            action_name = action.action_name
            action_code = action.action_code
            description = action.description or ""

            lines.append(f"- **{action_name}** (`{action_code}`)")
            if description:
                lines.append(f"  - 描述: {description}")

            # 参数列表
            if hasattr(action, 'params') and action.params:
                params_str = []
                for param in action.params[:5]:  # 最多显示5个参数
                    param_code = param.param_code
                    param_type = param.param_type
                    required = "必填" if param.required else "可选"
                    params_str.append(f"`{param_code}` ({param_type}, {required})")

                if params_str:
                    lines.append(f"  - 参数: {', '.join(params_str)}")

            lines.append("")

    return "\n".join(lines)


def filter_object_relations(
    object_code: str,
    all_relations: list[Any],  # list[OntologyRelation]
    ontology_loader: Any
) -> list[dict]:
    """过滤与指定对象相关的关系。

    Args:
        object_code: 对象编码
        all_relations: 所有关系列表
        ontology_loader: OntologyLoader 实例

    Returns:
        关系字典列表
    """
    relations = []

    for rel in all_relations:
        if rel.source_class == object_code or rel.target_class == object_code:
            # 获取源和目标对象的名称
            try:
                source_obj = ontology_loader.get_ontology_class(rel.source_class)
                source_name = source_obj.object_name
            except Exception:
                source_name = rel.source_class

            try:
                target_obj = ontology_loader.get_ontology_class(rel.target_class)
                target_name = target_obj.object_name
            except Exception:
                target_name = rel.target_class

            relations.append({
                "source_class": rel.source_class,
                "source_name": source_name,
                "target_class": rel.target_class,
                "target_name": target_name,
                "relation_type": rel.relation_type,
                "relation_name": rel.relation_name,
                "description": rel.description,
            })

    return relations
