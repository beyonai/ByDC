"""术语类型 OWL 渲染。"""

from __future__ import annotations

from collections import OrderedDict

from datacloud_knowledge.ingestion.owl_generate._xml import xml_escape
from datacloud_knowledge.ingestion.owl_generate.models import OwlGenConfig, Table


def build_term_type_defs(
    config: OwlGenConfig,
) -> OrderedDict[str, tuple[str, str, str]]:
    """构建术语类型定义表：code → (name, desc, data_type)。

    包含固定的本体术语类型 + 从 term_bindings 收集的值术语类型
    + ONTOLOGY_PROP（属性术语类型，补全缺失层）。
    """
    defs: OrderedDict[str, tuple[str, str, str]] = OrderedDict()
    # 固定本体术语类型
    defs["object"] = ("对象", "对象本体术语类型", "ONTOLOGY_TERM")
    defs["action"] = ("动作", "动作本体术语类型", "ONTOLOGY_TERM")
    defs["view"] = ("视图", "视图本体术语类型", "ONTOLOGY_TERM")
    # 属性术语类型（补全缺失层）
    defs["prop"] = ("属性", "属性/字段本体术语类型", "ONTOLOGY_TERM")
    # 从 term_bindings 收集值术语类型
    seen: set[str] = set()
    for binding in config.term_bindings:
        if binding.term_type_code in seen:
            continue
        seen.add(binding.term_type_code)
        configured_type = config.resolve_term_type(binding.term_type_code)
        type_name = (
            configured_type.type_name if configured_type is not None else binding.term_type_code
        )
        type_desc = (
            configured_type.type_desc
            if configured_type is not None and configured_type.type_desc
            else f"{type_name}术语类型"
        )
        defs[binding.term_type_code] = (
            type_name,
            type_desc,
            binding.term_data_type,
        )
    return defs


def enrich_term_type_names(
    defs: OrderedDict[str, tuple[str, str, str]],
    tables: list[Table],
    config: OwlGenConfig,
) -> None:
    """用表字段注释替换术语类型名称（就地修改）。"""
    col_comments: dict[str, str] = {}
    for table in tables:
        for col in table.columns:
            if col.comment:
                col_comments.setdefault(col.name, col.comment)
    for binding in config.term_bindings:
        code = binding.term_type_code
        if code in defs:
            old_name, _old_desc, data_type = defs[code]
            if config.resolve_term_type(code) is not None:
                continue
            comment = col_comments.get(binding.column_name, "")
            if comment and old_name == code:
                defs[code] = (comment, f"{comment}术语类型", data_type)


def _term_type_item(
    config: OwlGenConfig,
    type_code: str,
    name: str,
    desc: str,
    term_data_type: str,
) -> str:
    return f"""\
    <owl:NamedIndividual rdf:about="#termtype_{type_code}">
        <rdf:type rdf:resource="#TermTypeDefinition"/>
        <trem_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.library_code}#{type_code}</trem_type_code_path>
        <trem_type_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{type_code}</trem_type_code>
        <trem_type_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(name)}</trem_type_name>
        <trem_type_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(desc)}</trem_type_desc>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{term_data_type}</term_data_type>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.library_code}</library_code>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""


def _wrap_term_types(items: list[str]) -> str:
    body = "\n\n".join(items)
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/termtype/ontology#">

    <owl:Class rdf:about="#TermTypeDefinition">\
<rdfs:label>术语类型定义</rdfs:label></owl:Class>

{body}

    <owl:DatatypeProperty rdf:about="#trem_type_code_path"/>
    <owl:DatatypeProperty rdf:about="#trem_type_code"/>
    <owl:DatatypeProperty rdf:about="#trem_type_name"/>
    <owl:DatatypeProperty rdf:about="#trem_type_desc"/>
    <owl:DatatypeProperty rdf:about="#term_data_type"/>
    <owl:DatatypeProperty rdf:about="#library_code"/>
    <owl:DatatypeProperty rdf:about="#version"/>
</rdf:RDF>
"""


def render_term_types(
    config: OwlGenConfig,
    defs: OrderedDict[str, tuple[str, str, str]],
) -> str:
    """术语类型定义 OWL。"""
    items: list[str] = []
    for type_code, (name, desc, term_data_type) in defs.items():
        items.append(_term_type_item(config, type_code, name, desc, term_data_type))
    return _wrap_term_types(items)


def render_term_types_for_object(
    config: OwlGenConfig,
    table: Table,
    term_type_defs: OrderedDict[str, tuple[str, str, str]],
) -> str:
    """渲染单个对象涉及的术语类型定义。"""
    type_codes: set[str] = {"object", "prop"}
    for binding in config.term_bindings:
        if binding.table_code == table.code:
            type_codes.add(binding.term_type_code)

    items: list[str] = []
    for type_code in term_type_defs:
        if type_code not in type_codes:
            continue
        name, desc, term_data_type = term_type_defs[type_code]
        items.append(_term_type_item(config, type_code, name, desc, term_data_type))
    return _wrap_term_types(items)
