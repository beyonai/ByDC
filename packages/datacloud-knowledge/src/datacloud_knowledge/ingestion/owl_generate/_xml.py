"""XML 工具函数。"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape


def xml_escape(value: object) -> str:
    """XML 转义。"""
    return escape(str(value), {'"': "&quot;"})


def write_text(path: Path, content: str) -> None:
    """写入文本文件，自动创建父目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def safe_xml_id(value: str, max_len: int = 200) -> str:
    """将任意字符串转为合法 XML NCName 片段。

    保留 ASCII 字母/数字/下划线 + Unicode 字母（中文等），
    其余字符替换为 ``_``。
    """
    return re.sub(r"[^\w]", "_", value, flags=re.UNICODE)[:max_len]


def map_data_type(sql_type: str, column_name: str) -> str:
    """MySQL 类型 → OWL data_type（纯值，不含选项说明）。

    修复旧脚本 bug：旧脚本会把选项说明写进值，如
    ``STRING(STRING:字符串, INT:整数, ...)``，这里只返回纯类型。
    """
    raw = sql_type.lower()
    if column_name.startswith("is_") or raw == "tinyint(1)":
        return "BOOLEAN"
    if raw.startswith(("tinyint", "int", "smallint")):
        return "INT"
    if raw.startswith("bigint"):
        return "BIGINT"
    if raw.startswith(("decimal", "double", "float", "numeric")):
        return "DOUBLE"
    if raw.startswith(("datetime", "date", "timestamp", "time")):
        return "DATE"
    return "STRING"


def map_value_format(sql_type: str) -> str:
    """推断数据格式。"""
    raw = sql_type.lower()
    if raw.startswith("date") and not raw.startswith("datetime"):
        return "yyyy-MM-dd"
    if raw.startswith(("datetime", "timestamp")):
        return "yyyy-MM-dd HH:mm:ss"
    m = re.match(r"decimal\((\d+),(\d+)\)", raw)
    if m:
        scale = int(m.group(2))
        return "#,##0" if scale == 0 else "#,##0." + ("0" * scale)
    return ""


def map_measurement_unit(comment: str) -> str:
    """从字段注释推断度量单位。"""
    units = [
        ("万元", "万元"),
        ("亩", "亩"),
        ("平米", "平方米"),
        ("平方米", "平方米"),
        ("千瓦时", "千瓦时"),
        ("吨", "吨"),
        ("公里", "公里"),
        ("人次", "人次"),
        ("辆次", "辆次"),
        ("指数", "指数"),
    ]
    for keyword, unit in units:
        if keyword in comment:
            return unit
    return ""


# ── 关系 OWL 公共片段 ────────────────────────────────────────────────────────

REL_HEADER = """\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/relation/ontology#">

    <owl:Class rdf:about="#TermRelation"><rdfs:label>术语关系</rdfs:label></owl:Class>"""

REL_PROPS = """\
    <owl:DatatypeProperty rdf:about="#source_libeary">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#source_type">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#source_code">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#target_libeary">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#target_type">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#target_code">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#relation_name">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#relation_type">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#joinkeys">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#ext_field">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#version">\
<rdfs:domain rdf:resource="#TermRelation"/>\
<rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>\
</owl:DatatypeProperty>"""


def rel_item(
    rel_id: str,
    source_lib: str,
    source_type: str,
    source_code: str,
    target_lib: str,
    target_type: str,
    target_code: str,
    rel_name: str,
    rel_type: str,
    joinkeys: str = "[]",
    ext_field: str = "",
) -> str:
    """渲染单条关系 NamedIndividual。"""
    return f"""\
    <owl:NamedIndividual rdf:about=\"#{safe_xml_id(rel_id, 200)}\">
        <rdf:type rdf:resource=\"#TermRelation\"/>
        <source_libeary rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">{xml_escape(source_lib)}</source_libeary>
        <source_type rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">{xml_escape(source_type)}</source_type>
        <source_code rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">{xml_escape(source_code)}</source_code>
        <target_libeary rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">{xml_escape(target_lib)}</target_libeary>
        <target_type rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">{xml_escape(target_type)}</target_type>
        <target_code rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">{xml_escape(target_code)}</target_code>
        <relation_name rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">{xml_escape(rel_name)}</relation_name>
        <relation_type rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">{rel_type}</relation_type>
        <joinkeys rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">{joinkeys}</joinkeys>
        <ext_field rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">{xml_escape(ext_field)}</ext_field>
        <version rdf:datatype=\"http://www.w3.org/2001/XMLSchema#string\">1.0</version>
    </owl:NamedIndividual>"""


def wrap_rel(items: list[str]) -> str:
    """将关系条目列表包装为完整 OWL 文档。"""
    body = "\n".join(items)
    return f"{REL_HEADER}\n\n{body}\n\n{REL_PROPS}\n</rdf:RDF>\n"
