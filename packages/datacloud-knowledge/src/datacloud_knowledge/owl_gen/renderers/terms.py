"""术语定义 OWL 渲染。

包含所有四层术语：
- object（对象）
- action（动作）
- view（视图）
- prop（属性/字段）← 补全缺失层
- LIST_TERM / DICT_TERM（值术语）
"""

from __future__ import annotations

import json
from collections import OrderedDict

from datacloud_knowledge.owl_gen._xml import safe_xml_id, xml_escape
from datacloud_knowledge.owl_gen.models import OwlGenConfig, Table, ViewConfig

_TERM_HEADER = """\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/term/ontology#">

    <owl:Class rdf:about="#TermDefinition">\
<rdfs:label>术语定义</rdfs:label></owl:Class>"""

_TERM_FOOTER = """\
    <owl:DatatypeProperty rdf:about="#term_code_path"/>
    <owl:DatatypeProperty rdf:about="#term_code"/>
    <owl:DatatypeProperty rdf:about="#term_name"/>
    <owl:DatatypeProperty rdf:about="#library_code"/>
    <owl:DatatypeProperty rdf:about="#term_type_code"/>
    <owl:DatatypeProperty rdf:about="#term_desc"/>
    <owl:DatatypeProperty rdf:about="#synonyms"/>
    <owl:DatatypeProperty rdf:about="#terms_knowledge"/>
    <owl:DatatypeProperty rdf:about="#domain_code"/>
    <owl:DatatypeProperty rdf:about="#owl_doc_file"/>
    <owl:DatatypeProperty rdf:about="#ext_field"/>
    <owl:DatatypeProperty rdf:about="#parent_term_code"/>
    <owl:DatatypeProperty rdf:about="#version"/>
</rdf:RDF>"""


def _term_item(
    config: OwlGenConfig,
    code_path: str,
    term_code: str,
    term_name: str,
    term_type_code: str,
    term_desc: str,
    owl_doc_file: str = "",
    parent_term_code: str = "",
    synonyms: list[str] | None = None,
) -> str:
    synonyms_json = json.dumps(synonyms or [], ensure_ascii=False)
    return f"""\
    <owl:NamedIndividual rdf:about="#term_{term_type_code}_{safe_xml_id(term_code, 200)}">
        <rdf:type rdf:resource="#TermDefinition"/>
        <term_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(code_path)}</term_code_path>
        <term_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(term_code)}</term_code>
        <term_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(term_name)}</term_name>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.library_code}</library_code>
        <term_type_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{term_type_code}</term_type_code>
        <term_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(term_desc)}</term_desc>
        <synonyms rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_escape(synonyms_json)}</synonyms>
        <terms_knowledge rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
[]</terms_knowledge>
        <domain_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.domain_code}</domain_code>
        <owl_doc_file rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(owl_doc_file)}</owl_doc_file>
        <ext_field rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></ext_field>
        <parent_term_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(parent_term_code)}</parent_term_code>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""


def _wrap_terms(items: list[str]) -> str:
    """将术语条目包装为完整 OWL 文档。"""
    body = "\n\n".join(items)
    return f"{_TERM_HEADER}\n\n{body}\n\n{_TERM_FOOTER}\n"


def render_terms(
    config: OwlGenConfig,
    tables: list[Table],
    term_values: dict[str, list[dict[str, str]]],
    term_type_defs: OrderedDict[str, tuple[str, str, str]],
) -> dict[str, tuple[str, int]]:
    """渲染术语定义 OWL，按类型拆文件。

    返回 ``{relative_path: (content, count)}``：
    - ``terms/terms_ontology.owl`` — 对象/动作/视图/属性术语
    - ``terms/terms_{type_code}.owl`` — 每种值术语类型一个文件
    """
    result: dict[str, tuple[str, int]] = {}

    # ── 本体术语（对象/动作/视图/属性）──
    ontology_items: list[str] = []

    # 对象术语
    for table in tables:
        ontology_items.append(
            _term_item(
                config,
                code_path=f"OBJECT#{table.code}",
                term_code=table.code,
                term_name=table.name,
                term_type_code="object",
                term_desc=table.desc,
                owl_doc_file=f"ontology/objects/{table.code}/{table.code}_object.owl",
            )
        )

    # 动作术语
    for table in tables:
        action_code = f"query_{table.code}"
        ontology_items.append(
            _term_item(
                config,
                code_path=f"ACTION#{action_code}",
                term_code=action_code,
                term_name=f"查询{table.name}",
                term_type_code="action",
                term_desc=f"{table.name}查询动作",
                owl_doc_file="ontology/actions/action.owl",
            )
        )

    # 视图术语
    for v in config.resolved_views():
        ontology_items.append(
            _term_item(
                config,
                code_path=f"VIEW#{v.view_code}",
                term_code=v.view_code,
                term_name=v.view_name,
                term_type_code="view",
                term_desc=v.view_desc,
                owl_doc_file=f"ontology/views/{v.view_code}/{v.view_code}_view.owl",
            )
        )

    # 属性术语 (prop)：跨对象同名字段只保留首个定义。
    seen_prop_codes: set[str] = set()
    for table in tables:
        for col in table.columns:
            resolved_prop = config.resolve_object_prop(
                table.code, col.name, col.comment or col.name
            )
            if resolved_prop.property_code in seen_prop_codes:
                continue
            seen_prop_codes.add(resolved_prop.property_code)
            ontology_items.append(
                _term_item(
                    config,
                    code_path=f"PROP#{resolved_prop.property_code}",
                    term_code=resolved_prop.property_code,
                    term_name=resolved_prop.property_name,
                    term_type_code="prop",
                    term_desc=resolved_prop.property_desc,
                    synonyms=resolved_prop.synonyms,
                )
            )

    result["terms/terms_ontology.owl"] = (_wrap_terms(ontology_items), len(ontology_items))

    # ── 值术语（每种类型一个文件）──
    for type_code, values in term_values.items():
        type_name = term_type_defs.get(type_code, (type_code, "", ""))[0]
        items: list[str] = []
        for entry in values:
            items.append(
                _term_item(
                    config,
                    code_path=f"{config.library_code}#{type_code}#{entry['code']}",
                    term_code=entry["code"],
                    term_name=entry["name"],
                    term_type_code=type_code,
                    term_desc=f"{type_name}术语：{entry['name']}",
                    parent_term_code=entry.get("parent_prop_code", ""),
                )
            )
        if items:
            result[f"terms/terms_{type_code}.owl"] = (_wrap_terms(items), len(items))

    return result


def render_terms_for_object(
    config: OwlGenConfig,
    table: Table,
    term_values: dict[str, list[dict[str, str]]],
    term_type_defs: OrderedDict[str, tuple[str, str, str]],
    seen_prop_codes: set[str] | None = None,
) -> tuple[str, int]:
    """渲染单个对象下的所有术语（object + prop + 值术语）。"""
    items: list[str] = []
    prop_codes = seen_prop_codes if seen_prop_codes is not None else set()
    items.append(
        _term_item(
            config,
            code_path=f"OBJECT#{table.code}",
            term_code=table.code,
            term_name=table.name,
            term_type_code="object",
            term_desc=table.desc,
            owl_doc_file=f"object/{table.code}/{table.code}_definition.owl",
        )
    )

    for col in table.columns:
        resolved_prop = config.resolve_object_prop(table.code, col.name, col.comment or col.name)
        if resolved_prop.property_code in prop_codes:
            continue
        prop_codes.add(resolved_prop.property_code)
        items.append(
            _term_item(
                config,
                code_path=f"PROP#{resolved_prop.property_code}",
                term_code=resolved_prop.property_code,
                term_name=resolved_prop.property_name,
                term_type_code="prop",
                term_desc=resolved_prop.property_desc,
                synonyms=resolved_prop.synonyms,
            )
        )

    binding_lookup = {b.column_name: b for b in config.term_bindings if b.table_code == table.code}
    for binding in binding_lookup.values():
        type_code = binding.term_type_code
        type_name = term_type_defs.get(type_code, (type_code, "", ""))[0]
        for entry in term_values.get(type_code, []):
            items.append(
                _term_item(
                    config,
                    code_path=f"{config.library_code}#{type_code}#{entry['code']}",
                    term_code=entry["code"],
                    term_name=entry["name"],
                    term_type_code=type_code,
                    term_desc=f"{type_name}术语：{entry['name']}",
                    parent_term_code=entry.get("parent_prop_code", ""),
                )
            )

    return (_wrap_terms(items), len(items))


def render_terms_for_view(
    config: OwlGenConfig,
    view: ViewConfig,
    term_values: dict[str, list[dict[str, str]]] | None = None,
    term_type_defs: OrderedDict[str, tuple[str, str, str]] | None = None,
) -> tuple[str, int]:
    """渲染单个视图的术语定义。

    生成 VIEW 术语，以及视图专属 prop 术语。

    规则：
    - 与对象源字段同 code 的映射（如 enterprise_id -> enterprise_id）沿用对象层 prop，避免重复生成。
    - property_code 与 source_object_column_code 不同的视图字段（如 grid_total_revenue -> total_revenue）
      生成独立 prop 术语，保留自身 code 与中文名，避免被标准化为源字段 code。
    """
    items: list[str] = [
        _term_item(
            config,
            code_path=f"VIEW#{view.view_code}",
            term_code=view.view_code,
            term_name=view.view_name,
            term_type_code="view",
            term_desc=view.view_desc,
            owl_doc_file=f"view/{view.view_code}/{view.view_code}_definition.owl",
        )
    ]

    for mapping in view.field_mappings:
        object_prop_code = config.resolve_object_prop_code(
            mapping.source_object_code,
            mapping.source_object_column_code,
        )
        if not config.force_view_prop_terms and mapping.property_code in {
            mapping.source_object_column_code,
            object_prop_code,
        }:
            continue
        items.append(
            _term_item(
                config,
                code_path=f"VIEW_PROP#{view.view_code}#{mapping.property_code}",
                term_code=mapping.property_code,
                term_name=mapping.property_name,
                term_type_code="prop",
                term_desc=f"视图属性：{mapping.property_name}",
                owl_doc_file=f"view/{view.view_code}/{view.view_code}_terms.owl",
                synonyms=mapping.synonyms,
            )
        )

    if config.force_view_value_terms and term_values and term_type_defs:
        binding_lookup = {
            (binding.table_code, binding.column_name): binding for binding in config.term_bindings
        }
        emitted_props: set[str] = set()
        for mapping in view.field_mappings:
            binding = binding_lookup.get(
                (mapping.source_object_code, mapping.source_object_column_code)
            )
            if binding is None or mapping.property_code in emitted_props:
                continue

            emitted_props.add(mapping.property_code)
            type_name = term_type_defs.get(
                binding.term_type_code, (binding.term_type_code, "", "")
            )[0]
            for entry in term_values.get(binding.term_type_code, []):
                items.append(
                    _term_item(
                        config,
                        code_path=f"VIEW_VALUE#{view.view_code}#{mapping.property_code}#{entry['code']}",
                        term_code=entry["code"],
                        term_name=entry["name"],
                        term_type_code=binding.term_type_code,
                        term_desc=f"{type_name}术语：{entry['name']}",
                        parent_term_code=mapping.property_code,
                    )
                )
    return (_wrap_terms(items), len(items))
