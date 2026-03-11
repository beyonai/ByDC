"""ParamMapper: 参数别名映射 + mapping_path 写入。"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.ontology.models import OntologyAction


class ParamMapper:
    """将用户传入的参数名（可能是别名）映射到标准 param_code。"""

    def __init__(self, action: OntologyAction) -> None:
        self._action = action
        self._alias_map = self._build_alias_map()

    def _build_alias_map(self) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        for p in self._action.params:
            alias_map[p.param_code] = p.param_code
            alias_map[p.param_name] = p.param_code
        return alias_map

    def map_names(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """将别名映射为标准 param_code。"""
        mapped: dict[str, Any] = {}
        for key, value in arguments.items():
            param_code = self._alias_map.get(key, key)
            mapped[param_code] = value
        return mapped

    def map_to_physical(self, params: dict[str, Any]) -> dict[str, Any]:
        """按 mapping_path 将参数写入对应位置（简化版直接透传）。"""
        return params
