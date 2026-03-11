"""ActionToolGenerator: 从本体动作生成 MCP 工具定义。"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.action import PARAM_TYPE_MAP
from datacloud_data_sdk.ontology.loader import OntologyLoader


class ActionToolGenerator:
    """将 OntologyAction 转换为 MCP 工具定义。"""

    def __init__(self, loader: OntologyLoader) -> None:
        self._loader = loader

    def generate_tools(self, object_code: str) -> list[dict[str, Any]]:
        cls = self._loader.get_ontology_class(object_code)
        tools: list[dict[str, Any]] = []
        for action in cls.actions:
            in_params = [p for p in action.params if p.direction in ("IN", "INOUT")]
            properties: dict[str, Any] = {}
            required: list[str] = []
            for p in in_params:
                properties[p.param_code] = {
                    "type": PARAM_TYPE_MAP.get(p.param_type.upper(), "string"),
                    "description": p.param_name,
                }
                if p.required:
                    required.append(p.param_code)

            tool: dict[str, Any] = {
                "name": action.action_code,
                "description": action.description or action.action_name,
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                },
            }
            if required:
                tool["inputSchema"]["required"] = required

            tool["_meta"] = {"object_code": object_code}
            tools.append(tool)
        return tools
