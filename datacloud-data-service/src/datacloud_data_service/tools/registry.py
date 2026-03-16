"""ToolRegistry: 工具注册与列表生成。"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_service.tools.action_tool_generator import ActionToolGenerator


class ToolRegistry:
    """从 OntologyLoader 生成 MCP tools/list 响应。"""

    def __init__(self, loader: OntologyLoader) -> None:
        self._loader = loader
        self._action_gen = ActionToolGenerator(loader)

    def list_tools(
        self,
        view_id: str | None = None,
        object_ids: list[str] | None = None,
        tool_list_mode: str = "unified",
    ) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = [self._unified_query_tool()]

        target_ids = object_ids
        if not target_ids:
            target_ids = [c.object_code for c in self._loader.get_ontology_classes()]

        for oid in target_ids:
            for t in self._action_gen.generate_tools(oid):
                if tool_list_mode == "unified":
                    if t.get("_meta", {}).get("action_type") == "operation":
                        tools.append(t)
                else:
                    tools.append(t)

        return tools

    def _unified_query_tool(self) -> dict[str, Any]:
        return {
            "name": "unified_data_query",
            "title": "统一数据查询",
            "description": "通过自然语言查询数据，支持跨对象关联查询",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "自然语言查询问题"},
                    "view_id": {"type": "string", "description": "视图ID（可选）"},
                    "object_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "限定查询的对象ID列表（可选）",
                    },
                },
                "required": ["question"],
            },
        }
