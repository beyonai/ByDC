"""按 mapping_path 从 API 响应提取 records。"""

from __future__ import annotations

from typing import Any


def _parse_mapping_path(mapping_path: str) -> tuple[list[str], str] | None:
    """解析 $.response.users[].userId -> (['response','users'], 'userId')。"""
    if not mapping_path or not mapping_path.startswith("$."):
        return None
    path = mapping_path[2:]
    if "[]" not in path:
        return None
    parts = path.split("[]", 1)
    array_path_str = parts[0].rstrip(".")
    field_part = parts[1].lstrip(".")
    if not array_path_str or not field_part:
        return None
    array_path = array_path_str.split(".")
    return (array_path, field_part)


def _get_nested(data: dict, path: list[str]) -> Any:
    """按路径取嵌套值。"""
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def extract_by_mapping_path(
    data: dict[str, Any],
    output_params: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    """按 mapping_path 从 API 响应提取 records。格式 $.response.users[].userId。"""
    if not output_params or not isinstance(data, dict):
        return []

    parsed = [_parse_mapping_path(mp) for _, mp in output_params]
    if not all(parsed):
        return []

    array_path = parsed[0][0]
    for p in parsed[1:]:
        if p[0] != array_path:
            return []

    arr = _get_nested(data, array_path)
    if not isinstance(arr, list):
        return []

    records: list[dict[str, Any]] = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        record: dict[str, Any] = {}
        for (param_code, mapping_path), p in zip(output_params, parsed):
            if p is None:
                continue
            _, field = p
            record[param_code] = item.get(field, "")
        records.append(record)
    return records
