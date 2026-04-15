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
        tools: list[dict[str, Any]] = []
        if tool_list_mode == "unified":
            tools.extend([self._unified_query_tool()])

        target_views: list[Any] = []
        if view_id:
            target_views = [self._loader.get_view(view_id)]
            target_ids = [obj.object_code for obj in target_views[0].objects]
        elif object_ids:
            target_ids = object_ids
        else:
            target_ids = [c.object_code for c in self._loader.get_ontology_classes()]
            target_views = self._loader.get_views()

        for view in target_views:
            self._append_view_tools(tools, view, tool_list_mode)

        for oid in target_ids:
            for t in self._action_gen.generate_tools(oid):
                if tool_list_mode == "unified":
                    if t.get("_meta", {}).get("action_type") == "operation":
                        tools.append(t)
                else:
                    tools.append(t)

        return tools

    def _append_view_tools(
        self,
        tools: list[dict[str, Any]],
        view: Any,
        tool_list_mode: str,
    ) -> None:
        for action in view.actions:
            exposure = getattr(action, "exposure_policy", "direct")
            if tool_list_mode == "unified" and exposure == "skill_only":
                continue
            if exposure == "hidden":
                continue
            if action.input_schema:
                tools.append(
                    {
                        "name": action.action_code,
                        "title": action.action_name,
                        "description": action.description,
                        "inputSchema": action.input_schema,
                        "_meta": {
                            "scope_type": "view",
                            "scope_code": view.view_id,
                            "action_family": getattr(action, "action_family", None),
                        },
                    }
                )

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
                    "knowledge_context": {
                        "type": "string",
                        "description": "知识增强上下文，会在生成查询计划时提供给模型（可选）",
                    },
                },
                "required": ["question"],
            },
        }
