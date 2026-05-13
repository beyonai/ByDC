#!/usr/bin/env python3
"""将 JSON 导入包转换为 OWL 导入包。"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

LOGGER = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "resource" / "knowledge" / "import_package"
DEFAULT_OUTPUT_DIR = ROOT / "resource" / "knowledge" / "import_package_owl_sales"

FIXED_TERM_TYPES: dict[str, tuple[str, str]] = {
    "object": ("对象", "ONTOLOGY_TERM"),
    "action": ("动作", "ONTOLOGY_TERM"),
    "view": ("视图", "ONTOLOGY_TERM"),
    "prop": ("属性", "ONTOLOGY_TERM"),
}
PROPERTY_COMMENT_MAX_LEN = 200


@dataclass(slots=True)
class DomainRecord:
    """领域定义。"""

    domain_code: str
    domain_name: str
    domain_desc: str = ""
    parent_code: str = ""


@dataclass(slots=True)
class LibraryRecord:
    """本体库定义。"""

    library_code: str
    library_name: str
    library_desc: str = ""


@dataclass(slots=True)
class TermTypeRecord:
    """术语类型定义。"""

    term_type_code: str
    term_type_name: str
    term_data_type: str


def xml_text(value: object) -> str:
    """转义 XML 文本内容。"""
    return escape(str(value), {'"': "&quot;"})


def dump_json(value: object) -> str:
    """输出紧凑 JSON。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def safe_fragment(value: str) -> str:
    """生成稳定的 XML 片段标识。"""
    fragment = re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_")
    if not fragment:
        fragment = "item"
    if fragment[0].isdigit():
        fragment = f"n_{fragment}"
    return fragment


def clean_directory(path: Path) -> None:
    """清空输出目录。"""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    """写入文本文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    """读取单个 JSON 文件。"""
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 文件。"""
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def iter_json_files(path: Path) -> list[Path]:
    """返回目录下的 JSON 文件列表。"""
    if not path.exists():
        return []
    return sorted(file for file in path.iterdir() if file.suffix == ".json")


def load_package(source_dir: Path) -> dict[str, Any]:
    """加载源 JSON 导入包。"""
    manifest = read_json(source_dir / "manifest.json")
    domains = [
        DomainRecord(
            domain_code=row.get("domain_code", ""),
            domain_name=row.get("domain_name", ""),
            domain_desc=row.get("domain_desc", ""),
            parent_code=row.get("parent_code", ""),
        )
        for row in read_jsonl(source_dir / "meta" / "domains.jsonl")
        if row.get("op") != "delete"
    ]
    libraries = [
        LibraryRecord(
            library_code=row.get("library_code", ""),
            library_name=row.get("library_name", ""),
            library_desc=row.get("library_desc", ""),
        )
        for row in read_jsonl(source_dir / "meta" / "libraries.jsonl")
        if row.get("op") != "delete"
    ]
    objects = [read_json(path) for path in iter_json_files(source_dir / "ontology" / "objects")]
    actions = [read_json(path) for path in iter_json_files(source_dir / "ontology" / "actions")]
    functions = {
        data["function_code"]: data
        for data in (
            read_json(path) for path in iter_json_files(source_dir / "ontology" / "functions")
        )
        if data.get("function_code")
    }
    views = [read_json(path) for path in iter_json_files(source_dir / "ontology" / "views")]
    return {
        "manifest": manifest,
        "domains": domains,
        "libraries": libraries,
        "objects": objects,
        "actions": actions,
        "functions": functions,
        "views": views,
    }


def choose_primary_library_code(libraries: list[LibraryRecord]) -> str:
    """选择默认库编码，用于 termMeta 缺省场景。"""
    candidates = {library.library_code for library in libraries}
    for code in ("LIB_003", "LIB_002", "LIB_001"):
        if code in candidates:
            return code
    if libraries:
        return libraries[0].library_code
    return "LIB_001"


def choose_primary_domain_code(domains: list[DomainRecord]) -> str:
    """选择默认领域编码。"""
    return domains[0].domain_code if domains else "DOMAIN_001"


def term_data_type_from_meta(term_meta: dict[str, Any] | None) -> str:
    """从 termMeta 推导术语数据类型。"""
    if not term_meta:
        return ""
    master_type = str(term_meta.get("termMasterType", "")).lower()
    if master_type == "list":
        return "LIST_TERM"
    if master_type == "dict":
        return "DICT_TERM"
    if master_type == "ontology":
        return "ONTOLOGY_TERM"
    return ""


def build_term_type_path(term_meta: dict[str, Any] | None, default_library_code: str) -> str:
    """构造 OWL 中的 term_type_code_path。"""
    if not term_meta:
        return ""
    master_type = str(term_meta.get("termMasterType", "")).lower()
    if master_type == "ontology":
        object_code = str(term_meta.get("objectCode") or term_meta.get("termTypeCode") or "")
        return f"OBJECT#{object_code}" if object_code else ""

    term_type_code = str(term_meta.get("termTypeCode") or "")
    if not term_type_code:
        return ""

    library_code = str(term_meta.get("libraryCode") or default_library_code)
    return f"{library_code}#{term_type_code}"


def field_to_term_type_name(field_name: str) -> str:
    """压缩术语类型名称，避免长描述直接落库。"""
    compact = field_name.strip()
    if len(compact) <= PROPERTY_COMMENT_MAX_LEN:
        return compact
    return compact[:PROPERTY_COMMENT_MAX_LEN]


def discover_term_types(
    objects: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> list[TermTypeRecord]:
    """从对象字段和动作参数收集术语类型。"""
    discovered: dict[str, TermTypeRecord] = {
        code: TermTypeRecord(
            term_type_code=code,
            term_type_name=name,
            term_data_type=data_type,
        )
        for code, (name, data_type) in FIXED_TERM_TYPES.items()
    }

    def register_from_term_meta(label: str, term_meta: dict[str, Any] | None) -> None:
        if not term_meta:
            return
        term_type_code = str(term_meta.get("termTypeCode") or "").strip()
        term_data_type = term_data_type_from_meta(term_meta)
        if not term_type_code or not term_data_type:
            return
        discovered.setdefault(
            term_type_code,
            TermTypeRecord(
                term_type_code=term_type_code,
                term_type_name=field_to_term_type_name(label or term_type_code),
                term_data_type=term_data_type,
            ),
        )

    for obj in objects:
        for field in obj.get("fields", []):
            register_from_term_meta(str(field.get("field_name") or field.get("field_code") or ""), field.get("termMeta"))

    for action in actions:
        for param in action.get("params", []):
            register_from_term_meta(
                str(param.get("param_name") or param.get("param_code") or ""),
                param.get("termMeta"),
            )

    fixed_order = list(FIXED_TERM_TYPES)
    dynamic_codes = sorted(code for code in discovered if code not in FIXED_TERM_TYPES)
    return [discovered[code] for code in [*fixed_order, *dynamic_codes]]


def collect_relations(
    objects: list[dict[str, Any]],
    views: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """收集对象关系，按 relation_code 去重。"""
    relations: dict[str, dict[str, Any]] = {}

    def add_relation(raw: dict[str, Any], source_class: str) -> None:
        relation_code = str(raw.get("relation_code") or "").strip()
        if not relation_code:
            return
        if relation_code in relations:
            return
        normalized = dict(raw)
        normalized.setdefault("source_class", source_class)
        normalized.setdefault("target_class", "")
        normalized.setdefault("relation_name", relation_code)
        normalized.setdefault("relation_type", "ONE_TO_MANY")
        normalized["join_keys"] = list(raw.get("join_keys", []))
        relations[relation_code] = normalized

    for obj in objects:
        source_class = str(obj.get("object_code") or "")
        for relation in obj.get("relations", []):
            if isinstance(relation, dict):
                add_relation(relation, source_class=source_class)

    for view in views:
        for relation in view.get("relations", []):
            if isinstance(relation, dict):
                add_relation(relation, source_class=str(relation.get("source_class") or ""))

    return [relations[code] for code in sorted(relations)]


def collect_datasources(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """提取对象上的数据源配置。"""
    datasource_map: dict[str, dict[str, Any]] = {}
    for obj in objects:
        source_config = obj.get("source_config")
        if not isinstance(source_config, dict):
            continue
        alias = str(source_config.get("alias") or obj.get("datasource_alias") or "").strip()
        if not alias:
            continue
        datasource_map.setdefault(alias, source_config)
    return [datasource_map[alias] for alias in sorted(datasource_map)]


def extract_action_route(function_config: dict[str, Any] | None) -> tuple[str, str]:
    """从 function api_schema 中提取 URL 和方法。"""
    if not function_config:
        return "", ""

    api_schema = function_config.get("api_schema")
    if not isinstance(api_schema, dict):
        return "", ""

    servers = api_schema.get("servers", [])
    server_url = ""
    if isinstance(servers, list) and servers:
        first_server = servers[0]
        if isinstance(first_server, dict):
            server_url = str(first_server.get("url") or "").rstrip("/")

    paths = api_schema.get("paths", {})
    if not isinstance(paths, dict) or not paths:
        return "", ""

    first_path = next(iter(paths))
    path_payload = paths.get(first_path, {})
    if not isinstance(path_payload, dict):
        method = "POST"
    else:
        method = next(iter(path_payload), "post").upper()

    request_url = f"{server_url}{first_path}" if server_url else str(first_path)
    return request_url, method


def render_domains(domains: list[DomainRecord]) -> str:
    """渲染 domains.owl。"""
    individuals = []
    for domain in domains:
        individuals.append(
            f"""\
    <owl:NamedIndividual rdf:about="#{safe_fragment(domain.domain_code.lower())}">
        <rdf:type rdf:resource="#DomainDefinition"/>
        <domain_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(domain.domain_code)}</domain_code>
        <domain_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(domain.domain_name)}</domain_name>
        <parent_domain_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(domain.parent_code)}</parent_domain_code>
        <remark rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(domain.domain_desc)}</remark>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""
        )
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/domain/ontology#">

    <owl:Class rdf:about="#DomainDefinition"><rdfs:label>领域定义</rdfs:label></owl:Class>

{chr(10).join(individuals)}

    <owl:DatatypeProperty rdf:about="#domain_code"/>
    <owl:DatatypeProperty rdf:about="#domain_name"/>
    <owl:DatatypeProperty rdf:about="#parent_domain_code"/>
    <owl:DatatypeProperty rdf:about="#remark"/>
    <owl:DatatypeProperty rdf:about="#version"/>
</rdf:RDF>
"""


def render_libraries(libraries: list[LibraryRecord]) -> str:
    """渲染 library.owl。"""
    individuals = []
    for library in libraries:
        individuals.append(
            f"""\
    <owl:NamedIndividual rdf:about="#{safe_fragment(library.library_code.lower())}">
        <rdf:type rdf:resource="#LibraryDefinition"/>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(library.library_code)}</library_code>
        <library_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(library.library_name)}</library_name>
        <library_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(library.library_desc)}</library_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""
        )
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/library/ontology#">

    <owl:Class rdf:about="#LibraryDefinition"><rdfs:label>本体库定义</rdfs:label></owl:Class>

{chr(10).join(individuals)}

    <owl:DatatypeProperty rdf:about="#library_code"/>
    <owl:DatatypeProperty rdf:about="#library_name"/>
    <owl:DatatypeProperty rdf:about="#library_desc"/>
    <owl:DatatypeProperty rdf:about="#version"/>
</rdf:RDF>
"""


def render_term_types(
    term_types: list[TermTypeRecord],
    library_code: str,
) -> str:
    """渲染 term_types.owl。"""
    individuals = []
    for term_type in term_types:
        individuals.append(
            f"""\
    <owl:NamedIndividual rdf:about="#termtype_{safe_fragment(term_type.term_type_code)}">
        <rdf:type rdf:resource="#TermTypeDefinition"/>
        <trem_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(f"{library_code}#{term_type.term_type_code}")}</trem_type_code_path>
        <trem_type_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_type.term_type_code)}</trem_type_code>
        <trem_type_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_type.term_type_name)}</trem_type_name>
        <trem_type_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(f"{term_type.term_type_name}术语类型")}</trem_type_desc>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_type.term_data_type)}</term_data_type>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(library_code)}</library_code>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""
        )
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/termtype/ontology#">

    <owl:Class rdf:about="#TermTypeDefinition"><rdfs:label>术语类型定义</rdfs:label></owl:Class>

{chr(10).join(individuals)}

    <owl:DatatypeProperty rdf:about="#trem_type_code_path"/>
    <owl:DatatypeProperty rdf:about="#trem_type_code"/>
    <owl:DatatypeProperty rdf:about="#trem_type_name"/>
    <owl:DatatypeProperty rdf:about="#trem_type_desc"/>
    <owl:DatatypeProperty rdf:about="#term_data_type"/>
    <owl:DatatypeProperty rdf:about="#library_code"/>
    <owl:DatatypeProperty rdf:about="#version"/>
</rdf:RDF>
"""


def render_terms(
    *,
    objects: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    views: list[dict[str, Any]],
    library_code: str,
    domain_code: str,
) -> tuple[str, int]:
    """渲染 terms.owl，仅生成本体术语。"""
    items: list[str] = []

    def add_term(
        *,
        term_code_path: str,
        term_code: str,
        term_name: str,
        term_type_code: str,
        term_desc: str,
        owl_doc_file: str,
    ) -> None:
        items.append(
            f"""\
    <owl:NamedIndividual rdf:about="#term_{safe_fragment(term_type_code)}_{safe_fragment(term_code)}">
        <rdf:type rdf:resource="#TermDefinition"/>
        <term_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_code_path)}</term_code_path>
        <term_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_code)}</term_code>
        <term_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_name)}</term_name>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(library_code)}</library_code>
        <term_type_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_type_code)}</term_type_code>
        <term_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_desc)}</term_desc>
        <synonyms rdf:datatype="http://www.w3.org/2001/XMLSchema#string">[]</synonyms>
        <terms_knowledge rdf:datatype="http://www.w3.org/2001/XMLSchema#string">[]</terms_knowledge>
        <domain_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(domain_code)}</domain_code>
        <owl_doc_file rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(owl_doc_file)}</owl_doc_file>
        <ext_field rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></ext_field>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""
        )

    for obj in objects:
        object_code = str(obj.get("object_code") or "")
        add_term(
            term_code_path=f"OBJECT#{object_code}",
            term_code=object_code,
            term_name=str(obj.get("object_name") or object_code),
            term_type_code="object",
            term_desc=str(obj.get("description") or ""),
            owl_doc_file=f"ontology/objects/{object_code}/{object_code}_object.owl",
        )
        for field in obj.get("fields", []):
            field_code = str(field.get("field_code") or "")
            add_term(
                term_code_path=f"PROP#{object_code}.{field_code}",
                term_code=f"{object_code}.{field_code}",
                term_name=str(field.get("field_name") or field_code),
                term_type_code="prop",
                term_desc=f"{obj.get('object_name') or object_code}的字段：{field.get('field_name') or field_code}",
                owl_doc_file=f"ontology/objects/{object_code}/{object_code}_object.owl",
            )

    for action in actions:
        action_code = str(action.get("action_code") or "")
        add_term(
            term_code_path=f"ACTION#{action_code}",
            term_code=action_code,
            term_name=str(action.get("action_name") or action_code),
            term_type_code="action",
            term_desc=str(action.get("description") or ""),
            owl_doc_file=f"ontology/actions/{action_code}.owl",
        )

    for view in views:
        view_code = str(view.get("view_id") or "")
        add_term(
            term_code_path=f"VIEW#{view_code}",
            term_code=view_code,
            term_name=str(view.get("view_name") or view_code),
            term_type_code="view",
            term_desc=str(view.get("description") or ""),
            owl_doc_file="ontology/views/views.owl",
        )

    content = f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/term/ontology#">

    <owl:Class rdf:about="#TermDefinition"><rdfs:label>术语定义</rdfs:label></owl:Class>

{chr(10).join(items)}

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
    <owl:DatatypeProperty rdf:about="#version"/>
</rdf:RDF>
"""
    return content, len(items)


def render_relations(relations: list[dict[str, Any]], library_code: str) -> str:
    """渲染 relation.owl。"""
    items = []
    for relation in relations:
        relation_code = str(relation.get("relation_code") or "")
        items.append(
            f"""\
    <owl:NamedIndividual rdf:about="#{safe_fragment(relation_code)}">
        <rdf:type rdf:resource="#TermRelation"/>
        <source_libeary rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(library_code)}</source_libeary>
        <source_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">对象</source_type>
        <source_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(relation.get("source_class", ""))}</source_code>
        <target_libeary rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(library_code)}</target_libeary>
        <target_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">对象</target_type>
        <target_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(relation.get("target_class", ""))}</target_code>
        <relation_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(relation.get("relation_name", relation_code))}</relation_name>
        <relation_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(relation.get("relation_type", "ONE_TO_MANY"))}</relation_type>
        <joinkeys rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(dump_json(relation.get("join_keys", [])))}</joinkeys>
        <ext_field rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></ext_field>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""
        )

    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/relation/ontology#">

    <owl:Class rdf:about="#TermRelation"><rdfs:label>术语关系</rdfs:label></owl:Class>

{chr(10).join(items)}

    <owl:DatatypeProperty rdf:about="#source_libeary"/>
    <owl:DatatypeProperty rdf:about="#source_type"/>
    <owl:DatatypeProperty rdf:about="#source_code"/>
    <owl:DatatypeProperty rdf:about="#target_libeary"/>
    <owl:DatatypeProperty rdf:about="#target_type"/>
    <owl:DatatypeProperty rdf:about="#target_code"/>
    <owl:DatatypeProperty rdf:about="#relation_name"/>
    <owl:DatatypeProperty rdf:about="#relation_type"/>
    <owl:DatatypeProperty rdf:about="#joinkeys"/>
    <owl:DatatypeProperty rdf:about="#ext_field"/>
    <owl:DatatypeProperty rdf:about="#version"/>
</rdf:RDF>
"""


def render_dbsources(datasources: list[dict[str, Any]]) -> str:
    """渲染 dbsource.owl。"""
    items = []
    for datasource in datasources:
        alias = str(datasource.get("alias") or "")
        db_type = str(datasource.get("db_type") or "")
        db_params = {
            key: value
            for key, value in datasource.items()
            if key not in {"alias", "db_type"}
        }
        items.append(
            f"""\
    <owl:NamedIndividual rdf:about="#dbsource_{safe_fragment(alias)}">
        <rdf:type rdf:resource="#DatabaseDefinition"/>
        <dbCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(alias)}</dbCode>
        <dbType rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(db_type)}</dbType>
        <dbParams rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(dump_json(db_params))}</dbParams>
    </owl:NamedIndividual>"""
        )
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/dbsource/ontology#">

    <owl:Class rdf:about="#DatabaseDefinition"><rdfs:label>数据源定义</rdfs:label></owl:Class>

{chr(10).join(items)}

    <owl:DatatypeProperty rdf:about="#dbCode"/>
    <owl:DatatypeProperty rdf:about="#dbType"/>
    <owl:DatatypeProperty rdf:about="#dbParams"/>
</rdf:RDF>
"""


def render_object_owl(obj: dict[str, Any], default_library_code: str) -> str:
    """渲染对象定义 OWL。"""
    object_code = str(obj.get("object_code") or "")
    fields = list(obj.get("fields", []))
    field_refs = "\n".join(
        f'        <fields rdf:resource="#{safe_fragment(str(field.get("field_code") or ""))}_field"/>'
        for field in fields
    )
    action_refs = dump_json(obj.get("action_refs", []))
    relation_refs = dump_json(
        [relation.get("relation_code") for relation in obj.get("relations", []) if relation.get("relation_code")]
    )
    field_items = []

    for field in fields:
        field_code = str(field.get("field_code") or "")
        term_meta = field.get("termMeta") if isinstance(field.get("termMeta"), dict) else None
        field_items.append(
            f"""\
    <owl:NamedIndividual rdf:about="#{safe_fragment(field_code)}_field">
        <rdf:type rdf:resource="#EntityField"/>
        <property_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(field_code)}</property_code>
        <property_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(field.get("field_name", field_code))}</property_name>
        <data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(field.get("field_type", "STRING"))}</data_type>
        <is_required rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">{str(bool(field.get("required", False))).lower()}</is_required>
        <default_value rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></default_value>
        <source_column rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(field.get("source_column", ""))}</source_column>
        <synonyms rdf:datatype="http://www.w3.org/2001/XMLSchema#string">[]</synonyms>
        <data_format rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></data_format>
        <measurement_unit rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></measurement_unit>
        <property_category rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></property_category>
        <property_group rdf:datatype="http://www.w3.org/2001/XMLSchema#string">STORAGE</property_group>
        <ext_property rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></ext_property>
        <term_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(build_term_type_path(term_meta, default_library_code))}</term_type_code_path>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(str((term_meta or {}).get("libraryCode") or default_library_code if term_meta else ""))}</library_code>
        <rel_action rdf:datatype="http://www.w3.org/2001/XMLSchema#string">[]</rel_action>
        <rel_term_codeorname rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(str((term_meta or {}).get("termField") or ""))}</rel_term_codeorname>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_data_type_from_meta(term_meta))}</term_data_type>
    </owl:NamedIndividual>"""
        )

    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/entity/ontology#">

    <owl:Class rdf:about="#EntityDefinition"><rdfs:label>实体定义</rdfs:label></owl:Class>
    <owl:Class rdf:about="#EntityField"><rdfs:label>实体字段</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#{safe_fragment(object_code)}_v1">
        <rdf:type rdf:resource="#EntityDefinition"/>
        <entity_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(object_code)}</entity_code>
        <entity_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(obj.get("object_name", object_code))}</entity_name>
        <entity_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(obj.get("description", ""))}</entity_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <entity_source rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(obj.get("source_type", "DB"))}</entity_source>
{field_refs}
        <action_refs rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(action_refs)}</action_refs>
        <relations rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(relation_refs)}</relations>
    </owl:NamedIndividual>

{chr(10).join(field_items)}

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


def render_mapping_owl(obj: dict[str, Any]) -> str:
    """渲染对象映射 OWL。"""
    object_code = str(obj.get("object_code") or "")
    source_config = obj.get("source_config") if isinstance(obj.get("source_config"), dict) else {}
    datasource_alias = str(source_config.get("alias") or obj.get("datasource_alias") or "")
    table_name = str(obj.get("table_name") or object_code)
    fields = list(obj.get("fields", []))
    mapping_refs = "\n".join(
        f'        <mapping rdf:resource="#{safe_fragment(str(field.get("field_code") or ""))}_mapping"/>'
        for field in fields
    )
    mapping_items = []
    for field in fields:
        field_code = str(field.get("field_code") or "")
        mapping_items.append(
            f"""\
    <owl:NamedIndividual rdf:about="#{safe_fragment(field_code)}_mapping">
        <rdf:type rdf:resource="#Mapping"/>
        <property_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(field_code)}</property_code>
        <property_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(field.get("field_name", field_code))}</property_name>
        <source_table_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(table_name)}</source_table_code>
        <source_column_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(field.get("source_column", field_code))}</source_column_code>
        <source_datasource_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(datasource_alias)}</source_datasource_code>
        <ext_property rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></ext_property>
    </owl:NamedIndividual>"""
        )
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/entity/mapping#">

    <owl:Class rdf:about="#EntityMapping"><rdfs:label>实体映射</rdfs:label></owl:Class>
    <owl:Class rdf:about="#Mapping"><rdfs:label>映射关系</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#{safe_fragment(object_code)}_mapping">
        <rdf:type rdf:resource="#EntityMapping"/>
        <entity_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(object_code)}</entity_code>
        <entity_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(obj.get("object_name", object_code))}</entity_name>
        <entity_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(obj.get("description", ""))}</entity_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
{mapping_refs}
    </owl:NamedIndividual>

{chr(10).join(mapping_items)}

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


def render_views_owl(views: list[dict[str, Any]]) -> str:
    """渲染 views.owl。"""
    individuals = []
    for view in views:
        object_ids = dump_json(view.get("object_ids", []))
        relation_codes = dump_json(
            [relation.get("relation_code") for relation in view.get("relations", []) if relation.get("relation_code")]
        )
        individuals.append(
            f"""\
    <owl:NamedIndividual rdf:about="#{safe_fragment(str(view.get("view_id") or ""))}_v1">
        <rdf:type rdf:resource="#SceneDefinition"/>
        <view_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(view.get("view_id", ""))}</view_code>
        <view_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(view.get("view_name", ""))}</view_name>
        <description rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(view.get("description", ""))}</description>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <object_codes rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(object_ids)}</object_codes>
        <relations rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(relation_codes)}</relations>
    </owl:NamedIndividual>"""
        )
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/scene/ontology#">

    <owl:Class rdf:about="#SceneDefinition"><rdfs:label>视图定义</rdfs:label></owl:Class>

{chr(10).join(individuals)}

    <owl:DatatypeProperty rdf:about="#view_code"/>
    <owl:DatatypeProperty rdf:about="#view_name"/>
    <owl:DatatypeProperty rdf:about="#description"/>
    <owl:DatatypeProperty rdf:about="#version"/>
    <owl:DatatypeProperty rdf:about="#object_codes"/>
    <owl:DatatypeProperty rdf:about="#relations"/>
</rdf:RDF>
"""


def render_action_owl(
    action: dict[str, Any],
    function_config: dict[str, Any] | None,
    default_library_code: str,
) -> str:
    """渲染单个动作 OWL。"""
    action_code = str(action.get("action_code") or "")
    params = list(action.get("params", []))
    request_url, request_method = extract_action_route(function_config)
    request_param_refs: list[str] = []
    response_param_refs: list[str] = []
    request_param_items: list[str] = []
    response_param_items: list[str] = []

    for index, param in enumerate(params):
        param_code = str(param.get("param_code") or f"param_{index}")
        ref_id = f"{safe_fragment(action_code)}_{safe_fragment(param_code)}_{index}"
        term_meta = param.get("termMeta") if isinstance(param.get("termMeta"), dict) else None
        direction = str(param.get("direction") or "IN").upper()
        mapping_path = str(param.get("mapping_path") or "")
        if direction in {"IN", "INOUT"}:
            request_param_refs.append(
                f'        <request_params rdf:resource="#param_{ref_id}"/>'
            )
            request_param_items.append(
                f"""\
    <owl:NamedIndividual rdf:about="#param_{ref_id}">
        <rdf:type rdf:resource="#RequestParameter"/>
        <paramCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(param_code)}</paramCode>
        <type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(str(param.get("param_type") or "STRING").lower())}</type>
        <description rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(param.get("param_name", param_code))}</description>
        <isRequired rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">{str(bool(param.get("required", False))).lower()}</isRequired>
        <mapping_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(mapping_path)}</mapping_path>
        <term_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(build_term_type_path(term_meta, default_library_code))}</term_type_code_path>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(str((term_meta or {}).get("libraryCode") or default_library_code if term_meta else ""))}</library_code>
        <rel_term_codeorname rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(str((term_meta or {}).get("termField") or ""))}</rel_term_codeorname>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_data_type_from_meta(term_meta))}</term_data_type>
    </owl:NamedIndividual>"""
            )
        if direction in {"OUT", "INOUT"}:
            response_param_refs.append(
                f'        <response_params rdf:resource="#resp_{ref_id}"/>'
            )
            response_param_items.append(
                f"""\
    <owl:NamedIndividual rdf:about="#resp_{ref_id}">
        <rdf:type rdf:resource="#ResponseParameter"/>
        <fieldCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(param_code)}</fieldCode>
        <fieldType rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(str(param.get("param_type") or "STRING").lower())}</fieldType>
        <term_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(build_term_type_path(term_meta, default_library_code))}</term_type_code_path>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(str((term_meta or {}).get("libraryCode") or default_library_code if term_meta else ""))}</library_code>
        <object_property rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(param_code)}</object_property>
        <json_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(mapping_path)}</json_path>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(term_data_type_from_meta(term_meta))}</term_data_type>
    </owl:NamedIndividual>"""
            )

    action_type = str(action.get("action_type") or "").strip().lower()
    owl_action_type = "QUERY" if action_type == "query" else "OPERATION"
    function_refs = dump_json(action.get("function_refs", []))
    belong_entity = dump_json([action.get("belong_class", "")] if action.get("belong_class") else [])
    script = str(action.get("script") or "")
    return f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/action/ontology#">

    <owl:Class rdf:about="#ActionDefinition"><rdfs:label>动作定义</rdfs:label></owl:Class>
    <owl:Class rdf:about="#RequestParameter"><rdfs:label>请求参数</rdfs:label></owl:Class>
    <owl:Class rdf:about="#ResponseParameter"><rdfs:label>响应参数</rdfs:label></owl:Class>
    <owl:Class rdf:about="#HeaderParameter"><rdfs:label>请求头参数</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#action_{safe_fragment(action_code)}">
        <rdf:type rdf:resource="#ActionDefinition"/>
        <action_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(action_code)}</action_code>
        <action_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(action.get("action_name", action_code))}</action_name>
        <action_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(action.get("description", ""))}</action_desc>
        <action_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(owl_action_type)}</action_type>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <function_refs rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(function_refs)}</function_refs>
        <belong_entity rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(belong_entity)}</belong_entity>
        <request_url rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(request_url)}</request_url>
        <request_method rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(request_method)}</request_method>
        <script rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml_text(script)}</script>
        <request_header rdf:resource="#http_header"/>
{chr(10).join(request_param_refs)}
{chr(10).join(response_param_refs)}
    </owl:NamedIndividual>

{chr(10).join(request_param_items)}

{chr(10).join(response_param_items)}

    <owl:NamedIndividual rdf:about="#http_header">
        <rdf:type rdf:resource="#HeaderParameter"/>
        <name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">Content-Type</name>
        <value rdf:datatype="http://www.w3.org/2001/XMLSchema#string">application/json</value>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#action_code"/>
    <owl:DatatypeProperty rdf:about="#action_name"/>
    <owl:DatatypeProperty rdf:about="#action_desc"/>
    <owl:DatatypeProperty rdf:about="#action_type"/>
    <owl:DatatypeProperty rdf:about="#version"/>
    <owl:DatatypeProperty rdf:about="#function_refs"/>
    <owl:DatatypeProperty rdf:about="#belong_entity"/>
    <owl:DatatypeProperty rdf:about="#request_url"/>
    <owl:DatatypeProperty rdf:about="#request_method"/>
    <owl:DatatypeProperty rdf:about="#script"/>
    <owl:DatatypeProperty rdf:about="#request_header"/>
    <owl:DatatypeProperty rdf:about="#request_params"/>
    <owl:DatatypeProperty rdf:about="#response_params"/>
    <owl:DatatypeProperty rdf:about="#paramCode"/>
    <owl:DatatypeProperty rdf:about="#type"/>
    <owl:DatatypeProperty rdf:about="#description"/>
    <owl:DatatypeProperty rdf:about="#isRequired"/>
    <owl:DatatypeProperty rdf:about="#mapping_path"/>
    <owl:DatatypeProperty rdf:about="#term_type_code_path"/>
    <owl:DatatypeProperty rdf:about="#library_code"/>
    <owl:DatatypeProperty rdf:about="#rel_term_codeorname"/>
    <owl:DatatypeProperty rdf:about="#term_data_type"/>
    <owl:DatatypeProperty rdf:about="#fieldCode"/>
    <owl:DatatypeProperty rdf:about="#fieldType"/>
    <owl:DatatypeProperty rdf:about="#object_property"/>
    <owl:DatatypeProperty rdf:about="#json_path"/>
    <owl:DatatypeProperty rdf:about="#name"/>
    <owl:DatatypeProperty rdf:about="#value"/>
</rdf:RDF>
"""


def render_manifest(
    *,
    source_manifest: dict[str, Any],
    output_steps: list[dict[str, Any]],
) -> str:
    """渲染目标 manifest.json。"""
    manifest = {
        "version": "1.0",
        "package_id": f"{source_manifest.get('package_id', 'json_import')}_owl",
        "description": f"{source_manifest.get('description', 'JSON 导入包')} 的 OWL 转换输出",
        "created_at": date.today().isoformat(),
        "import_steps": output_steps,
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2)


def build_manifest_steps(
    *,
    term_type_count: int,
    term_count: int,
    relation_count: int,
    datasource_count: int,
    views: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    objects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """构造 manifest.import_steps。"""
    steps: list[dict[str, Any]] = [
        {"type": "meta", "file": "meta/domains.owl", "description": "业务领域定义"},
        {"type": "meta", "file": "meta/library.owl", "description": "本体库定义"},
        {
            "type": "term_types",
            "file": "term_types/term_types.owl",
            "description": "术语类型定义",
            "count": term_type_count,
        },
        {
            "type": "terms",
            "file": "terms/terms.owl",
            "description": "本体术语定义",
            "count": term_count,
        },
        {
            "type": "relations",
            "file": "relations/relation.owl",
            "description": "对象关系定义",
            "count": relation_count,
        },
    ]
    if datasource_count > 0:
        steps.append(
            {
                "type": "ontology",
                "file": "ontology/dbsources/dbsource.owl",
                "description": "数据源定义",
                "count": datasource_count,
            }
        )
    if views:
        steps.append(
            {
                "type": "ontology",
                "file": "ontology/views/views.owl",
                "description": "视图定义",
                "count": len(views),
            }
        )
    for action in actions:
        action_code = str(action.get("action_code") or "")
        steps.append(
            {
                "type": "ontology",
                "file": f"ontology/actions/{action_code}.owl",
                "description": f"动作定义：{action.get('action_name', action_code)}",
                "count": len(action.get("params", [])),
            }
        )
    for obj in objects:
        object_code = str(obj.get("object_code") or "")
        field_count = len(obj.get("fields", []))
        steps.append(
            {
                "type": "ontology",
                "file": f"ontology/objects/{object_code}/{object_code}_object.owl",
                "description": f"对象定义：{obj.get('object_name', object_code)}",
                "count": field_count,
            }
        )
        steps.append(
            {
                "type": "ontology",
                "file": f"ontology/objects/{object_code}/{object_code}_mapping.owl",
                "description": f"对象映射：{obj.get('object_name', object_code)}",
                "count": field_count,
            }
        )
    return steps


def convert(source_dir: Path, output_dir: Path, clean: bool) -> None:
    """执行 JSON 到 OWL 的完整转换。"""
    package = load_package(source_dir)
    domains: list[DomainRecord] = package["domains"]
    libraries: list[LibraryRecord] = package["libraries"]
    objects: list[dict[str, Any]] = package["objects"]
    actions: list[dict[str, Any]] = package["actions"]
    functions: dict[str, dict[str, Any]] = package["functions"]
    views: list[dict[str, Any]] = package["views"]

    default_library_code = choose_primary_library_code(libraries)
    default_domain_code = choose_primary_domain_code(domains)
    term_types = discover_term_types(objects, actions)
    relations = collect_relations(objects, views)
    datasources = collect_datasources(objects)

    if clean:
        clean_directory(output_dir)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    write_text(output_dir / "meta" / "domains.owl", render_domains(domains))
    write_text(output_dir / "meta" / "library.owl", render_libraries(libraries))
    write_text(
        output_dir / "term_types" / "term_types.owl",
        render_term_types(term_types, default_library_code),
    )
    terms_content, term_count = render_terms(
        objects=objects,
        actions=actions,
        views=views,
        library_code=default_library_code,
        domain_code=default_domain_code,
    )
    write_text(output_dir / "terms" / "terms.owl", terms_content)
    write_text(
        output_dir / "relations" / "relation.owl",
        render_relations(relations, default_library_code),
    )
    if datasources:
        write_text(
            output_dir / "ontology" / "dbsources" / "dbsource.owl",
            render_dbsources(datasources),
        )
    if views:
        write_text(output_dir / "ontology" / "views" / "views.owl", render_views_owl(views))

    for action in actions:
        action_code = str(action.get("action_code") or "")
        function_code = next(iter(action.get("function_refs", [])), "")
        function_config = functions.get(function_code) if function_code else None
        write_text(
            output_dir / "ontology" / "actions" / f"{action_code}.owl",
            render_action_owl(action, function_config, default_library_code),
        )

    for obj in objects:
        object_code = str(obj.get("object_code") or "")
        object_dir = output_dir / "ontology" / "objects" / object_code
        write_text(
            object_dir / f"{object_code}_object.owl",
            render_object_owl(obj, default_library_code),
        )
        write_text(object_dir / f"{object_code}_mapping.owl", render_mapping_owl(obj))

    manifest_steps = build_manifest_steps(
        term_type_count=len(term_types),
        term_count=term_count,
        relation_count=len(relations),
        datasource_count=len(datasources),
        views=views,
        actions=actions,
        objects=objects,
    )
    write_text(
        output_dir / "manifest.json",
        render_manifest(source_manifest=package["manifest"], output_steps=manifest_steps),
    )

    LOGGER.info(
        "转换完成: objects=%d actions=%d views=%d relations=%d term_types=%d terms=%d",
        len(objects),
        len(actions),
        len(views),
        len(relations),
        len(term_types),
        term_count,
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="将 JSON 导入包转换为 OWL 导入包")
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="源 JSON 导入包目录",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="目标 OWL 导入包目录",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="写入前不清空目标目录",
    )
    return parser.parse_args()


def main() -> None:
    """脚本入口。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    convert(args.source, args.output, clean=not args.no_clean)


if __name__ == "__main__":
    main()
