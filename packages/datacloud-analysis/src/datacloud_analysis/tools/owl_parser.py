"""OWL解析器 - 从OWL文件生成动态工具。

解析OWL本体定义，为每个对象类型生成专用的查询工具和动作工具。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def parse_owl_files(scene_path: Path) -> dict[str, Any]:
    """解析OWL文件，提取本体定义。

    Args:
        scene_path: OWL场景目录路径

    Returns:
        本体定义字典，格式：
        {
            "objects": {
                "Order": {
                    "properties": ["id", "customer", "total", ...],
                    "actions": ["create", "cancel", ...]
                },
                ...
            }
        }
    """
    logger.info("parse_owl_files: parsing OWL from %s", scene_path)

    ontology = {"objects": {}}

    try:
        # 查找所有OWL文件
        owl_files = list(scene_path.glob("*.owl"))
        if not owl_files:
            logger.warning("parse_owl_files: no .owl files found in %s", scene_path)
            return ontology

        logger.info("parse_owl_files: found %d OWL files", len(owl_files))

        # 简化实现：从文件名推断对象类型
        # 实际应该使用rdflib等库解析OWL
        for owl_file in owl_files:
            object_name = owl_file.stem  # 文件名作为对象名

            # 读取OWL文件内容（简化处理）
            try:
                content = owl_file.read_text(encoding="utf-8")

                # 提取属性和动作（简化实现）
                # 实际应该解析OWL的ObjectProperty、DataProperty等
                properties = _extract_properties_from_owl(content)
                actions = _extract_actions_from_owl(content)

                ontology["objects"][object_name] = {
                    "properties": properties,
                    "actions": actions,
                }

                logger.info(
                    "parse_owl_files: parsed %s - %d properties, %d actions",
                    object_name,
                    len(properties),
                    len(actions),
                )

            except Exception as e:
                logger.error("parse_owl_files: failed to parse %s: %s", owl_file, e)
                continue

        return ontology

    except Exception as e:
        logger.error("parse_owl_files: failed to parse OWL files: %s", e)
        return ontology


def _extract_properties_from_owl(content: str) -> list[str]:
    """从OWL内容提取属性列表（简化实现）。"""
    # 简化实现：查找常见属性关键字
    properties = []

    # 查找DataProperty定义
    import re
    data_props = re.findall(r'<owl:DatatypeProperty[^>]*rdf:about="[^"]*#([^"]+)"', content)
    properties.extend(data_props)

    # 查找ObjectProperty定义
    obj_props = re.findall(r'<owl:ObjectProperty[^>]*rdf:about="[^"]*#([^"]+)"', content)
    properties.extend(obj_props)

    # 去重
    return list(set(properties)) if properties else ["id", "name", "description"]


def _extract_actions_from_owl(content: str) -> list[str]:
    """从OWL内容提取动作列表（简化实现）。"""
    # 简化实现：查找常见动作关键字
    actions = []

    # 查找动作定义（通常在注释或特定标签中）
    import re
    action_matches = re.findall(r'action["\s:]+([a-zA-Z_]+)', content, re.IGNORECASE)
    actions.extend(action_matches)

    # 如果没找到，返回默认动作
    return list(set(actions)) if actions else ["create", "update", "delete"]


def generate_tools_from_owl(
    scene_path: Path,
    mounted_objects: list[str] | None = None,
    auto_register: bool = True,
) -> list[Any]:
    """从OWL文件生成动态工具。

    Args:
        scene_path: OWL场景目录路径
        mounted_objects: 挂载的对象列表（如果为空，加载所有对象）
        auto_register: 是否自动注册工具

    Returns:
        LangChain工具列表
    """
    logger.info("generate_tools_from_owl: scene_path=%s objects=%s", scene_path, mounted_objects)

    # 解析OWL文件
    ontology = parse_owl_files(scene_path)
    objects = ontology.get("objects", {})

    if not objects:
        logger.warning("generate_tools_from_owl: no objects found in OWL files")
        return []

    # 过滤挂载的对象
    if mounted_objects:
        objects = {k: v for k, v in objects.items() if k in mounted_objects}
        logger.info("generate_tools_from_owl: filtered to %d mounted objects", len(objects))

    # 为每个对象生成工具
    tools = []

    for object_name, object_def in objects.items():
        properties = object_def.get("properties", [])
        actions = object_def.get("actions", [])

        # 1. 生成查询工具
        query_tool = _create_query_tool(object_name, properties)
        tools.append(query_tool)

        # 2. 为每个动作生成工具
        for action_name in actions:
            action_tool = _create_action_tool(object_name, action_name, properties)
            tools.append(action_tool)

        logger.info(
            "generate_tools_from_owl: created %d tools for %s",
            1 + len(actions),
            object_name,
        )

    logger.info("generate_tools_from_owl: generated %d tools total", len(tools))
    return tools


def _create_query_tool(object_name: str, properties: list[str]) -> Any:
    """为对象创建查询工具。"""
    tool_name = f"{object_name}_query"
    tool_description = f"查询{object_name}对象数据。可用字段: {', '.join(properties)}"

    @tool(name=tool_name, description=tool_description)
    def query_func(
        filters: str = "",
        fields: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询对象数据（通过统一接口）。"""
        from datacloud_analysis.tools.oql.query_objects import query_objects

        # 调用统一的query_objects工具
        return query_objects(
            object_type=object_name,
            filters=filters,
            fields=fields,
            limit=limit,
            offset=offset,
        )

    return query_func


def _create_action_tool(object_name: str, action_name: str, properties: list[str]) -> Any:
    """为对象的动作创建工具。"""
    tool_name = f"{object_name}_{action_name}"
    tool_description = f"对{object_name}对象执行{action_name}动作"

    @tool(name=tool_name, description=tool_description)
    def action_func(
        target_objects: str = "",
        payload: str = "",
    ) -> dict[str, Any]:
        """执行动作（通过统一接口）。"""
        from datacloud_analysis.tools.oql.execute_action import execute_action

        # 调用统一的execute_action工具
        return execute_action(
            action_type=f"{object_name}.{action_name}",
            target_objects=target_objects,
            payload=payload,
        )

    return action_func
