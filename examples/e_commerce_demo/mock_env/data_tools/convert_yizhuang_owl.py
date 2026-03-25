"""Generate OWL v4 package from DDL + real CSV data for the mock_env."""

from __future__ import annotations

import csv
import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

PACKAGE_ID = "e_commerce_demo_owl_v4_init_20260325"
PACKAGE_DATE = "2026-03-25"
DOMAIN_CODE = "DOMAIN_002"
DOMAIN_NAME = "产业管理"
PARENT_DOMAIN_CODE = "DOMAIN_001"
LIBRARY_CODE = "LIB_002"
LIBRARY_NAME = "产业大脑"
LIBRARY_DESC = "基于 DDL 与真实 CSV 数据生成的亦庄产业大脑 OWL v4 导入包"
DB_CODE = "resource_csv"
DB_TYPE = "csv"

DATA_TYPE_DESC = {
    "BIGINT": "BIGINT(BIGINT:长整形，INT:整形, DOUBLE: 浮点形，STRING:字符，BOOLEAN:布尔，DATE:时间)",
    "INT": "INT(BIGINT:长整形，INT:整形, DOUBLE: 浮点形，STRING:字符，BOOLEAN:布尔，DATE:时间)",
    "DOUBLE": "DOUBLE(BIGINT:长整形，INT:整形, DOUBLE: 浮点形，STRING:字符，BOOLEAN:布尔，DATE:时间)",
    "STRING": "STRING(BIGINT:长整形，INT:整形, DOUBLE: 浮点形，STRING:字符，BOOLEAN:布尔，DATE:时间)",
    "BOOLEAN": "BOOLEAN(BIGINT:长整形，INT:整形, DOUBLE: 浮点形，STRING:字符，BOOLEAN:布尔，DATE:时间)",
    "DATE": "DATE(BIGINT:长整形，INT:整形, DOUBLE: 浮点形，STRING:字符，BOOLEAN:布尔，DATE:时间)",
}

ONTOLOGY_TERM_TYPES = [
    {"code": "VIEW", "name": "视图", "desc": "视图", "data_type": "ONTOLOGY_TERM"},
    {"code": "OBJECT", "name": "对象", "desc": "对象", "data_type": "ONTOLOGY_TERM"},
    {"code": "ACTIOIN", "name": "动作", "desc": "动作", "data_type": "ONTOLOGY_TERM"},
    {"code": "FUNCTION", "name": "函数", "desc": "函数", "data_type": "ONTOLOGY_TERM"},
    {"code": "PROPERTY", "name": "属性", "desc": "属性", "data_type": "ONTOLOGY_TERM"},
]

TERM_COLUMN_CONFIG = {
    "dws_enterprise_wide": {
        "enterprise_name": {"type_code": "ENTERPRISE_NAME", "type_name": "企业名称", "data_type": "LIST_TERM"},
        "industry_name": {"type_code": "INDUSTRY_NAME", "type_name": "行业名称", "data_type": "LIST_TERM"},
        "grid_name": {"type_code": "GRID_NAME", "type_name": "经营网格名称", "data_type": "LIST_TERM"},
        "bus_adress": {"type_code": "BUS_ADDRESS", "type_name": "经营地址", "data_type": "LIST_TERM"},
        "reg_address": {"type_code": "REG_ADDRESS", "type_name": "注册地址", "data_type": "LIST_TERM"},
        "chain_name": {"type_code": "CHAIN_NAME", "type_name": "产业链环节名称", "data_type": "LIST_TERM"},
        "upstream_chain_name": {"type_code": "UPSTREAM_CHAIN_NAME", "type_name": "上游环节名称", "data_type": "LIST_TERM"},
        "downstream_chain_name": {"type_code": "DOWNSTREAM_CHAIN_NAME", "type_name": "下游环节名称", "data_type": "LIST_TERM"},
        "risk_level": {"type_code": "RISK_LEVEL", "type_name": "企业风险等级", "data_type": "LIST_TERM"},
        "is_scale_enterprise": {"type_code": "IS_SCALE_ENTERPRISE", "type_name": "规上企业标识", "data_type": "LIST_TERM"},
        "is_high_tech": {"type_code": "IS_HIGH_TECH", "type_name": "高新企业标识", "data_type": "LIST_TERM"},
        "is_listed": {"type_code": "IS_LISTED", "type_name": "是否上市", "data_type": "LIST_TERM"},
        "is_leading": {"type_code": "IS_LEADING", "type_name": "是否龙头", "data_type": "LIST_TERM"},
        "is_risk": {"type_code": "IS_RISK", "type_name": "是否风险企业", "data_type": "LIST_TERM"},
        "enterprise_level": {"type_code": "ENTERPRISE_LEVEL", "type_name": "企业级别", "data_type": "LIST_TERM"},
        "data_source": {"type_code": "DATA_SOURCE", "type_name": "数据来源", "data_type": "LIST_TERM"},
        "latest_risk_type_name": {"type_code": "LATEST_RISK_TYPE_NAME", "type_name": "最新风险模式名", "data_type": "LIST_TERM"},
        "leading_levels": {"type_code": "LEADING_LEVELS", "type_name": "龙头等级聚合", "data_type": "LIST_TERM"},
    },
    "dws_grid_wide": {
        "grid_name": {"type_code": "GRID_NAME", "type_name": "网格名称", "data_type": "LIST_TERM"},
        "region_name": {"type_code": "REGION_NAME", "type_name": "区域名称", "data_type": "LIST_TERM"},
    },
    "dws_industry_wide": {
        "chain_name": {"type_code": "CHAIN_NAME", "type_name": "产业链名称", "data_type": "LIST_TERM"},
        "parent_chain_name": {"type_code": "PARENT_CHAIN_NAME", "type_name": "父产业链名称", "data_type": "LIST_TERM"},
        "chain_level": {"type_code": "CHAIN_LEVEL", "type_name": "产业链层级", "data_type": "DICT_TERM"},
    },
}

OBJECT_ACTIONS = {
    "dws_enterprise_wide": [
        {
            "code": "query_enterprise_by_name_or_id",
            "name": "按名称或ID查询企业",
            "desc": "按企业ID列表或企业名称列表批量查询企业详情",
            "request_fields": ["enterprise_id", "enterprise_name", "data_year"],
            "response_fields": ["enterprise_id", "enterprise_name", "risk_level", "chain_name", "grid_name"],
        },
        {
            "code": "query_enterprise_risk_profile",
            "name": "查询企业风险画像",
            "desc": "读取企业风险等级、风险类型、风险研判摘要等信息",
            "request_fields": ["enterprise_id", "enterprise_name", "data_year"],
            "response_fields": ["risk_score", "risk_level", "latest_risk_type_name", "latest_pattern_name", "latest_judgment_summary"],
        },
    ],
    "dws_grid_wide": [
        {
            "code": "query_grid_by_name_or_id",
            "name": "按名称或ID查询网格",
            "desc": "按网格ID列表或网格名称列表批量查询网格详情",
            "request_fields": ["grid_id", "grid_name", "data_year"],
            "response_fields": ["grid_id", "grid_name", "region_name", "enterprise_cnt", "vitality_idx"],
        },
        {
            "code": "query_grid_vitality_profile",
            "name": "查询网格活力画像",
            "desc": "读取网格人流、车流、夜光、物流热力和活力指数等指标",
            "request_fields": ["grid_id", "grid_name", "data_year"],
            "response_fields": ["vitality_idx", "human_flow_idx", "traffic_flow_idx_day", "night_light_idx_day", "logistics_heat_idx_day"],
        },
    ],
    "dws_industry_wide": [
        {
            "code": "query_industry_by_name_or_id",
            "name": "按名称或ID查询产业链",
            "desc": "按产业链ID列表或产业链名称列表批量查询产业链详情",
            "request_fields": ["chain_id", "chain_name", "data_year"],
            "response_fields": ["chain_id", "chain_name", "chain_level", "enterprise_cnt", "relation_strength_sum"],
        },
        {
            "code": "query_industry_relation_profile",
            "name": "查询产业链关系画像",
            "desc": "读取产业链上下游供需关系、链内关系数和关系强度等信息",
            "request_fields": ["chain_id", "chain_name", "data_year"],
            "response_fields": ["intra_chain_rel_cnt", "supplier_rel_out_cnt", "buyer_rel_out_cnt", "relation_strength_sum", "chain_level"],
        },
    ],
}


@dataclass
class ColumnDef:
    name: str
    sql_type: str
    nullable: bool
    comment: str
    default: str
    is_primary_key: bool = False


@dataclass
class TableDef:
    name: str
    comment: str
    columns: list[ColumnDef]


def xml_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return escape(json.dumps(value, ensure_ascii=False))
    if isinstance(value, bool):
        return "true" if value else "false"
    return escape(str(value))


def literal(name: str, value: object, datatype: str = "string", indent: str = "        ") -> str:
    return f'{indent}<{name} rdf:datatype="http://www.w3.org/2001/XMLSchema#{datatype}">{xml_value(value)}</{name}>'


def owl_document(xml_base: str, body: str) -> str:
    return (
        '<?xml version="1.0"?>\n'
        '<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"\n'
        '         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
        '         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"\n'
        '         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"\n'
        f'         xml:base="{xml_base}">\n\n'
        f"{body.rstrip()}\n"
        "</rdf:RDF>\n"
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("Wrote %s", path)


def safe_id(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z_]+", "_", text)
    return value.strip("_") or "item"


def snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def normalize_sql_type(sql_type: str) -> str:
    lowered = sql_type.lower()
    if lowered.startswith("bigint"):
        return "BIGINT"
    if lowered.startswith(("int", "tinyint", "smallint")):
        return "INT"
    if lowered.startswith(("decimal", "double", "float")):
        return "DOUBLE"
    if lowered.startswith(("date", "datetime", "timestamp")):
        return "DATE"
    if lowered.startswith("boolean"):
        return "BOOLEAN"
    return "STRING"


def xsd_range_for_sql(sql_type: str) -> str:
    normalized = normalize_sql_type(sql_type)
    if normalized == "BIGINT":
        return "http://www.w3.org/2001/XMLSchema#long"
    if normalized == "INT":
        return "http://www.w3.org/2001/XMLSchema#integer"
    if normalized == "DOUBLE":
        return "http://www.w3.org/2001/XMLSchema#decimal"
    if normalized == "BOOLEAN":
        return "http://www.w3.org/2001/XMLSchema#boolean"
    if normalized == "DATE":
        lowered = sql_type.lower()
        if lowered.startswith(("datetime", "timestamp")):
            return "http://www.w3.org/2001/XMLSchema#dateTime"
        return "http://www.w3.org/2001/XMLSchema#date"
    return "http://www.w3.org/2001/XMLSchema#string"


def infer_data_format(sql_type: str) -> str:
    lowered = sql_type.lower()
    if lowered.startswith("date") and not lowered.startswith("datetime"):
        return "yyyy-MM-dd"
    if lowered.startswith(("datetime", "timestamp")):
        return "yyyy-MM-dd HH:mm:ss"
    if lowered.startswith("decimal"):
        match = re.search(r"\((\d+),(\d+)\)", lowered)
        if match:
            scale = int(match.group(2))
            return "0." + ("0" * scale) if scale else "0"
    return ""


def infer_property_category(comment: str, column_name: str) -> str:
    if column_name.startswith("is_") or "等级" in comment or "标识" in comment:
        return "标签"
    if column_name.endswith("_cnt") or column_name.endswith("_count") or "数量" in comment:
        return "度量"
    if "指数" in comment or "评分" in comment or "营收" in comment or "税额" in comment:
        return "指标"
    return "属性"


def infer_property_group(column_name: str) -> str:
    if column_name == "output_per_mu":
        return "COMPUTE(STORAGE:存储属性,COMPUTE:计算属性)"
    return "STORAGE(STORAGE:存储属性,COMPUTE:计算属性)"


def term_type_config_for(table_name: str, column_name: str) -> dict | None:
    return TERM_COLUMN_CONFIG.get(table_name, {}).get(column_name)


def term_type_code_path(table_name: str, column_name: str) -> str:
    config = term_type_config_for(table_name, column_name)
    return f"{LIBRARY_CODE}#{config['type_code']}" if config else f"{LIBRARY_CODE}#PROPERTY"


def parse_ddl(path: Path) -> TableDef:
    text = path.read_text(encoding="utf-8")
    table_match = re.search(
        r"CREATE TABLE `[^`]+`\.`(?P<name>[^`]+)` \((?P<body>.*)\)\s*ENGINE=.*?COMMENT='(?P<comment>[^']*)';",
        text,
        re.S,
    )
    if not table_match:
        raise ValueError(f"Failed to parse DDL: {path}")
    body = table_match.group("body")
    primary_keys: set[str] = set()
    pk_match = re.search(r"PRIMARY KEY \((?P<keys>[^)]+)\)", body)
    if pk_match:
        for item in pk_match.group("keys").split(","):
            primary_keys.add(item.strip().strip("`"))

    columns: list[ColumnDef] = []
    for line in body.splitlines():
        line = line.rstrip().rstrip(",")
        if not line.lstrip().startswith("`"):
            continue
        match = re.match(r"\s*`(?P<name>[^`]+)`\s+(?P<type>[^\s]+(?:\([^)]+\))?)\s+(?P<rest>.*)$", line)
        if not match:
            continue
        rest = match.group("rest")
        default_match = re.search(r"DEFAULT\s+([^ ]+|CURRENT_TIMESTAMP)", rest, re.I)
        comment_match = re.search(r"COMMENT\s+'([^']*)'", rest)
        columns.append(
            ColumnDef(
                name=match.group("name"),
                sql_type=match.group("type").upper(),
                nullable="NOT NULL" not in rest.upper(),
                comment=comment_match.group(1) if comment_match else "",
                default=default_match.group(1) if default_match else "",
                is_primary_key=match.group("name") in primary_keys,
            )
        )
    return TableDef(name=table_match.group("name"), comment=table_match.group("comment"), columns=columns)


def find_csv(data_dir: Path, table_name: str) -> Path:
    matches = sorted(data_dir.glob(f"{table_name}*.csv"))
    if not matches:
        raise FileNotFoundError(f"CSV not found for {table_name}")
    return matches[0]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        return [{k: (v if v is not None else "") for k, v in row.items()} for row in csv.DictReader(f)]


def sample_stats(rows: list[dict[str, str]], column_name: str) -> dict[str, object]:
    values = [row.get(column_name, "").strip() for row in rows]
    non_empty = [v for v in values if v]
    return {
        "sample_value": non_empty[0] if non_empty else "",
        "non_null_count": len(non_empty),
        "unique_count": len(set(non_empty)),
    }


def build_term_types() -> list[dict]:
    rows = list(ONTOLOGY_TERM_TYPES)
    seen: set[str] = {row["code"] for row in rows}
    for table_name in sorted(TERM_COLUMN_CONFIG):
        for config in TERM_COLUMN_CONFIG[table_name].values():
            if config["type_code"] in seen:
                continue
            seen.add(config["type_code"])
            rows.append(
                {
                    "code": config["type_code"],
                    "name": config["type_name"],
                    "desc": f"{config['type_name']}术语类型",
                    "data_type": config["data_type"],
                }
            )
    return rows


def build_term_knowledge_map(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    result: dict[str, list[dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        code = item.get("term_code")
        content = item.get("content") or item.get("knowledge") or ""
        title = item.get("title") or item.get("name") or item.get("knowledge_name") or code or "知识"
        if not code or not content:
            continue
        result.setdefault(code, []).append({"name": title, "content": content})
    return result


def build_terms(all_rows: dict[str, list[dict[str, str]]], tables: list[TableDef], term_knowledge: dict[str, list[dict]]) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for table_name, config_map in TERM_COLUMN_CONFIG.items():
        for column_name, config in config_map.items():
            for row in all_rows[table_name]:
                value = row.get(column_name, "").strip()
                if not value:
                    continue
                key = (config["type_code"], value)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "term_code_path": f"{config['type_code']}#{value}",
                        "term_code": value,
                        "term_name": value,
                        "library_code": LIBRARY_CODE,
                        "term_type_code": config["type_code"],
                        "term_desc": f"来源于 {table_name}.{column_name} 的真实数据值",
                        "synonyms": "[]",
                        "terms_knowledge": term_knowledge.get(value, []),
                        "ext_field": {"source_table": table_name, "source_column": column_name},
                    }
                )

    for table in tables:
        rows.append(
            {
                "term_code_path": f"OBJECT#{table.name}",
                "term_code": table.name,
                "term_name": table.comment or table.name,
                "library_code": LIBRARY_CODE,
                "term_type_code": "OBJECT",
                "term_desc": f"来源于表 {table.name} 的对象定义",
                "synonyms": "[]",
                "terms_knowledge": [],
                "ext_field": {"source_table": table.name},
            }
        )
    rows.append(
        {
            "term_code_path": "VIEW#scene_01_data_analysis",
            "term_code": "scene_01_data_analysis",
            "term_name": "产业在线查数分析场景",
            "library_code": LIBRARY_CODE,
            "term_type_code": "VIEW",
            "term_desc": "基于企业、网格、产业链三张 DWS 宽表的在线查数分析场景",
            "synonyms": "[]",
            "terms_knowledge": [],
            "ext_field": {"object_codes": ["dws_enterprise_wide", "dws_grid_wide", "dws_industry_wide"]},
        }
    )
    return rows


def build_view() -> dict:
    return {
        "view_code": "scene_01_data_analysis",
        "view_name": "产业在线查数分析场景",
        "description": "基于企业、网格、产业链三张 DWS 宽表的在线查数分析场景",
        "object_codes": ["dws_enterprise_wide", "dws_grid_wide", "dws_industry_wide"],
        "relations": [
            "rel_dws_enterprise_wide__dws_grid_wide_0",
            "rel_dws_enterprise_wide__dws_industry_wide_1",
            "rel_dws_industry_wide__dws_industry_wide_2",
        ],
    }


def build_relation_rows() -> list[dict]:
    return [
        {
            "source_libeary": LIBRARY_CODE,
            "source_type": "对象",
            "source_code": "dws_enterprise_wide",
            "target_libeary": LIBRARY_CODE,
            "target_type": "对象",
            "target_code": "dws_grid_wide",
            "relation_name": "企业归属网格（按年）",
            "joinkeys": [{"sourceField": "gridId", "targetField": "gridId"}, {"sourceField": "dataYear", "targetField": "dataYear"}],
            "ext_field": "",
        },
        {
            "source_libeary": LIBRARY_CODE,
            "source_type": "对象",
            "source_code": "dws_enterprise_wide",
            "target_libeary": LIBRARY_CODE,
            "target_type": "对象",
            "target_code": "dws_industry_wide",
            "relation_name": "企业归属产业链环节（按年）",
            "joinkeys": [{"sourceField": "chainId", "targetField": "chainId"}, {"sourceField": "dataYear", "targetField": "dataYear"}],
            "ext_field": "",
        },
        {
            "source_libeary": LIBRARY_CODE,
            "source_type": "对象",
            "source_code": "dws_industry_wide",
            "target_libeary": LIBRARY_CODE,
            "target_type": "对象",
            "target_code": "dws_industry_wide",
            "relation_name": "产业链父子层级（按年）",
            "joinkeys": [{"sourceField": "parentChainId", "targetField": "chainId"}, {"sourceField": "dataYear", "targetField": "dataYear"}],
            "ext_field": "",
        },
    ]


def build_field_definition(table_name: str, column: ColumnDef, rows: list[dict[str, str]]) -> dict:
    field = {
        "property_code": snake_to_camel(column.name),
        "property_name": column.comment or column.name,
        "data_type": DATA_TYPE_DESC[normalize_sql_type(column.sql_type)],
        "is_required": not column.nullable,
        "default_value": column.default.strip("'"),
        "source_column": column.name,
        "synonyms": "",
        "data_format": infer_data_format(column.sql_type),
        "term_type_code_path": term_type_code_path(table_name, column.name),
        "library_code": LIBRARY_CODE,
        "ext_field": sample_stats(rows, column.name),
        "property_category": infer_property_category(column.comment, column.name),
        "property_group": infer_property_group(column.name),
    }
    if column.name == "output_per_mu":
        field["rel_action"] = ["compute_output_per_mu"]
    return field


def build_request_params(table_name: str, field_names: list[str], columns_by_name: dict[str, ColumnDef]) -> list[dict]:
    params: list[dict] = []
    for field_name in field_names:
        column = columns_by_name[field_name]
        params.append(
            {
                "paramCode": snake_to_camel(field_name),
                "type": normalize_sql_type(column.sql_type).lower(),
                "description": column.comment or field_name,
                "isRequired": field_name.endswith("_id") or field_name.endswith("_name"),
                "term_type_code_path": term_type_code_path(table_name, field_name),
                "library_code": LIBRARY_CODE,
                "rel_term_codeorname": "",
            }
        )
    return params


def build_response_params(table_name: str, field_names: list[str], columns_by_name: dict[str, ColumnDef]) -> list[dict]:
    params: list[dict] = []
    for field_name in field_names:
        column = columns_by_name[field_name]
        params.append(
            {
                "fieldCode": snake_to_camel(field_name),
                "fieldType": normalize_sql_type(column.sql_type).lower(),
                "term_type_code_path": term_type_code_path(table_name, field_name),
                "library_code": LIBRARY_CODE,
                "object_property": field_name,
                "json_path": f"data.{snake_to_camel(field_name)}",
            }
        )
    return params


def render_domains() -> str:
    body = "\n".join(
        [
            '    <owl:Class rdf:about="#DomainDefinition"><rdfs:label>领域定义</rdfs:label></owl:Class>',
            '    <owl:DatatypeProperty rdf:about="#domain_code"><rdfs:domain rdf:resource="#DomainDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#domain_name"><rdfs:domain rdf:resource="#DomainDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#parent_domain_code"><rdfs:domain rdf:resource="#DomainDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#remark"><rdfs:domain rdf:resource="#DomainDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#DomainDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:NamedIndividual rdf:about="#domain_002">',
            '        <rdf:type rdf:resource="#DomainDefinition"/>',
            literal("domain_code", DOMAIN_CODE),
            literal("domain_name", DOMAIN_NAME),
            literal("parent_domain_code", PARENT_DOMAIN_CODE),
            literal("remark", "亦庄产业大脑领域"),
            literal("version", "1.0"),
            "    </owl:NamedIndividual>",
        ]
    )
    return owl_document("http://example.org/domain/ontology#", body)


def render_library() -> str:
    body = "\n".join(
        [
            '    <owl:Class rdf:about="#LibraryDefinition"><rdfs:label>本体库定义</rdfs:label></owl:Class>',
            '    <owl:DatatypeProperty rdf:about="#library_code"><rdfs:domain rdf:resource="#LibraryDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#library_name"><rdfs:domain rdf:resource="#LibraryDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#library_desc"><rdfs:domain rdf:resource="#LibraryDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#LibraryDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:NamedIndividual rdf:about="#lib_002">',
            '        <rdf:type rdf:resource="#LibraryDefinition"/>',
            literal("library_code", LIBRARY_CODE),
            literal("library_name", LIBRARY_NAME),
            literal("library_desc", LIBRARY_DESC),
            literal("version", "1.0"),
            "    </owl:NamedIndividual>",
        ]
    )
    return owl_document("http://example.org/library/ontology#", body)


def render_term_types(rows: list[dict]) -> str:
    parts = ['    <owl:Class rdf:about="#TermTypeDefinition"><rdfs:label>术语类型定义</rdfs:label></owl:Class>']
    for row in rows:
        parts.extend(
            [
                f'    <owl:NamedIndividual rdf:about="#termtype_{safe_id(row["code"]).lower()}">',
                '        <rdf:type rdf:resource="#TermTypeDefinition"/>',
                literal("trem_type_code_path", f"{LIBRARY_CODE}#{row['code']}"),
                literal("trem_type_code", row["code"]),
                literal("trem_type_name", row["name"]),
                literal("trem_type_desc", row["desc"]),
                literal("trem_data_type", row["data_type"]),
                literal("version", "1.0"),
                "    </owl:NamedIndividual>",
            ]
        )
    parts.extend(
        [
            '    <owl:DatatypeProperty rdf:about="#trem_type_code_path"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#trem_type_code"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#trem_type_name"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#trem_type_desc"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#trem_data_type"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        ]
    )
    return owl_document("http://example.org/termtype/ontology#", "\n".join(parts))


def render_terms(rows: list[dict]) -> str:
    parts = ['    <owl:Class rdf:about="#TermDefinition"><rdfs:label>术语定义</rdfs:label></owl:Class>']
    for idx, row in enumerate(rows, start=1):
        parts.extend(
            [
                f'    <owl:NamedIndividual rdf:about="#term_{idx}">',
                '        <rdf:type rdf:resource="#TermDefinition"/>',
                literal("term_code_path", row["term_code_path"]),
                literal("term_code", row["term_code"]),
                literal("term_name", row["term_name"]),
                literal("library_code", row["library_code"]),
                literal("term_type_code", row["term_type_code"]),
                literal("term_desc", row["term_desc"]),
                literal("synonyms", row["synonyms"]),
                literal("terms_knowledge", row["terms_knowledge"]),
                literal("ext_field", row["ext_field"]),
                literal("version", "1.0"),
                "    </owl:NamedIndividual>",
            ]
        )
    parts.extend(
        [
            '    <owl:DatatypeProperty rdf:about="#term_code_path"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#term_code"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#term_name"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#library_code"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#term_type_code"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#term_desc"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#synonyms"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#terms_knowledge"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#ext_field"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        ]
    )
    return owl_document("http://example.org/term/ontology#", "\n".join(parts))


def render_actions(tables: list[TableDef]) -> str:
    table_map = {table.name: table for table in tables}
    parts = ['    <owl:Class rdf:about="#ActionDefinition"><rdfs:label>动作定义</rdfs:label></owl:Class>']
    for table_name, actions in OBJECT_ACTIONS.items():
        columns_by_name = {column.name: column for column in table_map[table_name].columns}
        for action in actions:
            parts.extend(
                [
                    f'    <owl:NamedIndividual rdf:about="#action_{action["code"]}">',
                    '        <rdf:type rdf:resource="#ActionDefinition"/>',
                    literal("action_code", action["code"]),
                    literal("action_name", action["name"]),
                    literal("action_desc", action["desc"]),
                    literal("action_type", "QUERY(UPDATE:操作, QUERY:查询)"),
                    literal("version", "1.0"),
                    literal("function_refs", []),
                    literal("belong_entity", [table_name]),
                    literal("request_url", f"http://127.0.0.1/{action['code']}"),
                    literal("request_method", "POST"),
                    literal("request_header", [{"Content-Type": "application/json"}]),
                    literal("request_params", build_request_params(table_name, action["request_fields"], columns_by_name)),
                    literal("response_params", build_response_params(table_name, action["response_fields"], columns_by_name)),
                    "    </owl:NamedIndividual>",
                ]
            )
    parts.extend(
        [
            '    <owl:DatatypeProperty rdf:about="#action_code"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#action_name"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#action_desc"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#action_type"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#function_refs"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#belong_entity"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#request_url"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#request_method"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#request_header"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#request_params"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#response_params"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        ]
    )
    return owl_document("http://example.org/action/ontology#", "\n".join(parts))


def render_dbsource(data_dir: Path) -> str:
    params = [
        {"paramName": "dataDir", "paramValue": str(data_dir)},
        {"paramName": "pattern", "paramValue": "*.csv"},
        {"paramName": "encoding", "paramValue": "utf-8"},
    ]
    body = "\n".join(
        [
            '    <owl:Class rdf:about="#DatabaseDefinition"><rdfs:label>数据源信息定义</rdfs:label></owl:Class>',
            '    <owl:NamedIndividual rdf:about="#database_resource_csv">',
            '        <rdf:type rdf:resource="#DatabaseDefinition"/>',
            literal("dbCode", DB_CODE),
            literal("dbType", DB_TYPE),
            literal("dbParams", params),
            "    </owl:NamedIndividual>",
            '    <owl:DatatypeProperty rdf:about="#dbCode"><rdfs:domain rdf:resource="#DatabaseDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#dbType"><rdfs:domain rdf:resource="#DatabaseDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#dbParams"><rdfs:domain rdf:resource="#DatabaseDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        ]
    )
    return owl_document("http://example.org/database/ontology#", body)


def render_object(table: TableDef, rows: list[dict[str, str]]) -> str:
    fields = [build_field_definition(table.name, column, rows) for column in table.columns]
    relations: list[str]
    if table.name == "dws_enterprise_wide":
        relations = ["rel_dws_enterprise_wide__dws_grid_wide_0", "rel_dws_enterprise_wide__dws_industry_wide_1"]
    elif table.name == "dws_grid_wide":
        relations = ["rel_dws_enterprise_wide__dws_grid_wide_0"]
    else:
        relations = ["rel_dws_enterprise_wide__dws_industry_wide_1", "rel_dws_industry_wide__dws_industry_wide_2"]

    body_parts = [
        '    <owl:Class rdf:about="#EntityDefinition"><rdfs:label>实体定义</rdfs:label></owl:Class>',
        '    <owl:Class rdf:about="#EntityField"><rdfs:label>实体字段</rdfs:label></owl:Class>',
        f'    <owl:NamedIndividual rdf:about="#{table.name}_v4">',
        '        <rdf:type rdf:resource="#EntityDefinition"/>',
        literal("entity_code", table.name),
        literal("entity_name", table.comment or table.name),
        literal("entity_desc", f"基于真实 CSV 数据和 DDL 生成的 {table.comment or table.name}"),
        literal("version", "1.0"),
    "    </owl:NamedIndividual>",
        '    <owl:DatatypeProperty rdf:about="#entity_code"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#entity_name"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#entity_desc"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:ObjectProperty rdf:about="#has_field"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="#EntityField"/></owl:ObjectProperty>',
        '    <owl:DatatypeProperty rdf:about="#action_ref"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#relation_ref"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#property_code"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#property_name"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#data_type"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#is_required"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#boolean"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#default_value"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#source_column"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#synonyms"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#data_format"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#term_type_code_path"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#library_code"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#sample_value"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#non_null_count"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#integer"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#unique_count"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#integer"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#property_category"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#property_group"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        '    <owl:DatatypeProperty rdf:about="#rel_action"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
    ]
    for action_code in [item["code"] for item in OBJECT_ACTIONS[table.name]]:
        body_parts.append(literal("action_ref", action_code))
    for relation_code in relations:
        body_parts.append(literal("relation_ref", relation_code))
    for field in fields:
        field_id = f'{table.name}_{field["property_code"]}_field'
        body_parts.extend(
            [
                f'    <owl:NamedIndividual rdf:about="#{field_id}">',
                '        <rdf:type rdf:resource="#EntityField"/>',
                literal("property_code", field["property_code"]),
                literal("property_name", field["property_name"]),
                literal("data_type", field["data_type"]),
                literal("is_required", field["is_required"], datatype="boolean"),
                literal("default_value", field["default_value"]),
                literal("source_column", field["source_column"]),
                literal("synonyms", field["synonyms"]),
                literal("data_format", field["data_format"]),
                literal("term_type_code_path", field["term_type_code_path"]),
                literal("library_code", field["library_code"]),
                literal("sample_value", field["ext_field"]["sample_value"]),
                literal("non_null_count", field["ext_field"]["non_null_count"], datatype="integer"),
                literal("unique_count", field["ext_field"]["unique_count"], datatype="integer"),
                literal("property_category", field["property_category"]),
                literal("property_group", field["property_group"]),
            ]
        )
        for rel_action in field.get("rel_action", []):
            body_parts.append(literal("rel_action", rel_action))
        body_parts.append("    </owl:NamedIndividual>")
        body_parts.append(f'    <has_field rdf:resource="#{field_id}"/>')
    for column in table.columns:
        property_code = snake_to_camel(column.name)
        body_parts.extend(
            [
                f'    <owl:DatatypeProperty rdf:about="#{property_code}">',
                f'        <rdfs:label>{escape(column.comment or property_code)}</rdfs:label>',
                '        <rdfs:domain rdf:resource="#EntityDefinition"/>',
                f'        <rdfs:range rdf:resource="{xsd_range_for_sql(column.sql_type)}"/>',
                "    </owl:DatatypeProperty>",
            ]
        )
    body = "\n".join(body_parts)
    return owl_document("http://example.org/entity/ontology#", body)


def render_mapping(table: TableDef) -> str:
    mapping = [
        {
            "property_code": snake_to_camel(column.name),
            "property_name": column.comment or column.name,
            "source_table_code": table.name,
            "source_column_code": column.name,
            "source_datasource_code": DB_CODE,
        }
        for column in table.columns
    ]
    body = "\n".join(
        [
            '    <owl:Class rdf:about="#EntityMapping"><rdfs:label>实体映射</rdfs:label></owl:Class>',
            f'    <owl:NamedIndividual rdf:about="#{table.name}_mapping">',
            '        <rdf:type rdf:resource="#EntityMapping"/>',
            literal("entity_code", table.name),
            literal("entity_name", table.comment or table.name),
            literal("entity_desc", f"{table.comment or table.name}字段映射定义"),
            literal("version", "1.0"),
            literal("mapping", mapping),
            "    </owl:NamedIndividual>",
            '    <owl:DatatypeProperty rdf:about="#entity_code"><rdfs:domain rdf:resource="#EntityMapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#entity_name"><rdfs:domain rdf:resource="#EntityMapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#entity_desc"><rdfs:domain rdf:resource="#EntityMapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#EntityMapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#mapping"><rdfs:domain rdf:resource="#EntityMapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        ]
    )
    return owl_document("http://example.org/entity/ontology#", body)


def render_view(view: dict) -> str:
    body = "\n".join(
        [
            '    <owl:Class rdf:about="#SceneDefinition"><rdfs:label>视图定义</rdfs:label></owl:Class>',
            '    <owl:NamedIndividual rdf:about="#scene_01_data_analysis_v4">',
            '        <rdf:type rdf:resource="#SceneDefinition"/>',
            literal("view_code", view["view_code"]),
            literal("view_name", view["view_name"]),
            literal("description", view["description"]),
            literal("version", "1.0"),
            literal("object_codes", view["object_codes"]),
            literal("relations", view["relations"]),
            "    </owl:NamedIndividual>",
            '    <owl:DatatypeProperty rdf:about="#view_code"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#view_name"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#description"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#object_codes"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#relations"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        ]
    )
    return owl_document("http://example.org/scene/ontology#", body)


def render_relations(rows: list[dict]) -> str:
    parts = ['    <owl:Class rdf:about="#TermRelation"><rdfs:label>术语关系</rdfs:label></owl:Class>']
    for idx, row in enumerate(rows, start=1):
        parts.extend(
            [
                f'    <owl:NamedIndividual rdf:about="#term_relation_{idx}">',
                '        <rdf:type rdf:resource="#TermRelation"/>',
                literal("source_libeary", row["source_libeary"]),
                literal("source_type", row["source_type"]),
                literal("source_code", row["source_code"]),
                literal("target_libeary", row["target_libeary"]),
                literal("target_type", row["target_type"]),
                literal("target_code", row["target_code"]),
                literal("relation_name", row["relation_name"]),
                literal("joinkeys", row["joinkeys"]),
                literal("ext_field", row["ext_field"]),
                literal("version", "1.0"),
                "    </owl:NamedIndividual>",
            ]
        )
    parts.extend(
        [
            '    <owl:DatatypeProperty rdf:about="#source_libeary"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#source_type"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#source_code"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#target_libeary"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#target_type"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#target_code"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#relation_name"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#joinkeys"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#ext_field"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
            '    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#TermRelation"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>',
        ]
    )
    return owl_document("http://example.org/relation/ontology#", "\n".join(parts))


def build_manifest() -> dict:
    return {
        "version": "1.0",
        "package_id": PACKAGE_ID,
        "description": "基于 DDL 和真实 CSV 数据生成的亦庄产业大脑 OWL v4 导入包",
        "created_at": PACKAGE_DATE,
        "import_steps": [
            {"type": "meta", "file": "meta/domains.owl", "description": "业务领域定义"},
            {"type": "meta", "file": "meta/library.owl", "description": "知识库定义"},
            {"type": "term_types", "file": "term_types/term_types.owl", "description": "用户自定义术语类型"},
            {"type": "terms", "file": "terms/terms.owl", "description": "本体术语"},
            {"type": "objects", "file": "ontology/objects/dws_enterprise_wide/dws_enterprise_wide_object.owl", "description": "企业对象"},
            {"type": "objects", "file": "ontology/objects/dws_enterprise_wide/dws_enterprise_wide_mapping.owl", "description": "企业映射"},
            {"type": "objects", "file": "ontology/objects/dws_grid_wide/dws_grid_wide_object.owl", "description": "网格对象"},
            {"type": "objects", "file": "ontology/objects/dws_grid_wide/dws_grid_wide_mapping.owl", "description": "网格映射"},
            {"type": "objects", "file": "ontology/objects/dws_industry_wide/dws_industry_wide_object.owl", "description": "产业链对象"},
            {"type": "objects", "file": "ontology/objects/dws_industry_wide/dws_industry_wide_mapping.owl", "description": "产业链映射"},
            {"type": "objects", "file": "ontology/actions/action.owl", "description": "本体动作"},
            {"type": "dbsources", "file": "ontology/dbsources/dbsource.owl", "description": "数据源定义"},
            {"type": "objects", "file": "ontology/views/views.owl", "description": "本体视图"},
            {"type": "relations", "file": "relations/relation.owl", "description": "本体关系"},
        ],
    }


def generate() -> Path:
    mock_root = Path(__file__).resolve().parent.parent
    ddl_dir = mock_root / "db" / "ddl" / "tables"
    data_dir = mock_root / "resource" / "data"
    term_knowledge_path = mock_root / "resource" / "knowledge" / "import_package" / "knowledge" / "term_knowledge.jsonl"
    out_root = mock_root / "resource" / "knowledge" / "import_package_owl"

    if out_root.exists():
        shutil.rmtree(out_root)

    tables = [parse_ddl(path) for path in sorted(ddl_dir.glob("*.sql"))]
    all_rows = {table.name: read_csv_rows(find_csv(data_dir, table.name)) for table in tables}
    term_knowledge = build_term_knowledge_map(term_knowledge_path)

    write_text(out_root / "manifest.json", json.dumps(build_manifest(), ensure_ascii=False, indent=2) + "\n")
    write_text(out_root / "meta" / "domains.owl", render_domains())
    write_text(out_root / "meta" / "library.owl", render_library())
    write_text(out_root / "term_types" / "term_types.owl", render_term_types(build_term_types()))
    write_text(out_root / "terms" / "terms.owl", render_terms(build_terms(all_rows, tables, term_knowledge)))
    write_text(out_root / "ontology" / "actions" / "action.owl", render_actions(tables))
    write_text(out_root / "ontology" / "dbsources" / "dbsource.owl", render_dbsource(data_dir))
    write_text(out_root / "ontology" / "views" / "views.owl", render_view(build_view()))
    write_text(out_root / "relations" / "relation.owl", render_relations(build_relation_rows()))

    for table in tables:
        object_dir = out_root / "ontology" / "objects" / table.name
        write_text(object_dir / f"{table.name}_object.owl", render_object(table, all_rows[table.name]))
        write_text(object_dir / f"{table.name}_mapping.owl", render_mapping(table))

    return out_root


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out_root = generate()
    logger.info("Generated OWL v4 package from DDL + CSV at %s", out_root)


if __name__ == "__main__":
    main()
