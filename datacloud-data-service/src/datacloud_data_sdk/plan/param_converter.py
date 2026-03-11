"""参数转换：逻辑参数 -> 物理 API 请求体。"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.plan.models import ObjectViewFunctionParam


def _extract_physical_key(mapping_path: str) -> str:
    """从 mapping_path 提取物理 key。$.requestBody.userIds -> userIds"""
    if not mapping_path or not mapping_path.startswith("$."):
        return ""
    parts = mapping_path[2:].split(".")
    return parts[-1] if parts else ""


def map_to_physical(
    logical_params: dict[str, Any],
    in_params: list[ObjectViewFunctionParam],
) -> dict[str, Any]:
    """将逻辑参数转换为物理 API 请求体。

    遍历 in_params（direction=IN），从 logical_params 取 param_code 对应值，
    或使用 default_value；按 mapping_path 提取物理 key，写入结果 dict。
    """
    result: dict[str, Any] = {}
    for p in in_params:
        if p.direction != "IN":
            continue
        value = logical_params.get(p.param_code)
        if value is None and p.default_value is not None:
            value = p.default_value
        physical_key = _extract_physical_key(p.mapping_path) if p.mapping_path else p.param_code
        if physical_key and value is not None:
            result[physical_key] = value
    return result
