"""本体 OWL 渲染：对象、映射、数据源、视图、动作。"""

from __future__ import annotations

import json
from typing import Any

from datacloud_knowledge.owl_gen._xml import (
    map_data_type,
    map_measurement_unit,
    map_value_format,
    xml_escape,
)
from datacloud_knowledge.owl_gen.models import (
    OwlGenConfig,
    Table,
    TermBinding,
    ViewConfig,
)


def _build_binding_lookup(
    config: OwlGenConfig,
) -> dict[tuple[str, str], TermBinding]:
    return {(b.table_code, b.column_name): b for b in config.term_bindings}


def _field_role_json(
    config: OwlGenConfig,
    table_code: str,
    column_name: str,
    is_pk: bool,
) -> str:
    """返回 ext_property 内容：优先取 config.field_roles，无配置时向后兼容。"""
    role = config.field_roles.get((table_code, column_name))
    if role is not None:
        obj: dict[str, Any] = {
            "property_role_rule": {"property_role": role.property_role, "rule_type": role.rule_type}
        }
        if role.formula:
            obj["formula"] = role.formula
        return json.dumps(obj, ensure_ascii=False)
    # 向后兼容：未配置 field_roles 时保留原逻辑
    return "主键" if is_pk else ""


def _property_group_for_field(
    config: OwlGenConfig,
    table_code: str,
    column_name: str,
) -> str:
    """根据字段角色返回 property_group：formula 非空则为 COMPUTED，否则 STORAGE。"""
    role = config.field_roles.get((table_code, column_name))
    if role is not None and role.formula:
        return "COMPUTED"
    return "STORAGE"


# ── 对象定义 ──────────────────────────────────────────────────────────────────


def render_object(config: OwlGenConfig, table: Table) -> str:
    """对象定义 OWL（实体 + 字段）。"""
    binding_lookup = _build_binding_lookup(config)
    field_refs = "\n".join(
        f'        <fields rdf:resource="#{col.name}_field"/>' for col in table.columns
    )
    action_code = f"query_{table.code}"
    action_refs = json.dumps([action_code], ensure_ascii=False)
    relation_ids = [r.relation_id for r in config.object_relations if r.source_code == table.code]
    relation_refs = json.dumps(relation_ids, ensure_ascii=False)

    field_items: list[str] = []
    for col in table.columns:
        dtype = map_data_type(col.sql_type, col.name)
        binding = binding_lookup.get((table.code, col.name))
        term_path = f"{config.library_code}#{binding.term_type_code}" if binding else ""
        lib_code = config.library_code if binding else ""
        rel_term = "name" if binding else ""
        term_dt = binding.term_data_type if binding else ""
        ext_prop = _field_role_json(config, table.code, col.name, col.is_primary_key)
        prop_group = _property_group_for_field(config, table.code, col.name)
        field_items.append(
            f"""\
    <owl:NamedIndividual rdf:about="#{col.name}_field">
        <rdf:type rdf:resource="#EntityField"/>
        <property_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{col.name}</property_code>
        <property_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(col.comment or col.name)}</property_name>
        <data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{dtype}</data_type>
        <is_required rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">\
{str(not col.nullable).lower()}</is_required>
        <default_value rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
</default_value>
        <source_column rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{col.name}</source_column>
        <synonyms rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></synonyms>
        <data_format rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{map_value_format(col.sql_type)}</data_format>
        <measurement_unit rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{map_measurement_unit(col.comment)}</measurement_unit>
        <property_category rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
</property_category>
        <property_group rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{prop_group}</property_group>
        <ext_property rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{ext_prop}</ext_property>
        <term_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{term_path}</term_type_code_path>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{lib_code}</library_code>
        <rel_action rdf:datatype="http://www.w3.org/2001/XMLSchema#string">[]</rel_action>
        <rel_term_codeorname rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{rel_term}</rel_term_codeorname>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{term_dt}</term_data_type>
    </owl:NamedIndividual>"""
        )

    fields_body = "\n\n".join(field_items)
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/entity/ontology#">

    <owl:Class rdf:about="#EntityDefinition">\
<rdfs:label>实体定义</rdfs:label></owl:Class>
    <owl:Class rdf:about="#EntityField">\
<rdfs:label>实体字段</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#{table.code}_v1">
        <rdf:type rdf:resource="#EntityDefinition"/>
        <entity_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{table.code}</entity_code>
        <entity_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{table.name}</entity_name>
        <entity_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(table.desc)}</entity_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <entity_source rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
DB</entity_source>
{field_refs}
        <action_refs rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(action_refs)}</action_refs>
        <relations rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(relation_refs)}</relations>
    </owl:NamedIndividual>

{fields_body}

    <owl:DatatypeProperty rdf:about="#entity_code"/>
    <owl:DatatypeProperty rdf:about="#entity_name"/>
    <owl:DatatypeProperty rdf:about="#entity_desc"/>
    <owl:DatatypeProperty rdf:about="#version"/>
    <owl:DatatypeProperty rdf:about="#entity_source"/>
    <owl:DatatypeProperty rdf:about="#fields"/>
    <owl:DatatypeProperty rdf:about="#action_refs"/>
    <owl:DatatypeProperty rdf:about="#relations"/>
    <owl:DatatypeProperty rdf:about="#property_code"/>
    <owl:DatatypeProperty rdf:about="#property_name"/>
    <owl:DatatypeProperty rdf:about="#data_type"/>
    <owl:DatatypeProperty rdf:about="#is_required"/>
    <owl:DatatypeProperty rdf:about="#default_value"/>
    <owl:DatatypeProperty rdf:about="#source_column"/>
    <owl:DatatypeProperty rdf:about="#synonyms"/>
    <owl:DatatypeProperty rdf:about="#data_format"/>
    <owl:DatatypeProperty rdf:about="#measurement_unit"/>
    <owl:DatatypeProperty rdf:about="#property_category"/>
    <owl:DatatypeProperty rdf:about="#property_group"/>
    <owl:DatatypeProperty rdf:about="#ext_property"/>
    <owl:DatatypeProperty rdf:about="#term_type_code_path"/>
    <owl:DatatypeProperty rdf:about="#library_code"/>
    <owl:DatatypeProperty rdf:about="#rel_action"/>
    <owl:DatatypeProperty rdf:about="#rel_term_codeorname"/>
    <owl:DatatypeProperty rdf:about="#term_data_type"/>
</rdf:RDF>
"""


# ── 对象映射 ────────────────────────────────────────────────────────────────────


def render_mapping(config: OwlGenConfig, table: Table) -> str:
    """对象映射 OWL。"""
    mapping_refs = "\n".join(
        f'        <mapping rdf:resource="#{col.name}_mapping"/>' for col in table.columns
    )
    mapping_items: list[str] = []
    for col in table.columns:
        mapping_items.append(
            f"""\
    <owl:NamedIndividual rdf:about="#{col.name}_mapping">
        <rdf:type rdf:resource="#Mapping"/>
        <property_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{col.name}</property_code>
        <property_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(col.comment or col.name)}</property_name>
        <source_table_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{table.code}</source_table_code>
        <source_column_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{col.name}</source_column_code>
        <source_datasource_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.db_code}</source_datasource_code>
        <ext_property rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{_field_role_json(config, table.code, col.name, col.is_primary_key)}</ext_property>
    </owl:NamedIndividual>"""
        )
    body = "\n\n".join(mapping_items)
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/entity/mapping#">

    <owl:Class rdf:about="#EntityMapping">\
<rdfs:label>实体映射</rdfs:label></owl:Class>
    <owl:Class rdf:about="#Mapping">\
<rdfs:label>映射关系</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#{table.code}_mapping">
        <rdf:type rdf:resource="#EntityMapping"/>
        <entity_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{table.code}</entity_code>
        <entity_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{table.name}</entity_name>
        <entity_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(table.desc)}</entity_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
{mapping_refs}
    </owl:NamedIndividual>

{body}

    <owl:DatatypeProperty rdf:about="#entity_code"/>
    <owl:DatatypeProperty rdf:about="#entity_name"/>
    <owl:DatatypeProperty rdf:about="#entity_desc"/>
    <owl:DatatypeProperty rdf:about="#version"/>
    <owl:DatatypeProperty rdf:about="#mapping"/>
    <owl:DatatypeProperty rdf:about="#property_code"/>
    <owl:DatatypeProperty rdf:about="#property_name"/>
    <owl:DatatypeProperty rdf:about="#source_table_code"/>
    <owl:DatatypeProperty rdf:about="#source_column_code"/>
    <owl:DatatypeProperty rdf:about="#source_datasource_code"/>
    <owl:DatatypeProperty rdf:about="#ext_property"/>
</rdf:RDF>
"""


# ── 数据源 ───────────────────────────────────────────────────────────────────────


def render_dbsource(config: OwlGenConfig) -> str:
    """数据源定义 OWL。"""
    params = json.dumps(config.db_params, ensure_ascii=False)
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/dbsource/ontology#">

    <owl:Class rdf:about="#DatabaseDefinition">\
<rdfs:label>数据源定义</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#dbsource_{config.db_code}">
        <rdf:type rdf:resource="#DatabaseDefinition"/>
        <dbCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.db_code}</dbCode>
        <dbType rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.db_type}</dbType>
        <dbParams rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(params)}</dbParams>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#dbCode"/>
    <owl:DatatypeProperty rdf:about="#dbType"/>
    <owl:DatatypeProperty rdf:about="#dbParams"/>
</rdf:RDF>
"""


# ── 视图 ────────────────────────────────────────────────────────────────────────


def _view_relation_ids(config: OwlGenConfig, view: ViewConfig) -> list[str]:
    rel_ids = [f"rel_{view.view_code}_to_{obj_code}" for obj_code in view.object_codes]
    anchor = view.object_codes[0] if view.object_codes else ""
    for rel in config.object_relations:
        if rel.source_code == anchor and rel.target_code in view.object_codes:
            rel_ids.append(rel.relation_id)
    return rel_ids


def render_single_view(config: OwlGenConfig, view: ViewConfig) -> str:
    """单个视图定义 OWL。"""
    object_codes = json.dumps(view.object_codes, ensure_ascii=False)
    relations_json = json.dumps(_view_relation_ids(config, view), ensure_ascii=False)
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/scene/ontology#">

    <owl:Class rdf:about="#SceneDefinition">\
<rdfs:label>视图定义</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#{view.view_code}_v1">
        <rdf:type rdf:resource="#SceneDefinition"/>
        <view_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{view.view_code}</view_code>
        <view_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{view.view_name}</view_name>
        <description rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(view.view_desc)}</description>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <object_codes rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(object_codes)}</object_codes>
        <relations rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(relations_json)}</relations>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#view_code"/>
    <owl:DatatypeProperty rdf:about="#view_name"/>
    <owl:DatatypeProperty rdf:about="#description"/>
    <owl:DatatypeProperty rdf:about="#version"/>
    <owl:DatatypeProperty rdf:about="#object_codes"/>
    <owl:DatatypeProperty rdf:about="#relations"/>
</rdf:RDF>
"""


def render_view(config: OwlGenConfig) -> str:
    """兼容旧接口：聚合输出多个视图定义。"""
    views = config.resolved_views()
    if not views:
        return ""

    individuals: list[str] = []
    for view in views:
        object_codes = json.dumps(view.object_codes, ensure_ascii=False)
        relations_json = json.dumps(_view_relation_ids(config, view), ensure_ascii=False)
        individuals.append(f"""\
    <owl:NamedIndividual rdf:about="#{view.view_code}_v1">
        <rdf:type rdf:resource="#SceneDefinition"/>
        <view_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{view.view_code}</view_code>
        <view_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{view.view_name}</view_name>
        <description rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(view.view_desc)}</description>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <object_codes rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(object_codes)}</object_codes>
        <relations rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(relations_json)}</relations>
    </owl:NamedIndividual>""")

    body = "\n\n".join(individuals)
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/scene/ontology#">

    <owl:Class rdf:about="#SceneDefinition">\
<rdfs:label>视图定义</rdfs:label></owl:Class>

{body}

    <owl:DatatypeProperty rdf:about="#view_code"/>
    <owl:DatatypeProperty rdf:about="#view_name"/>
    <owl:DatatypeProperty rdf:about="#description"/>
    <owl:DatatypeProperty rdf:about="#version"/>
    <owl:DatatypeProperty rdf:about="#object_codes"/>
    <owl:DatatypeProperty rdf:about="#relations"/>
</rdf:RDF>
"""


# ── 视图映射 ──────────────────────────────────────────────────────────────────


def render_view_mapping(config: OwlGenConfig, view: ViewConfig | None = None) -> str:
    """视图映射 OWL（视图字段→对象字段）。"""
    if view is not None:
        mappings = view.field_mappings
        v_code = view.view_code
        v_name = view.view_name
        v_desc = view.view_desc
    else:
        # 向后兼容
        mappings = config.view_field_mappings
        v_code = config.view_code
        v_name = config.view_name
        v_desc = config.view_desc
    if not mappings:
        return ""

    mapping_refs = "\n".join(
        f'        <mapping rdf:resource="#{m.property_code}_mapping"/>' for m in mappings
    )
    mapping_items: list[str] = []
    for m in mappings:
        role_obj: dict[str, Any] = {
            "property_role_rule": {
                "property_role": m.role.property_role,
                "rule_type": m.role.rule_type,
            }
        }
        if m.role.formula:
            role_obj["formula"] = m.role.formula
        role_json = json.dumps(role_obj, ensure_ascii=False)
        mapping_items.append(
            f"""\
    <owl:NamedIndividual rdf:about="#{m.property_code}_mapping">
        <rdf:type rdf:resource="#Mapping"/>
        <property_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{m.property_code}</property_code>
        <property_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(m.property_name)}</property_name>
        <source_object_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{m.source_object_code}</source_object_code>
        <source_object_column_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{m.source_object_column_code}</source_object_column_code>
        <ext_property rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(role_json)}</ext_property>
    </owl:NamedIndividual>"""
        )
    body = "\n\n".join(mapping_items)
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/entity/mapping#">

    <owl:Class rdf:about="#EntityMapping">\
<rdfs:label>实体映射</rdfs:label></owl:Class>
    <owl:Class rdf:about="#Mapping">\
<rdfs:label>映射关系</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#{v_code}_mapping">
        <rdf:type rdf:resource="#EntityMapping"/>
        <entity_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{v_code}</entity_code>
        <entity_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(v_name)}</entity_name>
        <entity_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(v_desc)}</entity_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
{mapping_refs}
    </owl:NamedIndividual>

{body}

    <owl:DatatypeProperty rdf:about="#entity_code"/>
    <owl:DatatypeProperty rdf:about="#entity_name"/>
    <owl:DatatypeProperty rdf:about="#entity_desc"/>
    <owl:DatatypeProperty rdf:about="#version"/>
    <owl:ObjectProperty rdf:about="#mapping"/>
    <owl:DatatypeProperty rdf:about="#property_code"/>
    <owl:DatatypeProperty rdf:about="#property_name"/>
    <owl:DatatypeProperty rdf:about="#source_object_code"/>
    <owl:DatatypeProperty rdf:about="#source_object_column_code"/>
    <owl:DatatypeProperty rdf:about="#ext_property"/>
</rdf:RDF>
"""


# ── 动作定义 ──────────────────────────────────────────────────────────────────────


def render_actions(config: OwlGenConfig, tables: list[Table]) -> str:
    """动作定义 OWL。每个表生成一个查询动作。"""
    binding_lookup = _build_binding_lookup(config)
    action_items: list[str] = []
    param_items: list[str] = []

    for table in tables:
        action_code = f"query_{table.code}"
        req_refs: list[str] = []
        resp_refs: list[str] = []

        for col in table.columns:
            binding = binding_lookup.get((table.code, col.name))
            # 请求参数：主键 + 术语化字段
            if col.is_primary_key or binding:
                term_path = (
                    f"{config.library_code}#{binding.term_type_code}"
                    if binding
                    else f"OBJECT#{table.code}"
                )
                term_dt = binding.term_data_type if binding else "ONTOLOGY_TERM"
                rel_term = "name" if binding else col.name
                req_refs.append(
                    f'        <request_params rdf:resource="#param_{action_code}_{col.name}"/>'
                )
                param_items.append(
                    f"""\
    <owl:NamedIndividual rdf:about="#param_{action_code}_{col.name}">
        <rdf:type rdf:resource="#RequestParameter"/>
        <paramCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{col.name}</paramCode>
        <type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">string</type>
        <description rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(col.comment or col.name)}</description>
        <isRequired rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">\
false</isRequired>
        <term_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{term_path}</term_type_code_path>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.library_code}</library_code>
        <rel_term_codeorname rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{rel_term}</rel_term_codeorname>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{term_dt}</term_data_type>
    </owl:NamedIndividual>"""
                )
            # 响应参数：所有字段
            resp_refs.append(
                f'        <response_params rdf:resource="#resp_{action_code}_{col.name}"/>'
            )
            param_items.append(
                f"""\
    <owl:NamedIndividual rdf:about="#resp_{action_code}_{col.name}">
        <rdf:type rdf:resource="#ResponseParameter"/>
        <fieldCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{col.name}</fieldCode>
        <fieldType rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{map_data_type(col.sql_type, col.name).lower()}</fieldType>
        <term_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
OBJECT#{table.code}</term_type_code_path>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.library_code}</library_code>
        <object_property rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{col.name}</object_property>
        <json_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
data.{col.name}</json_path>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
ONTOLOGY_TERM</term_data_type>
    </owl:NamedIndividual>"""
            )

        action_items.append(
            f"""\
    <owl:NamedIndividual rdf:about="#action_{action_code}">
        <rdf:type rdf:resource="#ActionDefinition"/>
        <action_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{action_code}</action_code>
        <action_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
查询{table.name}</action_name>
        <action_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{table.name}查询动作</action_desc>
        <action_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
QUERY</action_type>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <function_refs rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(json.dumps([action_code], ensure_ascii=False))}</function_refs>
        <belong_entity rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(json.dumps([table.code], ensure_ascii=False))}</belong_entity>
        <request_url rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
/{action_code}</request_url>
        <request_method rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
POST</request_method>
        <request_header rdf:resource="#http_header"/>
{chr(10).join(req_refs)}
{chr(10).join(resp_refs)}
    </owl:NamedIndividual>"""
        )

    actions_body = "\n\n".join(action_items)
    params_body = "\n\n".join(param_items)
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/action/ontology#">

    <owl:Class rdf:about="#ActionDefinition">\
<rdfs:label>动作定义</rdfs:label></owl:Class>
    <owl:Class rdf:about="#RequestParameter">\
<rdfs:label>请求参数</rdfs:label></owl:Class>
    <owl:Class rdf:about="#ResponseParameter">\
<rdfs:label>响应参数</rdfs:label></owl:Class>
    <owl:Class rdf:about="#HeaderParameter">\
<rdfs:label>请求头参数</rdfs:label></owl:Class>

{actions_body}

{params_body}

    <owl:NamedIndividual rdf:about="#http_header">
        <rdf:type rdf:resource="#HeaderParameter"/>
        <name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
Content-Type</name>
        <value rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
application/json</value>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#action_code"/>
    <owl:DatatypeProperty rdf:about="#action_name"/>
    <owl:DatatypeProperty rdf:about="#action_desc"/>
    <owl:DatatypeProperty rdf:about="#action_type"/>
    <owl:DatatypeProperty rdf:about="#function_refs"/>
    <owl:DatatypeProperty rdf:about="#belong_entity"/>
    <owl:DatatypeProperty rdf:about="#request_url"/>
    <owl:DatatypeProperty rdf:about="#request_method"/>
    <owl:DatatypeProperty rdf:about="#request_header"/>
    <owl:DatatypeProperty rdf:about="#request_params"/>
    <owl:DatatypeProperty rdf:about="#response_params"/>
</rdf:RDF>
"""
