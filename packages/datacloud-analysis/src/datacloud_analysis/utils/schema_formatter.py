"""
Schema 格式化工具函数

用于将本体对象的元数据格式化为 Markdown Schema
"""

from __future__ import annotations
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_data_sdk.ontology.loader import OntologyClass, OntologyRelation, OntologyLoader

logger = logging.getLogger(__name__)

# 常量定义
MAX_FIELDS_DISPLAY = 10
MAX_RELATIONS_DISPLAY = 5
MAX_ACTIONS_DISPLAY = 5
MAX_ACTION_PARAMS_DISPLAY = 5
MAX_FIELD_ALIASES_DISPLAY = 3


def format_object_schema(
    ontology_class: Any,  # OntologyClass
    all_relations: list[Any],  # list[OntologyRelation]
    ontology_loader: Any,  # OntologyLoader
) -> str:
    """格式化单个对象的完整 Schema。

    Args:
        ontology_class: OntologyClass 实例，包含对象的元数据
        all_relations: 所有关系列表，用于查找与当前对象相关的关系
        ontology_loader: OntologyLoader 实例，用于查询其他对象信息

    Returns:
        格式化的 Schema 字符串，使用 Markdown 格式
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

    # 🆕 添加工具使用说明
    lines.append("")
    lines.append(
        f'**如何查询**: 使用 `query_objects` 工具，参数 `object_type="{ontology_class.object_code}"`'
    )
    lines.append("")

    # 2. 属性列表（属性名称、属性编码、类型、说明、别名）
    if hasattr(ontology_class, "fields") and ontology_class.fields:
        lines.append("#### 属性列表")
        lines.append("| 属性名称 | 属性编码 | 类型 | 说明 | 别名 |")
        lines.append("|---------|---------|------|------|------|")

        for field in ontology_class.fields[:MAX_FIELDS_DISPLAY]:
            field_name = field.field_name
            field_code = field.field_code
            field_type = field.field_type
            description = field.description or ""
            aliases = (
                ", ".join(field.aliases[:MAX_FIELD_ALIASES_DISPLAY])
                if hasattr(field, "aliases") and field.aliases
                else ""
            )

            lines.append(
                f"| {field_name} | {field_code} | {field_type} | {description} | {aliases} |"
            )

        lines.append("")

    # 3. 关联关系（仅对象，视图不显示关系）
    if not is_view:
        object_relations = filter_object_relations(
            ontology_class.object_code, all_relations, ontology_loader
        )
        if object_relations:
            lines.append("#### 关联关系")
            for rel in object_relations[:MAX_RELATIONS_DISPLAY]:
                source_name = rel["source_name"]
                target_name = rel["target_name"]
                rel_type = rel["relation_type"]
                desc = rel["description"] or rel["relation_name"]

                lines.append(f"- **{source_name} → {target_name}** ({rel_type}): {desc}")
            lines.append("")

    # 4. 可用动作（动作名称、动作编码、参数列表）
    if hasattr(ontology_class, "actions") and ontology_class.actions:
        lines.append("#### 可用动作")
        for action in ontology_class.actions[:MAX_ACTIONS_DISPLAY]:
            action_name = action.action_name
            action_code = action.action_code
            description = action.description or ""

            lines.append(f"- **{action_name}** (`{action_code}`)")
            if description:
                lines.append(f"  - 描述: {description}")

            # 参数列表
            if hasattr(action, "params") and action.params:
                params_str = []
                for param in action.params[:MAX_ACTION_PARAMS_DISPLAY]:
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
    ontology_loader: Any,  # OntologyLoader
) -> list[dict]:
    """过滤与指定对象相关的关系。

    遍历所有关系，找出源或目标为指定对象的关系，
    并解析出源和目标对象的名称。

    Args:
        object_code: 对象编码，用于匹配关系的源或目标
        all_relations: 所有关系列表，包含系统中定义的所有对象关系
        ontology_loader: OntologyLoader 实例，用于查询对象名称

    Returns:
        关系字典列表，每个字典包含：
        - source_class: 源对象编码
        - source_name: 源对象名称
        - target_class: 目标对象编码
        - target_name: 目标对象名称
        - relation_type: 关系类型
        - relation_name: 关系名称
        - description: 关系描述
    """
    relations = []

    for rel in all_relations:
        if rel.source_class == object_code or rel.target_class == object_code:
            # 获取源和目标对象的名称
            try:
                source_obj = ontology_loader.get_ontology_class(rel.source_class)
                source_name = source_obj.object_name
            except Exception as e:
                logger.debug("Failed to get source object name for %s: %s", rel.source_class, e)
                source_name = rel.source_class

            try:
                target_obj = ontology_loader.get_ontology_class(rel.target_class)
                target_name = target_obj.object_name
            except Exception as e:
                logger.debug("Failed to get target object name for %s: %s", rel.target_class, e)
                target_name = rel.target_class

            relations.append(
                {
                    "source_class": rel.source_class,
                    "source_name": source_name,
                    "target_class": rel.target_class,
                    "target_name": target_name,
                    "relation_type": rel.relation_type,
                    "relation_name": rel.relation_name,
                    "description": rel.description,
                }
            )

    return relations
