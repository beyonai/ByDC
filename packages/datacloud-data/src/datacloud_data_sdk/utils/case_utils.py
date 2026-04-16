"""
命名风格转换工具模块

本模块提供 camelCase 与 snake_case 之间的转换功能。
用于处理 LLM 返回的 JSON 数据与 Python 代码之间的命名风格差异。

核心功能：
- 单个字符串的命名风格转换
- 字典键名的递归转换
- 支持保留特定子字段不转换

使用示例：
    snake_name = camel_to_snake("canAnswer")  # "can_answer"
    camel_name = snake_to_camel("can_answer")  # "canAnswer"
"""

from __future__ import annotations

import re


def camel_to_snake(name: str) -> str:
    """
    将 camelCase 转换为 snake_case

    Args:
        name: camelCase 格式的字符串

    Returns:
        str: snake_case 格式的字符串

    Example:
        camel_to_snake("canAnswer")  # "can_answer"
        camel_to_snake("sqlTemplate")  # "sql_template"
    """
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_camel(name: str) -> str:
    """
    将 snake_case 转换为 camelCase

    Args:
        name: snake_case 格式的字符串

    Returns:
        str: camelCase 格式的字符串

    Example:
        snake_to_camel("can_answer")  # "canAnswer"
        snake_to_camel("sql_template")  # "sqlTemplate"
    """
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def camel_to_snake_keys(
    d: dict | list | object,
    preserve_children: set[str] | None = None,
) -> dict | list | object:
    """
    递归转换字典键名从 camelCase 到 snake_case

    Args:
        d: 要转换的字典、列表或对象
        preserve_children: 需要保留子键不转换的键名集合

    Returns:
        转换后的数据结构

    Example:
        data = {"canAnswer": True, "sqlTemplate": "SELECT *"}
        result = camel_to_snake_keys(data)
        # {"can_answer": True, "sql_template": "SELECT *"}
    """
    if isinstance(d, dict):
        result = {}
        for k, v in d.items():
            new_k = camel_to_snake(k)
            if preserve_children and new_k in preserve_children and isinstance(v, dict):
                result[new_k] = v
            else:
                result[new_k] = camel_to_snake_keys(v, preserve_children=preserve_children)
        return result
    if isinstance(d, list):
        return [camel_to_snake_keys(i, preserve_children=preserve_children) for i in d]
    return d


def snake_to_camel_keys(d: dict | list | object) -> dict | list | object:
    """
    递归转换字典键名从 snake_case 到 camelCase

    Args:
        d: 要转换的字典、列表或对象

    Returns:
        转换后的数据结构

    Example:
        data = {"can_answer": True, "sql_template": "SELECT *"}
        result = snake_to_camel_keys(data)
        # {"canAnswer": True, "sqlTemplate": "SELECT *"}
    """
    if isinstance(d, dict):
        return {snake_to_camel(k): snake_to_camel_keys(v) for k, v in d.items()}
    if isinstance(d, list):
        return [snake_to_camel_keys(i) for i in d]
    return d
