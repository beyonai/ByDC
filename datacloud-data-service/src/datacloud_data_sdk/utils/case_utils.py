"""camelCase 与 snake_case 互转工具。"""

from __future__ import annotations

import re
from typing import Any


def camel_to_snake(name: str) -> str:
    """canAnswer -> can_answer, sqlTemplate -> sql_template"""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_camel(name: str) -> str:
    """can_answer -> canAnswer, sql_template -> sqlTemplate"""
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def camel_to_snake_keys(
    d: dict | list | object,
    preserve_children: set[str] | None = None,
) -> dict | list | object:
    """递归转换 dict 的 key 从 camelCase 到 snake_case。

    preserve_children: 这些 key 对应的 dict 值不递归转换其子 key，用于 params 等
    需与 param_code 保持一致的字段（param_code 来自 ontology，可能为 camelCase）。
    """
    if isinstance(d, dict):
        result = {}
        for k, v in d.items():
            new_k = camel_to_snake(k)
            if preserve_children and new_k in preserve_children and isinstance(v, dict):
                result[new_k] = v
            else:
                result[new_k] = camel_to_snake_keys(
                    v, preserve_children=preserve_children
                )
        return result
    if isinstance(d, list):
        return [camel_to_snake_keys(i, preserve_children=preserve_children) for i in d]
    return d


def snake_to_camel_keys(d: dict | list | object) -> dict | list | object:
    """递归转换 dict 的 key 从 snake_case 到 camelCase。"""
    if isinstance(d, dict):
        return {snake_to_camel(k): snake_to_camel_keys(v) for k, v in d.items()}
    if isinstance(d, list):
        return [snake_to_camel_keys(i) for i in d]
    return d
