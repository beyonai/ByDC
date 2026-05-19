"""本体 OWL 渲染：对象、映射、数据源、视图 — 基于 GraphBuilder API。

迁移说明：
- 定义级实体（EntityDefinition/EntityField/SceneDefinition 等）非 KPS，保留在
  GraphBuilder 中作为独立方法，通过 rdflib Graph API 序列化产出标准 RDF/XML。
- 业务逻辑辅助函数（binding lookup、field role、term meta 等）不变。
- 旧 f-string 模板替换为 GraphBuilder.add_*() + build().serialize()。
"""

from __future__ import annotations

import json
from typing import Any

from datacloud_knowledge.ingestion.owl_generate._xml import (
    map_data_type,
    map_measurement_unit,
    map_value_format,
)
from datacloud_knowledge.ingestion.owl_generate.graph_builder import GraphBuilder
from datacloud_knowledge.ingestion.owl_generate.models import (
    OwlGenConfig,
    Table,
    TermBinding,
    ViewConfig,
    ViewFieldMapping,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 业务逻辑辅助函数（不变）
# ═══════════════════════════════════════════════════════════════════════════════


def _build_binding_lookup(
    config: OwlGenConfig,
) -> dict[tuple[str, str], TermBinding]:
    return {(b.table_code, b.column_name): b for b in config.term_bindings}


def _term_data_type_for_term_type(config: OwlGenConfig, term_type_code: str) -> str:
    for binding in config.term_bindings:
        if binding.term_type_code == term_type_code:
            return binding.term_data_type
    return ""


def _empty_term_meta() -> dict[str, str]:
    return {
        "termTypeCodePath": "",
        "libraryCode": "",
        "relTermCodeorname": "",
        "termDataType": "",
        "relAction": "[]",
    }


def _term_meta_for_alias(
    config: OwlGenConfig, term_type_code: str, rel_term_codeorname: str
) -> dict[str, str]:
    term_data_type = _term_data_type_for_term_type(config, term_type_code)
    if not term_data_type:
        return _empty_term_meta()
    return {
        "termTypeCodePath": f"{config.library_code}#{term_type_code}",
        "libraryCode": config.library_code,
        "relTermCodeorname": rel_term_codeorname,
        "termDataType": term_data_type,
        "relAction": "[]",
    }


def _rel_term_codeorname_for_binding(config: OwlGenConfig, binding: TermBinding) -> str:
    if binding.term_type_code in config.name_term_type_codes or binding.column_name.endswith(
        "_name"
    ):
        return "name"
    return "code"


def _term_meta_for_object_field(
    config: OwlGenConfig,
    table_code: str,
    column_name: str,
    binding_lookup: dict[tuple[str, str], TermBinding],
) -> dict[str, str]:
    identity_alias = config.object_identity_term_aliases.get((table_code, column_name))
    if identity_alias is not None:
        term_type_code, rel_term_codeorname = identity_alias
        return _term_meta_for_alias(config, term_type_code, rel_term_codeorname)

    property_alias = config.object_property_term_aliases.get((table_code, column_name))
    if property_alias is not None:
        return _term_meta_for_alias(config, property_alias, "code")

    binding = binding_lookup.get((table_code, column_name))
    if binding is None:
        return _empty_term_meta()

    meta = _empty_term_meta()
    meta["termTypeCodePath"] = f"{config.library_code}#{binding.term_type_code}"
    meta["libraryCode"] = config.library_code
    meta["relTermCodeorname"] = _rel_term_codeorname_for_binding(config, binding)
    meta["termDataType"] = binding.term_data_type
    return meta


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
    return "主键" if is_pk else ""


def _property_group_for_field(
    config: OwlGenConfig,
    table_code: str,
    column_name: str,
) -> str:
    """根据字段角色返回 property_group。"""
    role = config.field_roles.get((table_code, column_name))
    if role is not None and role.formula:
        return "COMPUTED"
    return "STORAGE"


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助：实体字段构建（旧 _xml 参数 → dict props）
# ═══════════════════════════════════════════════════════════════════════════════


def _build_entity_field_props(
    config: OwlGenConfig,
    table_code: str,
    col: Any,  # Column
    resolved_prop: Any,  # ResolvedObjectProp
    term_meta: dict[str, str],
) -> dict[str, str]:
    """构建 EntityField 属性字典，用于 GraphBuilder.add_entity_field()。"""
    dtype = map_data_type(col.sql_type, col.name)
    ext_prop = _field_role_json(config, table_code, col.name, col.is_primary_key)
    prop_group = _property_group_for_field(config, table_code, col.name)
    return {
        "propertyCode": resolved_prop.property_code,
        "propertyName": resolved_prop.property_name,
        "dataType": dtype,
        "isRequired": str(not col.nullable).lower(),
        "defaultValue": "",
        "sourceColumn": col.name,
        "synonyms": "",
        "dataFormat": map_value_format(col.sql_type),
        "measurementUnit": map_measurement_unit(col.comment or ""),
        "propertyCategory": "",
        "propertyGroup": prop_group,
        "extProperty": ext_prop,
        "termTypeCodePath": term_meta.get("termTypeCodePath", ""),
        "libraryCode": term_meta.get("libraryCode", ""),
        "relAction": term_meta.get("relAction", "[]"),
        "relTermCodeorname": term_meta.get("relTermCodeorname", ""),
        "termDataType": term_meta.get("termDataType", ""),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助：序列化
# ═══════════════════════════════════════════════════════════════════════════════


def _serialize_xml(builder: GraphBuilder) -> str:
    """将 GraphBuilder 的图序列化为 XML 字符串。"""
    result = builder.build().serialize(format="xml")
    return result if isinstance(result, str) else result.decode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# 对象定义（_definition.owl）
# ═══════════════════════════════════════════════════════════════════════════════


def _camel_to_snake(name: str) -> str:
    """驼峰转下划线，如 propertyCode → property_code。"""
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def _xml_str(value: str) -> str:
    """转义 XML 特殊字符。"""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _render_field_xml(field_id: str, props: dict[str, str]) -> str:
    """生成单个 EntityField 的 owl:NamedIndividual XML 片段。"""
    lines = [
        f'    <owl:NamedIndividual rdf:about="#{field_id}">',
        f'        <rdf:type rdf:resource="#EntityField"/>',
    ]
    for key, val in props.items():
        tag = _camel_to_snake(key)
        lines.append(
            f'        <{tag} rdf:datatype="http://www.w3.org/2001/XMLSchema#string">'
            f'{_xml_str(val)}</{tag}>'
        )
    lines.append("    </owl:NamedIndividual>")
    return "\n".join(lines)


def render_object(config: OwlGenConfig, table: Table) -> str:
    """对象定义 OWL（EntityDefinition + EntityField）— 直接生成标准格式 XML。"""
    binding_lookup = _build_binding_lookup(config)
    resolved_props = {
        col.name: config.resolve_object_prop(table.code, col.name, col.comment or col.name)
        for col in table.columns
    }

    action_code = f"query_{table.code}"
    action_refs = json.dumps([action_code], ensure_ascii=False)
    relation_ids = [r.relation_id for r in config.object_relations if r.source_code == table.code]
    relation_refs = json.dumps(relation_ids, ensure_ascii=False)

    # 生成字段 XML 片段
    field_xml_parts: list[str] = []
    field_refs_xml: list[str] = []
    for col in table.columns:
        resolved_prop = resolved_props[col.name]
        term_meta = _term_meta_for_object_field(config, table.code, col.name, binding_lookup)
        field_props = _build_entity_field_props(config, table.code, col, resolved_prop, term_meta)
        field_id = f"{resolved_prop.property_code}_field"
        field_xml_parts.append(_render_field_xml(field_id, field_props))
        field_refs_xml.append(f'        <fields rdf:resource="#{field_id}"/>')

    fields_block = "\n".join(field_refs_xml)
    fields_xml = "\n\n".join(field_xml_parts)

    return f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/entity/ontology#">

    <owl:Class rdf:about="#EntityDefinition"><rdfs:label>实体定义</rdfs:label></owl:Class>
    <owl:Class rdf:about="#EntityField"><rdfs:label>实体字段</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#{table.code}_v1">
        <rdf:type rdf:resource="#EntityDefinition"/>
        <entity_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_str(table.code)}</entity_code>
        <entity_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_str(table.name)}</entity_name>
        <entity_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_str(table.desc or "")}</entity_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <entity_source rdf:datatype="http://www.w3.org/2001/XMLSchema#string">DB</entity_source>
{fields_block}
        <action_refs rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_str(action_refs)}</action_refs>
        <relations rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_str(relation_refs)}</relations>
    </owl:NamedIndividual>

{fields_xml}

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


# ═══════════════════════════════════════════════════════════════════════════════
# 对象映射（_mapping.owl）
# ═══════════════════════════════════════════════════════════════════════════════


def render_mapping(config: OwlGenConfig, table: Table) -> str:
    """对象映射 OWL（EntityMapping + Mapping）— GraphBuilder API。

    业务逻辑：为每个数据库表生成 EntityMapping（表级映射容器）
    + 每个字段的 Mapping（字段→表列映射）。
    产物写入 {object_code}_mapping.owl 文件。
    """
    resolved_props = {
        col.name: config.resolve_object_prop(table.code, col.name, col.comment or col.name)
        for col in table.columns
    }

    # 构建映射引用 ID 列表
    mapping_ref_ids = [f"{resolved_props[col.name].property_code}_mapping" for col in table.columns]

    builder = GraphBuilder()
    builder.add_entity_mapping(
        object_code=table.code,
        object_name=table.name,
        object_desc=table.desc,
        mapping_refs=mapping_ref_ids,
    )

    for col in table.columns:
        resolved_prop = resolved_props[col.name]
        ext_prop = _field_role_json(config, table.code, col.name, col.is_primary_key)
        builder.add_field_mapping(
            {
                "propertyCode": resolved_prop.property_code,
                "propertyName": resolved_prop.property_name,
                "sourceTableCode": table.code,
                "sourceColumnCode": col.name,
                "sourceDatasourceCode": config.db_code,
                "extProperty": ext_prop,
            }
        )

    return _serialize_xml(builder)


# ═══════════════════════════════════════════════════════════════════════════════
# 数据源（_dbsource.owl）
# ═══════════════════════════════════════════════════════════════════════════════


def render_dbsource(config: OwlGenConfig) -> str:
    """数据源定义 OWL（DatabaseDefinition）— 直接生成标准格式 XML。"""
    db_params = json.dumps(
        {**config.db_params, "connector_type": "BYCLAW_SQL_EXECUTE"},
        ensure_ascii=False,
    )
    return f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/dbsource/ontology#">

    <owl:Class rdf:about="#DatabaseDefinition"><rdfs:label>数据源定义</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#dbsource_{_xml_str(config.db_code)}">
        <rdf:type rdf:resource="#DatabaseDefinition"/>
        <dbCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_str(config.db_code)}</dbCode>
        <dbType rdf:datatype="http://www.w3.org/2001/XMLSchema#string">SQLITE</dbType>
        <dbParams rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{_xml_str(db_params)}</dbParams>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#dbCode"/>
    <owl:DatatypeProperty rdf:about="#dbType"/>
    <owl:DatatypeProperty rdf:about="#dbParams"/>
</rdf:RDF>
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 视图定义（_definition.owl）
# ═══════════════════════════════════════════════════════════════════════════════


def _view_relation_ids(config: OwlGenConfig, view: ViewConfig) -> list[str]:
    """计算视图的关系 ID 列表。"""
    rel_ids = [f"rel_{view.view_code}_to_{obj_code}" for obj_code in view.object_codes]
    anchor = view.object_codes[0] if view.object_codes else ""
    for rel in config.object_relations:
        if rel.source_code == anchor and rel.target_code in view.object_codes:
            rel_ids.append(rel.relation_id)
    return rel_ids


def _view_field_role_json(m: ViewFieldMapping) -> str:
    """返回视图字段的 ext_property JSON。"""
    obj: dict[str, Any] = {
        "property_role_rule": {
            "property_role": m.role.property_role,
            "rule_type": m.role.rule_type,
        }
    }
    if m.role.formula:
        obj["formula"] = m.role.formula
    return json.dumps(obj, ensure_ascii=False)


def _build_scene_field_props(m: ViewFieldMapping) -> dict[str, str]:
    """构建 SceneField 属性字典，用于 GraphBuilder.add_scene_field()。"""
    ext_prop = _view_field_role_json(m)
    synonyms_str = json.dumps(m.synonyms, ensure_ascii=False) if m.synonyms else ""
    return {
        "propertyCode": m.property_code,
        "propertyName": m.property_name,
        "sourceObjectCode": m.source_object_code,
        "sourceObjectColumnCode": m.source_object_column_code,
        "synonyms": synonyms_str,
        "extProperty": ext_prop,
    }


def render_single_view(config: OwlGenConfig, view: ViewConfig) -> str:
    """单个视图定义 OWL（SceneDefinition + SceneField）— GraphBuilder API。

    业务逻辑：为每个视图配置生成 SceneDefinition（含 object_codes、relations、
    字段引用）+ 每个字段映射的 SceneField（含源对象/字段、同义词、角色）。
    产物写入 {view_code}_definition.owl 文件。
    """
    object_codes_json = json.dumps(view.object_codes, ensure_ascii=False)
    relations_json = json.dumps(_view_relation_ids(config, view), ensure_ascii=False)

    # 字段引用 ID 列表
    field_ref_ids = [f"{m.property_code}_field" for m in view.field_mappings]

    builder = GraphBuilder()
    builder.add_scene_definition(
        view_code=view.view_code,
        view_name=view.view_name,
        view_desc=view.view_desc,
        object_codes_json=object_codes_json,
        relations_json=relations_json,
        field_refs=field_ref_ids,
    )

    for m in view.field_mappings:
        builder.add_scene_field(_build_scene_field_props(m))

    return _serialize_xml(builder)


# ═══════════════════════════════════════════════════════════════════════════════
# 兼容旧接口（生成器未使用，保留供后续迁移）
# ═══════════════════════════════════════════════════════════════════════════════


def render_view(config: OwlGenConfig) -> str:
    """兼容旧接口：聚合输出多个视图定义。"""
    views = config.resolved_views()
    if not views:
        return ""

    builder = GraphBuilder()
    for view in views:
        object_codes_json = json.dumps(view.object_codes, ensure_ascii=False)
        relations_json = json.dumps(_view_relation_ids(config, view), ensure_ascii=False)
        field_ref_ids = [f"{m.property_code}_field" for m in view.field_mappings]
        builder.add_scene_definition(
            view_code=view.view_code,
            view_name=view.view_name,
            view_desc=view.view_desc,
            object_codes_json=object_codes_json,
            relations_json=relations_json,
            field_refs=field_ref_ids,
        )
        for m in view.field_mappings:
            builder.add_scene_field(_build_scene_field_props(m))

    return _serialize_xml(builder)


def render_view_mapping(config: OwlGenConfig, view: ViewConfig | None = None) -> str:
    """视图映射 OWL（视图字段→对象字段）— GraphBuilder API。

    兼容旧接口：支持单 view 参数或回退到 config.view_* 字段。
    """
    if view is not None:
        mappings = view.field_mappings
        v_code = view.view_code
        v_name = view.view_name
        v_desc = view.view_desc
    else:
        mappings = config.view_field_mappings
        v_code = config.view_code
        v_name = config.view_name
        v_desc = config.view_desc
    if not mappings:
        return ""

    mapping_ref_ids = [f"{m.property_code}_mapping" for m in mappings]

    builder = GraphBuilder()
    builder.add_entity_mapping(
        object_code=v_code,
        object_name=v_name,
        object_desc=v_desc,
        mapping_refs=mapping_ref_ids,
    )

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
        builder.add_field_mapping(
            {
                "propertyCode": m.property_code,
                "propertyName": m.property_name,
                "sourceTableCode": m.source_object_code,
                "sourceColumnCode": m.source_object_column_code,
                "sourceDatasourceCode": "",
                "extProperty": role_json,
            }
        )

    return _serialize_xml(builder)


def render_actions(config: OwlGenConfig, tables: list[Table]) -> str:
    """动作定义 OWL — 兼容旧接口。

    注意：此函数已被 actions.py + GraphBuilder.add_actions() 替代。
    保留仅为向后兼容。
    """
    binding_lookup = _build_binding_lookup(config)
    actions: list[dict[str, Any]] = []
    all_params: list[dict[str, str]] = []

    for table in tables:
        action_code = f"query_{table.code}"
        req_ref_ids: list[str] = []
        resp_ref_ids: list[str] = []

        for col in table.columns:
            binding = binding_lookup.get((table.code, col.name))
            if col.is_primary_key or binding:
                term_path = (
                    f"{config.library_code}#{binding.term_type_code}"
                    if binding
                    else f"OBJECT#{table.code}"
                )
                term_dt = binding.term_data_type if binding else "ONTOLOGY_TERM"
                rel_term = "name" if binding else col.name
                req_ref_ids.append(f"param_{action_code}_{col.name}")
                all_params.append(
                    {
                        "id": f"param_{action_code}_{col.name}",
                        "type": "RequestParameter",
                        "paramCode": col.name,
                        "paramType": "string",
                        "description": col.comment or col.name,
                        "isRequired": "false",
                        "termTypeCodePath": term_path,
                        "libraryCode": config.library_code,
                        "relTermCodeorname": rel_term,
                        "termDataType": term_dt,
                    }
                )
            resp_ref_ids.append(f"resp_{action_code}_{col.name}")
            all_params.append(
                {
                    "id": f"resp_{action_code}_{col.name}",
                    "type": "ResponseParameter",
                    "fieldCode": col.name,
                    "fieldType": map_data_type(col.sql_type, col.name).lower(),
                    "termTypeCodePath": f"OBJECT#{table.code}",
                    "libraryCode": config.library_code,
                    "objectProperty": col.name,
                    "jsonPath": f"data.{col.name}",
                    "termDataType": "ONTOLOGY_TERM",
                }
            )

        actions.append(
            {
                "actionCode": action_code,
                "actionName": f"查询{table.name}",
                "actionDesc": f"{table.name}查询动作",
                "actionType": "QUERY",
                "functionRefs": json.dumps([action_code], ensure_ascii=False),
                "belongEntity": json.dumps([table.code], ensure_ascii=False),
                "requestUrl": f"/{action_code}",
                "requestMethod": "POST",
                "requestParams": req_ref_ids,
                "responseParams": resp_ref_ids,
            }
        )

    builder = GraphBuilder()
    for action_data in actions:
        uri = builder._ns[f"action_{action_data['actionCode']}"]
        builder._graph.add((uri, builder._RDF.type, builder._ns.ActionDefinition))
        builder._add_literal(uri, builder._ns.actionCode, action_data["actionCode"])
        builder._add_literal(uri, builder._ns.actionName, action_data["actionName"])
        builder._add_literal(uri, builder._ns.actionType, action_data["actionType"])
        builder._add_literal(uri, builder._ns.requestUrl, action_data["requestUrl"])
        builder._add_literal(uri, builder._ns.requestMethod, action_data["requestMethod"])

    for param in all_params:
        param_uri = builder._ns[param["id"]]
        builder._graph.add((param_uri, builder._RDF.type, builder._ns[param["type"]]))
        for key, value in param.items():
            if key not in ("id", "type"):
                builder._add_literal(param_uri, builder._ns[key], value)

    return _serialize_xml(builder)
