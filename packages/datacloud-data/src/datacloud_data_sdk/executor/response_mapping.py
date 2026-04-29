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

    array_params = [
        (output_param, parsed_param)
        for output_param, parsed_param in zip(output_params, parsed)
        if parsed_param is not None and parsed_param[0] == "array"
    ]
    object_params = [
        (output_param, parsed_param)
        for output_param, parsed_param in zip(output_params, parsed)
        if parsed_param is not None and parsed_param[0] == "object"
    ]

    if array_params and object_params:
        return _extract_mixed_array_object_params(data, array_params, object_params)

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


def _extract_mixed_array_object_params(
    data: dict[str, Any],
    array_params: list[tuple[tuple[str, str], tuple[str, list[str], list[str]]]],
    object_params: list[tuple[tuple[str, str], tuple[str, list[str], list[str]]]],
) -> list[dict[str, Any]]:
    """提取数组明细字段，并将顶层对象字段补充到每条记录。"""
    array_path = array_params[0][1][1]
    for _output_param, parsed_param in array_params[1:]:
        if parsed_param[1] != array_path:
            return []

    arr = _get_nested(data, array_path)
    if not isinstance(arr, list):
        return []

    object_values: dict[str, Any] = {}
    for (param_code, _mapping_path), parsed_param in object_params:
        value = _get_nested(data, parsed_param[2])
        object_values[param_code] = "" if value is _MISSING else value

    records: list[dict[str, Any]] = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        record = dict(object_values)
        for (param_code, _mapping_path), parsed_param in array_params:
            value = _get_nested(item, parsed_param[2])
            record[param_code] = "" if value is _MISSING else value
        records.append(record)
    return records
