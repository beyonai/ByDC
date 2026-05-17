"""数据库 schema → OWL 生成配置自动推导器。

不从数据库元数据自动推导生成器配置，减少手工配置工作。

职责：
1. 从 INFORMATION_SCHEMA.COLUMNS 的 COLUMN_COMMENT 解析字段中文名和同义词
2. 按 column_name 聚合跨表的显示名与同义词（同名字段在不同表中可能有不同注释）
3. 按 (table_code, column_name) 产出 ObjectPropConfig（对象字段级配置）

依赖约束：
- 不直接连接数据库 — 通过 schema_reader.py 或 adapters 层获取 Table/Column 数据
- Phase 1 不读 FK 约束 — MANY_TO_ONE 仍需手工配置 ObjectRelation
- 零外部依赖 — 仅依赖项目内 models.py 的 Column/Table/ObjectPropConfig 类型

使用方式:
    from datacloud_knowledge.ingestion.owl_generate.schema_reader import read_tables
    from datacloud_knowledge.ingestion.owl_generate.schema_deriver import derive_from_schema

    tables = read_tables(config)
    derived = derive_from_schema(tables)
    # 合并到 OwlGenConfig:
    config.prop_display_names.update(derived["prop_display_names"])
    config.prop_synonyms.update(derived["prop_synonyms"])
    config.object_prop_configs.update(derived["object_prop_configs"])
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_knowledge.ingestion.owl_generate.models import (
    ObjectPropConfig,
    Table,
)

logger = logging.getLogger(__name__)

# 字段注释分隔符：中文分号、英文分号、竖线、顿号、逗号（按优先级）
_COMMENT_SEPARATORS = ("；", ";", "|", "、", "，")


def parse_column_comment(comment: str, column_name: str) -> tuple[str, list[str]]:
    """从字段注释中解析显示名与同义词。

    业务逻辑：
    - 数据库 COMMENT ON COLUMN 通常格式为 "显示名" 或 "显示名;同义词1;同义词2"
    - 第一段作为 display_name（字段的中文显示名）
    - 后续段作为 synonyms（同义词/别名，供检索使用）
    - 注释为空时返回空字符串和空列表

    解析规则：
    1. 按分隔符（中文分号、英文分号、竖线、顿号、逗号）拆分注释
    2. 第一段为 display_name，去除首尾空白
    3. 剩余段为 synonyms，去除空白和空字符串
    4. 若 display_name 与 column_name 完全相同，视为无有效名称

    Returns:
        (display_name, synonyms) — display_name 为字段中文名，synonyms 为同义词列表。
    """
    if not comment or not comment.strip():
        return "", []

    # 按分隔符拆分注释
    parts = _split_by_separators(comment.strip())
    if not parts:
        return "", []

    # 第一段为显示名，后续段为同义词
    display_name = parts[0].strip()
    synonyms = [p.strip() for p in parts[1:] if p.strip()]

    # 若显示名与字段编码完全一致，可能为无注释或注释不完整，降级为空
    if display_name == column_name:
        display_name = ""

    return display_name, synonyms


def _split_by_separators(text: str) -> list[str]:
    """按多个分隔符递归拆分文本。

    优先用中文分号拆分（避免误拆逗号分隔的数值），
    再进行英文分号、竖线、顿号、逗号的二次拆分。
    """
    for sep in _COMMENT_SEPARATORS:
        if sep in text:
            result: list[str] = []
            for segment in text.split(sep):
                result.extend(_split_by_separators(segment))
            return result
    return [text] if text.strip() else []


def derive_display_names(tables: list[Table]) -> dict[str, str]:
    """从多张表的字段注释中推导跨表通用显示名。

    推导规则：
    - 按 column_name 聚合：遍历所有表的同名字段注释
    - 取第一个非空的 display_name 作为该字段的通用显示名
    - 同名字段在不同表中的注释可能不同（如 by_customer.customer_name="客户名称"、
      by_project.customer_name="客户名"），首次遇到的注释作为默认显示名

    Args:
        tables: 从 schema_reader 读取的表列表。

    Returns:
        {column_name: display_name} 映射。
    """
    display_names: dict[str, str] = {}

    for table in tables:
        for col in table.columns:
            if display_names.get(col.name, ""):
                continue  # 已有显示名，跳过
            name, _synonyms = parse_column_comment(col.comment, col.name)
            if name:
                display_names[col.name] = name

    logger.info(
        "从 %d 张表中推导 %d 个字段显示名",
        len(tables),
        len(display_names),
    )
    return display_names


def derive_synonyms(tables: list[Table]) -> dict[str, list[str]]:
    """从多张表的字段注释中推导跨表同义词。

    推导规则：
    - 按 column_name 聚合：收集所有表中该字段注释的同义词部分
    - 去重但保留顺序（后出现的排后面）
    - 同时收集 display_name 作为同义词（同名字段在不同表中可能有不同名称）

    Args:
        tables: 从 schema_reader 读取的表列表。

    Returns:
        {column_name: [synonym_list]} 映射。
    """
    synonyms_map: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}

    for table in tables:
        for col in table.columns:
            display_name, synonyms = parse_column_comment(col.comment, col.name)

            if col.name not in seen:
                seen[col.name] = set()

            # 收集同义词
            for syn in synonyms:
                if syn not in seen[col.name] and syn != col.name:
                    seen[col.name].add(syn)
                    synonyms_map.setdefault(col.name, []).append(syn)

            # 若 display_name 与同名字段已有显示名不同，也作为同义词
            existing_display = _get_existing_display(tables, col.name, display_name)
            if display_name and existing_display and display_name != existing_display:
                if display_name not in seen[col.name] and display_name != col.name:
                    seen[col.name].add(display_name)
                    synonyms_map.setdefault(col.name, []).append(display_name)

    logger.info(
        "从 %d 张表中推导 %d 个字段的同义词",
        len(tables),
        len(synonyms_map),
    )
    return synonyms_map


def _get_existing_display(tables: list[Table], column_name: str, current_display: str) -> str:
    """查找 column_name 在已遍历的表中的第一个已知显示名。

    用于判断当前表的 display_name 是否与已知显示名不同，
    若不同则将其作为同义词添加。
    """
    for table in tables:
        for col in table.columns:
            if col.name == column_name:
                name, _synonyms = parse_column_comment(col.comment, col.name)
                if name and name != current_display:
                    return name
    return ""


def derive_prop_configs(
    tables: list[Table],
    *,
    display_names: dict[str, str] | None = None,
    synonyms_map: dict[str, list[str]] | None = None,
) -> dict[tuple[str, str], ObjectPropConfig]:
    """为每个 (table_code, column_name) 组合生成对象字段配置。

    业务逻辑：
    - 按 (table_code, column_name) 粒度生成 ObjectPropConfig
    - property_name 优先用此表此字段的 display_name，其次用跨表通用名
    - synonyms 合并此字段的局部同义词与跨表通用同义词
    - property_desc 使用原始注释文本

    Args:
        tables: 从 schema_reader 读取的表列表。
        display_names: 跨表通用显示名（由 derive_display_names 产出）。
        synonyms_map: 跨表通用同义词（由 derive_synonyms 产出）。

    Returns:
        {(table_code, column_name): ObjectPropConfig} 映射。
    """
    global_display = display_names or {}
    global_synonyms = synonyms_map or {}

    prop_configs: dict[tuple[str, str], ObjectPropConfig] = {}

    for table in tables:
        for col in table.columns:
            display_name, local_synonyms = parse_column_comment(col.comment, col.name)

            # property_name：优先局部显示名，其次全局显示名，否则用字段名
            property_name = display_name or global_display.get(col.name, col.name)

            # synonym 合并：去重
            all_synonyms: list[str] = list(local_synonyms)
            for syn in global_synonyms.get(col.name, []):
                if syn not in all_synonyms and syn != property_name:
                    all_synonyms.append(syn)

            # property_desc：使用原始注释
            property_desc = col.comment or f"字段：{col.name}"

            key = (table.code, col.name)
            prop_configs[key] = ObjectPropConfig(
                property_code=col.name,
                property_name=property_name,
                property_desc=property_desc,
                synonyms=all_synonyms,
            )

    logger.info(
        "从 %d 张表中推导 %d 个对象字段配置",
        len(tables),
        len(prop_configs),
    )
    return prop_configs


def derive_from_schema(tables: list[Table]) -> dict[str, Any]:
    """从数据库表结构一次性推导所有可自动生成的配置。

    产出三类配置，可直接 merge 到 OwlGenConfig：

    - prop_display_names: {column_name: display_name}
    - prop_synonyms: {column_name: [synonym, ...]}
    - object_prop_configs: {(table_code, column_name): ObjectPropConfig}

    这三类配置对应 OwlGenConfig 的同名字段，控制生成器
    的字段显示名、同义词和 prop 级别的业务语义。

    Args:
        tables: 从 schema_reader.read_tables() 读取的表列表。

    Returns:
        dict 包含 prop_display_names、prop_synonyms、object_prop_configs 三个 key。

    Example:
        >>> tables = read_tables(config)
        >>> derived = derive_from_schema(tables)
        >>> config.prop_display_names.update(derived["prop_display_names"])
        >>> config.prop_synonyms.update(derived["prop_synonyms"])
        >>> config.object_prop_configs.update(derived["object_prop_configs"])
    """
    if not tables:
        logger.warning("表列表为空，无法推导配置")
        return {
            "prop_display_names": {},
            "prop_synonyms": {},
            "object_prop_configs": {},
        }

    # Step 1: 推导跨表通用显示名（按 column_name 聚合）
    display_names = derive_display_names(tables)

    # Step 2: 推导跨表通用同义词（按 column_name 聚合）
    synonyms_map = derive_synonyms(tables)

    # Step 3: 推导对象字段级配置（按 (table_code, column_name) 粒度）
    prop_configs = derive_prop_configs(
        tables,
        display_names=display_names,
        synonyms_map=synonyms_map,
    )

    logger.info(
        "配置推导完成: %d 显示名, %d 同义词组, %d 对象字段配置",
        len(display_names),
        len(synonyms_map),
        len(prop_configs),
    )

    return {
        "prop_display_names": display_names,
        "prop_synonyms": synonyms_map,
        "object_prop_configs": prop_configs,
    }


__all__ = [
    "derive_display_names",
    "derive_from_schema",
    "derive_prop_configs",
    "derive_synonyms",
    "parse_column_comment",
]
