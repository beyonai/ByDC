"""虚拟动作注入：为 Loader 中 DB/KB 对象注入 query_{object_code} 虚拟动作。"""

from __future__ import annotations


def inject_virtual_actions(loader: object) -> None:
    """为 Loader 中 DB/KB 对象注入虚拟 query_{object_code} 动作。"""
    from datacloud_data_service.tools.dynamic_query_tool_generator import (
        DynamicQueryToolGenerator,
    )

    dyn_gen = DynamicQueryToolGenerator(loader)
    for cls in loader._classes.values():
        if cls.source_type in ("DB", "KNOWLEDGE_BASE"):
            virt = dyn_gen.generate_ontology_action(cls.object_code)
            if virt:
                cls.actions.append(virt)
