from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from datacloud_analysis.tools.param_link_graph import ParamLinkGraph


@dataclass
class ScopeEntry:
    code: str
    scope_type: Literal["ONTOLOGY_BASE", "SCENE", "OBJECT", "VIEW"]
    base_id: str = ""
    # base_id 来源：数字员工配置 ontologyBaseCode（所属本体库 ID）
    # ONTOLOGY_BASE 类型：base_id == code
    # SCENE / OBJECT / VIEW 类型：base_id 来自 relResourceList[i].ontologyBaseCode


@dataclass
class RequestToolContext:
    allowed_scope: list[ScopeEntry]
    loader: Any                                         # OntologyLoader，按需加载
    tools_map: dict[str, Any] = field(default_factory=dict)
    object_to_tools: dict[str, list[str]] = field(default_factory=dict)
    anchor_mode: bool = False
    param_link_graph: Any = None
    # OntologyRelationGraph 不存入此处，"下一跳"关系直接查 term_relation 表

    @classmethod
    def build(
        cls,
        allowed_scope: list[ScopeEntry],
        loader: Any,
        tool_loader_cls: Any,
        threshold: int = 30,
    ) -> "RequestToolContext":
        """构建 RequestToolContext，确定 anchor_mode 并在 False 时预填充 tools_map。"""
        has_coarse = any(e.scope_type in ("ONTOLOGY_BASE", "SCENE") for e in allowed_scope)
        if has_coarse:
            return cls(allowed_scope=allowed_scope, loader=loader, anchor_mode=True)

        # 全为 OBJECT/VIEW：构建工具，按数量决定 anchor_mode
        tool_loader = tool_loader_cls(
            mounted_objects=[e.code for e in allowed_scope],
            loader=loader,
        )
        tools: dict[str, Any] = tool_loader.load()

        object_to_tools: dict[str, list[str]] = {}
        for tool_name, tool_obj in tools.items():
            obj_code = getattr(tool_obj, "_object_code", None) or ""
            object_to_tools.setdefault(obj_code, []).append(tool_name)

        anchor_mode = len(tools) > threshold
        if anchor_mode:
            return cls(
                allowed_scope=allowed_scope,
                loader=loader,
                object_to_tools=object_to_tools,
                anchor_mode=True,
            )

        # anchor_mode=False：预填充 tools_map，构建 ParamLinkGraph
        ctx = cls(
            allowed_scope=allowed_scope,
            loader=loader,
            tools_map=tools,
            object_to_tools=object_to_tools,
            anchor_mode=False,
        )
        plg = ParamLinkGraph()
        plg.build(ctx.tools_map, loader)
        ctx.param_link_graph = plg
        return ctx

    def is_object_allowed(
        self,
        object_code: str,
        scene_id: str | None,
        library_id: str | None,
    ) -> bool:
        """三级权限校验：OBJECT 精确匹配 → SCENE → ONTOLOGY_BASE。"""
        for entry in self.allowed_scope:
            if entry.scope_type == "OBJECT" and entry.code == object_code:
                return True
            if entry.scope_type == "SCENE" and scene_id and entry.code == scene_id:
                return True
            if entry.scope_type == "ONTOLOGY_BASE" and library_id and entry.code == library_id:
                return True
        return False
