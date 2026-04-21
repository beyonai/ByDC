"""关系 OWL 渲染（5 种关系文件）。"""

from __future__ import annotations

import json

from datacloud_knowledge.owl_gen._xml import rel_item, safe_xml_id, wrap_rel
from datacloud_knowledge.owl_gen.models import OwlGenConfig, Table, ViewConfig


def render_relation_view(config: OwlGenConfig) -> str:
    """视图关系：对象归属视图（支持多视图）。"""
    items = []
    for v in config.resolved_views():
        for obj_code in v.object_codes:
            items.append(
                rel_item(
                    rel_id=f"rel_{v.view_code}_to_{obj_code}",
                    source_lib=config.library_code,
                    source_type="view",
                    source_code=v.view_code,
                    target_lib=config.library_code,
                    target_type="object",
                    target_code=obj_code,
                    rel_name=f"{v.view_name}_包含_{config.table_names.get(obj_code, obj_code)}",
                    rel_type="HAS_OBJECT",
                )
            )
    return wrap_rel(items)


def render_view_relations_for_view(config: OwlGenConfig, view: ViewConfig) -> str:
    """渲染单个视图的关系：HAS_OBJECT + HAS_FIELD。"""
    items = []
    # HAS_OBJECT: 视图包含哪些对象
    for obj_code in view.object_codes:
        items.append(
            rel_item(
                rel_id=f"rel_{view.view_code}_to_{obj_code}",
                source_lib=config.library_code,
                source_type="view",
                source_code=view.view_code,
                target_lib=config.library_code,
                target_type="object",
                target_code=obj_code,
                rel_name=f"{view.view_name}_包含_{config.table_names.get(obj_code, obj_code)}",
                rel_type="HAS_OBJECT",
            )
        )
    # HAS_FIELD: 视图拥有的字段（带视图专属别名）
    for mapping in view.field_mappings:
        alias = mapping.property_name or mapping.source_object_column_code
        items.append(
            rel_item(
                rel_id=f"rel_{view.view_code}_{mapping.property_code}",
                source_lib=config.library_code,
                source_type="view",
                source_code=view.view_code,
                target_lib=config.library_code,
                target_type="prop",
                target_code=mapping.source_object_column_code,
                rel_name=f"{view.view_name}_拥有字段_{alias}",
                rel_type="HAS_FIELD",
                ext_field=_has_field_ext(alias, mapping.synonyms),
            )
        )
    return wrap_rel(items) if items else ""


def render_relation_object(config: OwlGenConfig) -> str:
    """对象关系：对象之间的 JOIN 关系。"""
    items = []
    for rel in config.object_relations:
        jk = json.dumps(rel.join_keys, ensure_ascii=False, separators=(",", ":"))
        items.append(
            rel_item(
                rel_id=rel.relation_id,
                source_lib=config.library_code,
                source_type="object",
                source_code=rel.source_code,
                target_lib=config.library_code,
                target_type="object",
                target_code=rel.target_code,
                rel_name=rel.relation_name,
                rel_type="MANY_TO_ONE",
                joinkeys=jk,
            )
        )
    return wrap_rel(items)


def render_object_relations_for_object(config: OwlGenConfig, table_code: str) -> str:
    """渲染单个对象作为 source 的对象间关系。"""
    items = []
    for rel in config.object_relations:
        if rel.source_code != table_code:
            continue
        jk = json.dumps(rel.join_keys, ensure_ascii=False, separators=(",", ":"))
        items.append(
            rel_item(
                rel_id=rel.relation_id,
                source_lib=config.library_code,
                source_type="object",
                source_code=rel.source_code,
                target_lib=config.library_code,
                target_type="object",
                target_code=rel.target_code,
                rel_name=rel.relation_name,
                rel_type="MANY_TO_ONE",
                joinkeys=jk,
            )
        )
    return wrap_rel(items) if items else ""


def render_relation_attribute(config: OwlGenConfig, tables: list[Table]) -> str:
    """属性关系：对象拥有字段。"""
    items = []
    for table in tables:
        for col in table.columns:
            alias = col.comment or col.name
            syns = config.object_field_synonyms.get((table.code, col.name), [])
            items.append(
                rel_item(
                    rel_id=f"rel_{table.code}_{col.name}",
                    source_lib=config.library_code,
                    source_type="object",
                    source_code=table.code,
                    target_lib=config.library_code,
                    target_type="prop",
                    target_code=col.name,
                    rel_name=f"{table.name}_拥有字段_{alias}",
                    rel_type="HAS_FIELD",
                    ext_field=_has_field_ext(alias, syns),
                )
            )
    return wrap_rel(items)


def _has_field_ext(field_alias: str, synonyms: list[str] | None = None) -> str:
    """构建 HAS_FIELD 关系的 ext_field JSON。"""
    data: dict[str, object] = {"field_alias": field_alias}
    if synonyms:
        data["synonyms"] = synonyms
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def render_attribute_relations_for_object(config: OwlGenConfig, table: Table) -> str:
    """渲染单个对象的字段关系。"""
    items = []
    for col in table.columns:
        alias = col.comment or col.name
        syns = config.object_field_synonyms.get((table.code, col.name), [])
        items.append(
            rel_item(
                rel_id=f"rel_{table.code}_{col.name}",
                source_lib=config.library_code,
                source_type="object",
                source_code=table.code,
                target_lib=config.library_code,
                target_type="prop",
                target_code=col.name,
                rel_name=f"{table.name}_拥有字段_{alias}",
                rel_type="HAS_FIELD",
                ext_field=_has_field_ext(alias, syns),
            )
        )
    return wrap_rel(items) if items else ""


def render_relation_action(config: OwlGenConfig, tables: list[Table]) -> str:
    """动作关系：对象拥有动作。"""
    items = []
    for table in tables:
        action_code = f"query_{table.code}"
        items.append(
            rel_item(
                rel_id=f"rel_{table.code}_to_{action_code}",
                source_lib=config.library_code,
                source_type="object",
                source_code=table.code,
                target_lib=config.library_code,
                target_type="action",
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
                    source_type=type_code,
                    source_code=type_code,
                    target_lib=config.library_code,
                    target_type=type_code,
                    target_code=entry["code"],
                    rel_name=f"{type_code}包含{entry['name']}",
                    rel_type="HAS_TERM",
                )
            )
        if items:
            result[f"relations/relation_term_{type_code}.owl"] = wrap_rel(items)
    return result


def render_term_relations_for_object(
    config: OwlGenConfig,
    table: Table,
    term_values: dict[str, list[dict[str, str]]],
) -> str:
    """渲染单个对象绑定字段的值术语关系。"""
    items: list[str] = []
    binding_lookup = {b.column_name: b for b in config.term_bindings if b.table_code == table.code}
    for binding in binding_lookup.values():
        type_code = binding.term_type_code
        for entry in term_values.get(type_code, []):
            safe_code = safe_xml_id(entry["code"])
            items.append(
                rel_item(
                    rel_id=f"rel_term_{table.code}_{type_code}_{safe_code}",
                    source_lib=config.library_code,
                    source_type=type_code,
                    source_code=type_code,
                    target_lib=config.library_code,
                    target_type=type_code,
                    target_code=entry["code"],
                    rel_name=f"{type_code}包含{entry['name']}",
                    rel_type="HAS_TERM",
                )
            )
    return wrap_rel(items) if items else ""
