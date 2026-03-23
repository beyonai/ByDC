"""ActionToolGenerator: 从本体动作生成 MCP 工具定义。"""

from __future__ import annotations

from typing import Any

from datacloud_data.action import Action
from datacloud_data.ontology.loader import OntologyLoader


class ActionToolGenerator:
    """将 OntologyAction 转换为 MCP 工具定义，统一通过 Action.get_schema() 获取 schema。"""

    def __init__(self, loader: OntologyLoader) -> None:
        self._loader = loader

    def generate_tools(self, object_code: str) -> list[dict[str, Any]]:
        cls = self._loader.get_ontology_class(object_code)
        tools: list[dict[str, Any]] = []
        for action in cls.actions:
            schema = Action(action, loader=self._loader).get_schema()
            tool: dict[str, Any] = {
                "name": schema["name"],
                "title": schema.get("title", schema["name"]),
                "description": schema.get("description", ""),
                "inputSchema": schema["inputSchema"],
            }
            tool["_meta"] = {"object_code": object_code, "action_type": action.action_type}
            tools.append(tool)
        return tools
