"""参数转换：逻辑参数 -> 物理 API 请求体。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from datacloud_data_sdk.plan.models import ObjectViewFunctionParam

if TYPE_CHECKING:
    from datacloud_data_sdk.ontology.models import OntologyActionParam


def _extract_physical_key(mapping_path: str) -> str:
    """从 mapping_path 提取物理 key。$.requestBody.userIds -> userIds"""
    if not mapping_path or not mapping_path.startswith("$."):
        return ""
    parts = mapping_path[2:].split(".")
    return parts[-1] if parts else ""


def _to_function_param(p: "OntologyActionParam") -> ObjectViewFunctionParam:
    """将 OntologyActionParam 转为 ObjectViewFunctionParam（供 map_to_physical 使用）。"""
    return ObjectViewFunctionParam(
        param_code=p.param_code,
        param_name=p.param_name,
        param_type=p.param_type,
        direction=p.direction,
        required=p.required,
        mapping_path=p.mapping_path,
        default_value=p.default_value,
        term_set=p.term_set,
        term_type=p.term_type,
        term_field=p.term_field,
        dataset_id=p.dataset_id,
    )


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
        if p.direction not in ("IN", "INOUT"):
            continue
        value = logical_params.get(p.param_code)
        if value is None and p.default_value is not None:
            value = p.default_value
        physical_key = _extract_physical_key(p.mapping_path) if p.mapping_path else p.param_code
        if physical_key and value is not None:
            result[physical_key] = value
    return result
