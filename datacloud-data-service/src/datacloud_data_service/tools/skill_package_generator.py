"""SkillPackageGenerator: 生成 M5 Skills API 所需的技能包。"""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.ontology.loader import OntologyLoader

from datacloud_data_service.tools.registry import ToolRegistry


class SkillPackageGenerator:
    """从 OntologyLoader 生成技能包（含 tools + examples）。"""

    def __init__(self, loader: OntologyLoader) -> None:
        self._loader = loader

    def generate(
        self,
        view_id: str | None = None,
        object_ids: list[str] | None = None,
        tool_list_mode: str = "unified",
    ) -> dict[str, Any]:
        """生成技能包。

        - 若传 view_id：通过 loader.get_view(view_id) 获取 View，从 view.objects 提取 object_ids
        - 若传 object_ids：直接使用
        - 两者都未传时，使用全部 ontology 对象
        """
        view: Any = None
        resolved_object_ids: list[str]
        resolved_view_id: str
        resolved_view_name: str

        if view_id is not None:
            view = self._loader.get_view(view_id)
            resolved_object_ids = [obj.object_code for obj in view.objects]
            resolved_view_id = view_id
            resolved_view_name = view.view_name
        elif object_ids:
            resolved_object_ids = object_ids
            resolved_view_id = ""
            first_cls = self._loader.get_ontology_class(object_ids[0])
            resolved_view_name = first_cls.object_name
        else:
            resolved_object_ids = [c.object_code for c in self._loader.get_ontology_classes()]
            resolved_view_id = ""
            resolved_view_name = ""
            if resolved_object_ids:
                resolved_view_name = self._loader.get_ontology_class(
                    resolved_object_ids[0]
                ).object_name

        registry = ToolRegistry(self._loader)
        tools = registry.list_tools(
            object_ids=resolved_object_ids,
            tool_list_mode=tool_list_mode,
        )

        result_tools: list[dict[str, Any]] = []
        for t in tools:
            tool = dict(t)
            tool.pop("_meta", None)
            examples = self._build_examples(tool)
            tool["examples"] = examples
            result_tools.append(tool)

        return {
            "version": "1.0",
            "view_id": resolved_view_id,
            "view_name": resolved_view_name,
            "tools": result_tools,
        }

    def _build_examples(self, tool: dict[str, Any]) -> list[dict[str, Any]]:
        """为工具生成 examples 占位示例。"""
        name = tool.get("name", "")
        if name == "unified_data_query":
            return [{"question": "查询xxx"}]
        schema = tool.get("inputSchema", {})
        props = schema.get("properties", {})
        if not props:
            return []
        example = {k: "示例值" for k in props}
        return [example]
