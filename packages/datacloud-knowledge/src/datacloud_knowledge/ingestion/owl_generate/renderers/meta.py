"""领域 & 本体库 OWL 渲染。"""

from __future__ import annotations

from datacloud_knowledge.ingestion.owl_generate._xml import xml_escape
from datacloud_knowledge.ingestion.owl_generate.models import OwlGenConfig


def render_domains(config: OwlGenConfig) -> str:
    """领域定义 OWL。"""
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/domain/ontology#">

    <owl:Class rdf:about="#DomainDefinition">
        <rdfs:label>领域定义</rdfs:label>
    </owl:Class>

    <owl:NamedIndividual rdf:about="#domain_{config.domain_code.lower()}">
        <rdf:type rdf:resource="#DomainDefinition"/>
        <domain_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.domain_code}</domain_code>
        <domain_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.domain_name}</domain_name>
        <parent_domain_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
</parent_domain_code>
        <remark rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(config.domain_desc)}</remark>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#domain_code"/>
    <owl:DatatypeProperty rdf:about="#domain_name"/>
    <owl:DatatypeProperty rdf:about="#parent_domain_code"/>
    <owl:DatatypeProperty rdf:about="#remark"/>
    <owl:DatatypeProperty rdf:about="#version"/>
</rdf:RDF>
"""


def render_library(config: OwlGenConfig) -> str:
    """本体库定义 OWL。"""
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/library/ontology#">

    <owl:Class rdf:about="#LibraryDefinition">
        <rdfs:label>本体库定义</rdfs:label>
    </owl:Class>

    <owl:NamedIndividual rdf:about="#library_{config.library_code.lower()}">
        <rdf:type rdf:resource="#LibraryDefinition"/>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.library_code}</library_code>
        <library_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{config.library_name}</library_name>
        <library_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">\
{xml_escape(config.library_desc)}</library_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#library_code"/>
    <owl:DatatypeProperty rdf:about="#library_name"/>
    <owl:DatatypeProperty rdf:about="#library_desc"/>
    <owl:DatatypeProperty rdf:about="#version"/>
</rdf:RDF>
"""
