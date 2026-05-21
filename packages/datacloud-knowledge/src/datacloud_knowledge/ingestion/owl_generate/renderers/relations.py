"""关系 OWL 渲染 — 基于 GraphBuilder API。

迁移说明：
- rel_item() f-string 模板 → _build_relation_def() 构建 KPS RelationDef
- wrap_rel() XML 包装 → GraphBuilder.add_relations() + export_relations_graph() + serialize
- ext_field 从 JSON 字符串改为直接构建 dict
"""

from __future__ import annotations

import json
from typing import Any

from datacloud_knowledge.contracts.kps import RelationDef
from datacloud_knowledge.ingestion.owl_generate.graph_builder import GraphBuilder
from datacloud_knowledge.ingestion.owl_generate.models import OwlGenConfig, Table, ViewConfig

# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助：构建 KPS RelationDef
# ═══════════════════════════════════════════════════════════════════════════════


def _build_relation_def(
    config: OwlGenConfig,
    source_type: str,
    source_code: str,
    target_type: str,
    target_code: str,
    relation_name: str,
    relation_category: str,
    joinkeys: str = "[]",
    ext_field: str | dict[str, Any] | None = None,
) -> RelationDef:
    """从旧 rel_item() 参数构建 KPS RelationDef 对象。

    旧格式将 source/target 拆为 lib + type + code 三字段，
    KPS 统一为 {library}#{type}#{code} 合成 term_code。
    """
    # 合成 source/target term_code
    source_term = f"{config.library_code}#{source_type}#{source_code}"
    target_term = f"{config.library_code}#{target_type}#{target_code}"

    # 解析 joinkeys（旧格式为 JSON 压缩字符串）
    jk: tuple[dict[str, str], ...] = ()
    if joinkeys and joinkeys != "[]":
        try:
            parsed = json.loads(joinkeys)
            if isinstance(parsed, list):
                jk = tuple(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    # 解析 ext_field（旧格式为 JSON 字符串或已为 dict）
    ef: dict[str, Any] | None = None
    if ext_field is not None:
        if isinstance(ext_field, dict):
            ef = ext_field if ext_field else None
        elif ext_field:
            try:
                parsed = json.loads(ext_field)
                if isinstance(parsed, dict):
                    ef = parsed
            except (json.JSONDecodeError, ValueError):
                ef = {"raw": ext_field}

    return RelationDef(
        source_term_code=source_term,
        target_term_code=target_term,
        relation_name=relation_name,
        relation_category=relation_category,
        cardinality="",  # Phase 1: 不设置 cardinality，由导入端推断
        joinkeys=jk,
        ext_field=ef,
    )


def _serialize_relations_xml(builder: GraphBuilder) -> str:
    """将 GraphBuilder 中所有关系序列化为 XML 字符串。"""
    relations_graph = builder.export_relations_graph()
    result = relations_graph.serialize(format="xml")
    return result if isinstance(result, str) else result.decode("utf-8")


def _has_field_ext_field(field_alias: str, synonyms: list[str] | None = None) -> dict[str, Any]:
    """构建 HAS_FIELD 关系的 ext_field dict。"""
    data: dict[str, Any] = {"field_alias": field_alias}
    if synonyms:
        data["synonyms"] = synonyms
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# OWL 渲染（GraphBuilder API）
# ═══════════════════════════════════════════════════════════════════════════════


def render_relation_view(config: OwlGenConfig) -> str:
    """视图关系：对象归属视图（支持多视图）。"""
    relations: list[RelationDef] = []
    for v in config.resolved_views():
        for obj_code in v.object_codes:
            relations.append(
                _build_relation_def(
                    config,
                    source_type="view",
                    source_code=v.view_code,
                    target_type="object",
                    target_code=obj_code,
                    relation_name=f"{v.view_name}_包含_{config.table_names.get(obj_code, obj_code)}",
                    relation_category="HAS_OBJECT",
                )
            )
    if not relations:
        return ""
    builder = GraphBuilder()
    builder.add_relations(relations)
    return _serialize_relations_xml(builder)


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _rel_node(
    rel_id: str,
    library_code: str,
    source_type: str,
    source_code: str,
    target_type: str,
    target_code: str,
    relation_name: str,
    relation_type: str,
    joinkeys: str = "[]",
    ext_field: str = "",
) -> str:
    return f"""    <owl:NamedIndividual rdf:about="#{_xml_escape(rel_id)}">
        <rdf:type rdf:resource="#TermRelation"/>
        <source_libeary rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(library_code)}</source_libeary>
        <source_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(source_type)}</source_type>
        <source_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(source_code)}</source_code>
        <target_libeary rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(library_code)}</target_libeary>
        <target_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(target_type)}</target_type>
        <target_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(target_code)}</target_code>
        <relation_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(relation_name)}</relation_name>
        <relation_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(relation_type)}</relation_type>
        <joinkeys rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(joinkeys)}</joinkeys>
        <ext_field rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_escape(ext_field)}</ext_field>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""


_RELATIONS_FOOTER = """
    <owl:DatatypeProperty rdf:about="#source_libeary"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#source_type"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#source_code"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#target_libeary"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#target_type"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#target_code"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#relation_name"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#relation_type"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#joinkeys"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#ext_field"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
</rdf:RDF>"""


def render_view_relations_for_view(config: OwlGenConfig, view: ViewConfig) -> str:
    """渲染单个视图的关系 OWL（标准下划线格式，与门户标准完全对齐）。

    包含三类节点：
    - HAS_OBJECT：视图 → 每个关联对象
    - HAS_FIELD：视图 → 每个字段（ext_field 含 field_alias/synonyms）
    - MANY_TO_ONE：对象间 JOIN 关系（含 joinkeys）
    """
    lib = config.library_code
    view_name = view.view_name
    nodes: list[str] = []

    # HAS_OBJECT
    for obj_code in view.object_codes:
        obj_name = config.table_names.get(obj_code, obj_code)
        rel_id = f"rel_{view.view_code}_to_{obj_code}"
        nodes.append(
            _rel_node(
                rel_id=rel_id,
                library_code=lib,
                source_type="view",
                source_code=view.view_code,
                target_type="object",
                target_code=obj_code,
                relation_name=f"{view_name}_包含_{obj_name}",
                relation_type="HAS_OBJECT",
            )
        )

    # HAS_FIELD
    for mapping in view.field_mappings:
        alias = mapping.property_name or mapping.source_object_column_code
        synonyms = mapping.synonyms or []
        ext: dict[str, Any] = {"field_alias": alias}
        if synonyms:
            ext["synonyms"] = synonyms
        ext_field_str = json.dumps(ext, ensure_ascii=False)
        rel_id = f"rel_{view.view_code}_{mapping.property_code}"
        nodes.append(
            _rel_node(
                rel_id=rel_id,
                library_code=lib,
                source_type="view",
                source_code=view.view_code,
                target_type="prop",
                target_code=mapping.property_code,
                relation_name=f"{view_name}_拥有字段_{alias}",
                relation_type="HAS_FIELD",
                ext_field=ext_field_str,
            )
        )

    # MANY_TO_ONE（对象间 JOIN）
    obj_set = set(view.object_codes)
    for rel in config.object_relations:
        if rel.source_code not in obj_set or rel.target_code not in obj_set:
            continue
        jk = json.dumps(rel.join_keys, ensure_ascii=False, separators=(",", ":"))
        rel_id = f"rel_{rel.source_code}_to_{rel.target_code}"
        nodes.append(
            _rel_node(
                rel_id=rel_id,
                library_code=lib,
                source_type="object",
                source_code=rel.source_code,
                target_type="object",
                target_code=rel.target_code,
                relation_name=rel.relation_name,
                relation_type="MANY_TO_ONE",
                joinkeys=jk,
            )
        )

    if not nodes:
        return ""

    body = "\n".join(nodes)
    return f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/relation/ontology#">

    <owl:Class rdf:about="#TermRelation"><rdfs:label>术语关系</rdfs:label></owl:Class>

{body}
{_RELATIONS_FOOTER}"""


def render_relation_object(config: OwlGenConfig) -> str:
    """对象关系：对象之间的 JOIN 关系（MANY_TO_ONE）。"""
    relations: list[RelationDef] = []
    for rel in config.object_relations:
        jk = json.dumps(rel.join_keys, ensure_ascii=False, separators=(",", ":"))
        relations.append(
            _build_relation_def(
                config,
                source_type="object",
                source_code=rel.source_code,
                target_type="object",
                target_code=rel.target_code,
                relation_name=rel.relation_name,
                relation_category="MANY_TO_ONE",
                joinkeys=jk,
            )
        )
    if not relations:
        return ""
    builder = GraphBuilder()
    builder.add_relations(relations)
    return _serialize_relations_xml(builder)


def render_object_relations_for_object(config: OwlGenConfig, table_code: str) -> str:
    """渲染单个对象作为 source 的对象间关系（MANY_TO_ONE）。

    产物写入 {object_code}_object_relations.owl 文件。
    """
    relations: list[RelationDef] = []
    for rel in config.object_relations:
        if rel.source_code != table_code:
            continue
        jk = json.dumps(rel.join_keys, ensure_ascii=False, separators=(",", ":"))
        relations.append(
            _build_relation_def(
                config,
                source_type="object",
                source_code=rel.source_code,
                target_type="object",
                target_code=rel.target_code,
                relation_name=rel.relation_name,
                relation_category="MANY_TO_ONE",
                joinkeys=jk,
            )
        )
    if not relations:
        return ""
    builder = GraphBuilder()
    builder.add_relations(relations)
    return _serialize_relations_xml(builder)


def render_relation_attribute(config: OwlGenConfig, tables: list[Table]) -> str:
    """属性关系：对象拥有字段（HAS_FIELD），跨所有表。"""
    relations: list[RelationDef] = []
    for table in tables:
        for col in table.columns:
            resolved_prop = config.resolve_object_prop(
                table.code, col.name, col.comment or col.name
            )
            alias = resolved_prop.property_name
            syns = resolved_prop.synonyms or config.object_field_synonyms.get(
                (table.code, col.name), []
            )
            relations.append(
                _build_relation_def(
                    config,
                    source_type="object",
                    source_code=table.code,
                    target_type="prop",
                    target_code=resolved_prop.property_code,
                    relation_name=f"{table.name}_拥有字段_{alias}",
                    relation_category="HAS_FIELD",
                    ext_field=_has_field_ext_field(alias, syns),
                )
            )
    if not relations:
        return ""
    builder = GraphBuilder()
    builder.add_relations(relations)
    return _serialize_relations_xml(builder)


def render_attribute_relations_for_object(config: OwlGenConfig, table: Table) -> str:
    """渲染单个对象的字段关系（HAS_FIELD）。

    产物写入 {object_code}_attribute_relations.owl 文件。
    """
    relations: list[RelationDef] = []
    for col in table.columns:
        resolved_prop = config.resolve_object_prop(table.code, col.name, col.comment or col.name)
        alias = resolved_prop.property_name
        syns = resolved_prop.synonyms or config.object_field_synonyms.get(
            (table.code, col.name), []
        )
        relations.append(
            _build_relation_def(
                config,
                source_type="object",
                source_code=table.code,
                target_type="prop",
                target_code=resolved_prop.property_code,
                relation_name=f"{table.name}_拥有字段_{alias}",
                relation_category="HAS_FIELD",
                ext_field=_has_field_ext_field(alias, syns),
            )
        )
    if not relations:
        return ""
    builder = GraphBuilder()
    builder.add_relations(relations)
    return _serialize_relations_xml(builder)


def render_relation_action(config: OwlGenConfig, tables: list[Table]) -> str:
    """动作关系：对象拥有动作（HAS_ACTION）。"""
    relations: list[RelationDef] = []
    for table in tables:
        action_code = f"query_{table.code}"
        relations.append(
            _build_relation_def(
                config,
                source_type="object",
                source_code=table.code,
                target_type="action",
                target_code=action_code,
                relation_name=f"{table.name}拥有动作查询{table.name}",
                relation_category="HAS_ACTION",
            )
        )
    if not relations:
        return ""
    builder = GraphBuilder()
    builder.add_relations(relations)
    return _serialize_relations_xml(builder)


def render_relation_term(
    config: OwlGenConfig,
    term_values: dict[str, list[dict[str, str]]],
) -> dict[str, str]:
    """术语绑定关系（HAS_TERM: prop → type），按 term_type_code 拆文件。

    已废弃：不再迭代 term_values 生成逐条的 type→value HAS_TERM。
    改为 term_bindings 驱动的 prop→type 模式，由 generator._build_object_package() 负责。

    返回 ``{relative_path: content}``。
    """
    _ = term_values
    result: dict[str, str] = {}
    for binding in config.term_bindings:
        type_code = binding.term_type_code
        resolved_prop = config.resolve_object_prop(
            binding.table_code, binding.column_name, binding.column_name
        )
        prop_code = resolved_prop.property_code
        relations = [
            _build_relation_def(
                config,
                source_type="prop",
                source_code=prop_code,
                target_type=type_code,
                target_code=type_code,
                relation_name=f"{prop_code}绑定{type_code}",
                relation_category="HAS_TERM",
            )
        ]
        if relations:
            builder = GraphBuilder()
            builder.add_relations(relations)
            result[f"relations/relation_term_{type_code}.owl"] = _serialize_relations_xml(builder)
    return result


def render_term_relations_for_object(
    config: OwlGenConfig,
    table: Table,
    term_values: dict[str, list[dict[str, str]]],
) -> str:
    """渲染单个对象的术语绑定关系（HAS_TERM: prop → type）。

    产物写入 {object_code}_term_relations.owl 文件。
    term_values 参数保留用于兼容，但不再用于生成逐条 value 关系。
    """
    _ = term_values
    relations: list[RelationDef] = []
    for binding in config.term_bindings:
        if binding.table_code != table.code:
            continue
        type_code = binding.term_type_code
        resolved_prop = config.resolve_object_prop(
            binding.table_code, binding.column_name, binding.column_name
        )
        prop_code = resolved_prop.property_code
        relations.append(
            _build_relation_def(
                config,
                source_type="prop",
                source_code=prop_code,
                target_type=type_code,
                target_code=type_code,
                relation_name=f"{prop_code}绑定{type_code}",
                relation_category="HAS_TERM",
            )
        )
    if not relations:
        return ""
    builder = GraphBuilder()
    builder.add_relations(relations)
    return _serialize_relations_xml(builder)
