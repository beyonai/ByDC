"""关系 OWL 渲染（5 种关系文件）。"""

from __future__ import annotations

import json

from datacloud_knowledge.owl_gen._xml import rel_item, safe_xml_id, wrap_rel
from datacloud_knowledge.owl_gen.models import OwlGenConfig, Table


def render_relation_view(config: OwlGenConfig) -> str:
    """视图关系：对象归属视图（支持多视图）。"""
    items = []
    for v in config.resolved_views():
        for obj_code in v.object_codes:
            items.append(
                rel_item(
                    rel_id=f"rel_{v.view_code}_to_{obj_code}",
                    source_lib=config.library_code,
                    source_type="视图",
                    source_code=v.view_code,
                    target_lib=config.library_code,
                    target_type="对象",
                    target_code=obj_code,
                    rel_name=f"{v.view_name}包含{config.table_names.get(obj_code, obj_code)}",
                    rel_type="HAS_OBJECT",
                )
            )
    return wrap_rel(items)


def render_relation_object(config: OwlGenConfig) -> str:
    """对象关系：对象之间的 JOIN 关系。"""
    items = []
    for rel in config.object_relations:
        jk = json.dumps(rel.join_keys, ensure_ascii=False, separators=(",", ":"))
        items.append(
            rel_item(
                rel_id=rel.relation_id,
                source_lib=config.library_code,
                source_type="对象",
                source_code=rel.source_code,
                target_lib=config.library_code,
                target_type="对象",
                target_code=rel.target_code,
                rel_name=rel.relation_name,
                rel_type="MANY_TO_ONE",
                joinkeys=jk,
            )
        )
    return wrap_rel(items)


def render_relation_attribute(config: OwlGenConfig, tables: list[Table]) -> str:
    """属性关系：对象拥有字段。"""
    items = []
    for table in tables:
        for col in table.columns:
            items.append(
                rel_item(
                    rel_id=f"rel_{table.code}_{col.name}",
                    source_lib=config.library_code,
                    source_type="对象",
                    source_code=table.code,
                    target_lib=config.library_code,
                    target_type="属性",
                    target_code=col.name,
                    rel_name=f"{table.name}拥有字段{col.comment or col.name}",
                    rel_type="HAS_FIELD",
                )
            )
    return wrap_rel(items)


def render_relation_action(config: OwlGenConfig, tables: list[Table]) -> str:
    """动作关系：对象拥有动作。"""
    items = []
    for table in tables:
        action_code = f"query_{table.code}"
        items.append(
            rel_item(
                rel_id=f"rel_{table.code}_to_{action_code}",
                source_lib=config.library_code,
                source_type="对象",
                source_code=table.code,
                target_lib=config.library_code,
                target_type="动作",
                target_code=action_code,
                rel_name=f"{table.name}拥有动作查询{table.name}",
                rel_type="HAS_ACTION",
            )
        )
    return wrap_rel(items)


def render_relation_term(
    config: OwlGenConfig,
    term_values: dict[str, list[dict[str, str]]],
) -> dict[str, str]:
    """术语值关系，按 term_type_code 拆文件。

    返回 ``{relative_path: content}``。
    """
    result: dict[str, str] = {}
    for type_code, values in term_values.items():
        items: list[str] = []
        for entry in values:
            safe_code = safe_xml_id(entry["code"])
            items.append(
                rel_item(
                    rel_id=f"rel_term_{type_code}_{safe_code}",
                    source_lib=config.library_code,
                    source_type="术语类型",
                    source_code=type_code,
                    target_lib=config.library_code,
                    target_type="术语",
                    target_code=entry["code"],
                    rel_name=f"{type_code}包含{entry['name']}",
                    rel_type="HAS_TERM",
                )
            )
        if items:
            result[f"relations/relation_term_{type_code}.owl"] = wrap_rel(items)
    return result
