"""按 mapping_path 从 API 响应提取 records。"""

from __future__ import annotations

from typing import Any

_MISSING = object()


def _parse_mapping_path(mapping_path: str) -> tuple[str, list[str], list[str]] | None:
    """解析对象/数组响应映射路径。"""
    if not mapping_path or not mapping_path.startswith("$."):
        return None

    path = mapping_path[2:]
    if not path:
        return None

    if "[]" not in path:
        field_path = [part for part in path.split(".") if part]
        if not field_path:
            return None
        return ("object", [], field_path)

    parts = path.split("[]")
    if len(parts) != 2:
        return None

    array_path_str, field_part = parts
    array_path = [part for part in array_path_str.rstrip(".").split(".") if part]
    field_path = [part for part in field_part.lstrip(".").split(".") if part]
    if not array_path or not field_path:
        return None
    return ("array", array_path, field_path)


def _get_nested(data: Any, path: list[str]) -> Any:
    """按路径取嵌套值。"""
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return _MISSING
        cur = cur[key]
    return cur


def extract_by_mapping_path(
    data: dict[str, Any],
    output_params: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    """按 mapping_path 从 API 响应提取 records。"""
    if not output_params or not isinstance(data, dict):
        return []

    parsed = [_parse_mapping_path(mp) for _, mp in output_params]
    if not all(parsed):
        return []

    mode = parsed[0][0]
    for p in parsed[1:]:
        if p[0] != mode:
            return []

    if mode == "object":
        record: dict[str, Any] = {}
        for (param_code, _mapping_path), p in zip(output_params, parsed):
            if p is None:
                continue
            value = _get_nested(data, p[2])
            record[param_code] = "" if value is _MISSING else value
        return [record] if record else []

    array_path = parsed[0][1]
    for p in parsed[1:]:
        if p[1] != array_path:
            return []

    arr = _get_nested(data, array_path)
    if not isinstance(arr, list):
        return []
    records: list[dict[str, Any]] = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        record: dict[str, Any] = {}
        for (param_code, _mapping_path), p in zip(output_params, parsed):
            if p is None:
                continue
            value = _get_nested(item, p[2])
            record[param_code] = "" if value is _MISSING else value
        records.append(record)
    return records
