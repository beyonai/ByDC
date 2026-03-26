#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
DDL_DIR = ROOT / "db" / "ddl" / "tables"
DATA_DIR = ROOT / "resource" / "data"
OUTPUT_DIR = ROOT / "resource" / "knowledge" / "import_package_owl"

DOMAIN_CODE = "DOMAIN_002"
DOMAIN_NAME = "产业管理"
LIBRARY_CODE = "LIB_002"
LIBRARY_NAME = "产业大脑"
DATASOURCE_CODE = "e_commerce_demo_db"


@dataclass
class Column:
    name: str
    sql_type: str
    nullable: bool
    comment: str
    default: str


@dataclass
class Table:
    code: str
    name: str
    desc: str
    columns: list[Column]
    primary_keys: list[str]


TERM_TYPE_DEFS = OrderedDict(
    [
        ("ENTERPRISE_NAME", ("企业名称", "企业名称列表", "LIST_TERM")),
        ("INDUSTRY_NAME", ("行业名称", "行业名称列表", "LIST_TERM")),
        ("GRID_NAME", ("网格名称", "网格名称列表", "LIST_TERM")),
        ("BUS_ADRESS", ("经营地址", "经营地址列表", "LIST_TERM")),
        ("REG_ADDRESS", ("注册地址", "注册地址列表", "LIST_TERM")),
        ("CHAIN_NAME", ("产业链名称", "产业链名称列表", "LIST_TERM")),
        ("UPSTREAM_CHAIN_NAME", ("上游链名称", "企业上游链名称列表", "LIST_TERM")),
        ("DOWNSTREAM_CHAIN_NAME", ("下游链名称", "企业下游链名称列表", "LIST_TERM")),
        ("RISK_LEVEL", ("风险等级", "企业风险等级字典", "DICT_TERM")),
        ("IS_SCALE_ENTERPRISE", ("规上企业标识", "规上企业标识字典", "DICT_TERM")),
        ("IS_HIGH_TECH", ("高新企业标识", "高新企业标识字典", "DICT_TERM")),
        ("IS_LISTED", ("上市标识", "上市标识字典", "DICT_TERM")),
        ("IS_LEADING", ("龙头标识", "龙头企业标识字典", "DICT_TERM")),
        ("IS_RISK", ("风险企业标识", "风险企业标识字典", "DICT_TERM")),
        ("ENTERPRISE_LEVEL", ("企业级别", "企业级别字典", "DICT_TERM")),
        ("DATA_SOURCE", ("数据来源", "数据来源字典", "DICT_TERM")),
        ("RISK_PATTERN", ("风险模式", "最新风险模式列表", "LIST_TERM")),
        ("RISK_TYPE", ("风险类型", "最新风险类型列表", "LIST_TERM")),
        ("LEADING_LEVELS", ("龙头等级", "龙头等级列表", "LIST_TERM")),
        ("REGION_NAME", ("区域名称", "区域名称列表", "LIST_TERM")),
        ("WEAKNESS_TAG", ("活力短板", "网格活力短板列表", "LIST_TERM")),
        ("CHAIN_LEVEL", ("产业链层级", "产业链层级字典", "DICT_TERM")),
        ("PARENT_CHAIN_NAME", ("父产业链名称", "父产业链名称列表", "LIST_TERM")),
        ("ASSET_TYPE", ("资产类型", "主经营资产类型字典", "DICT_TERM")),
        ("ASSET_STATUS", ("资产状态", "主经营资产状态字典", "DICT_TERM")),
        ("LOCATION_REALITY", ("位置真实性", "位置真实性字典", "DICT_TERM")),
        ("OBJECT", ("对象", "本体对象术语", "ONTOLOGY_TERM")),
        ("VIEW", ("视图", "本体视图术语", "ONTOLOGY_TERM")),
        ("ACTION", ("动作", "本体动作术语", "ONTOLOGY_TERM")),
    ]
)

TERM_BINDINGS = {
    ("dws_enterprise_wide", "enterprise_name"): "ENTERPRISE_NAME",
    ("dws_enterprise_wide", "industry_name"): "INDUSTRY_NAME",
    ("dws_enterprise_wide", "grid_name"): "GRID_NAME",
    ("dws_enterprise_wide", "bus_adress"): "BUS_ADRESS",
    ("dws_enterprise_wide", "reg_address"): "REG_ADDRESS",
    ("dws_enterprise_wide", "chain_name"): "CHAIN_NAME",
    ("dws_enterprise_wide", "upstream_chain_name"): "UPSTREAM_CHAIN_NAME",
    ("dws_enterprise_wide", "downstream_chain_name"): "DOWNSTREAM_CHAIN_NAME",
    ("dws_enterprise_wide", "risk_level"): "RISK_LEVEL",
    ("dws_enterprise_wide", "is_scale_enterprise"): "IS_SCALE_ENTERPRISE",
    ("dws_enterprise_wide", "is_high_tech"): "IS_HIGH_TECH",
    ("dws_enterprise_wide", "is_listed"): "IS_LISTED",
    ("dws_enterprise_wide", "is_leading"): "IS_LEADING",
    ("dws_enterprise_wide", "is_risk"): "IS_RISK",
    ("dws_enterprise_wide", "enterprise_level"): "ENTERPRISE_LEVEL",
    ("dws_enterprise_wide", "data_source"): "DATA_SOURCE",
    ("dws_enterprise_wide", "latest_pattern_name"): "RISK_PATTERN",
    ("dws_enterprise_wide", "latest_risk_type_name"): "RISK_TYPE",
    ("dws_enterprise_wide", "leading_levels"): "LEADING_LEVELS",
    ("dws_enterprise_wide", "region_name"): "REGION_NAME",
    ("dws_enterprise_wide", "primary_asset_type"): "ASSET_TYPE",
    ("dws_enterprise_wide", "primary_asset_status"): "ASSET_STATUS",
    ("dws_enterprise_wide", "location_reality"): "LOCATION_REALITY",
    ("dws_grid_wide", "grid_name"): "GRID_NAME",
    ("dws_grid_wide", "region_name"): "REGION_NAME",
    ("dws_grid_wide", "weakness_tag"): "WEAKNESS_TAG",
    ("dws_industry_wide", "chain_name"): "CHAIN_NAME",
    ("dws_industry_wide", "parent_chain_name"): "PARENT_CHAIN_NAME",
    ("dws_industry_wide", "chain_level"): "CHAIN_LEVEL",
}

TABLE_DESCRIPTIONS = {
    "dws_enterprise_wide": "企业粒度年度画像对象，覆盖企业身份归属、经营申报、风险研判、资产占用和产业链关系等核心指标。",
    "dws_grid_wide": "网格粒度年度治理对象，覆盖企业汇总、资产利用、IoT 活力和空间治理类指标。",
    "dws_industry_wide": "产业链粒度年度分析对象，覆盖产业链规模、龙头结构、开票能力、关系强度和链内风险等指标。",
}

ENTITY_NAMES = {
    "dws_enterprise_wide": "企业年度画像",
    "dws_grid_wide": "网格年度治理画像",
    "dws_industry_wide": "产业链年度画像",
}

ENTITY_RELATIONS = {
    "dws_enterprise_wide": ["rel_enterprise_grid", "rel_enterprise_industry"],
    "dws_grid_wide": [],
    "dws_industry_wide": ["rel_industry_parent_industry"],
}

ENTITY_ACTIONS = {
    "dws_enterprise_wide": ["query_enterprise_profile"],
    "dws_grid_wide": ["query_grid_profile"],
    "dws_industry_wide": ["query_industry_profile"],
}

ACTION_SPECS = [
    {
        "code": "query_enterprise_profile",
        "name": "按企业名称或企业ID查询企业画像",
        "desc": "按企业名称、企业ID和年份查询企业年度画像。",
        "entity": "dws_enterprise_wide",
        "request": [
            ("enterpriseName", "企业名称", "string", False, "LIB_002#ENTERPRISE_NAME", "LIST_TERM", ""),
            ("enterpriseId", "企业ID", "string", False, "OBJECT#dws_enterprise_wide", "ONTOLOGY_TERM", "enterpriseId"),
            ("dataYear", "数据年份", "integer", False, "OBJECT#dws_enterprise_wide", "ONTOLOGY_TERM", "dataYear"),
        ],
        "response": [
            ("enterpriseId", "string", "enterpriseId"),
            ("enterpriseName", "string", "enterpriseName"),
            ("gridName", "string", "gridName"),
            ("chainName", "string", "chainName"),
            ("annualRevenueReport", "double", "annualRevenueReport"),
            ("taxDeclared", "double", "taxDeclared"),
            ("riskLevel", "string", "riskLevel"),
            ("latestPatternName", "string", "latestPatternName"),
        ],
    },
    {
        "code": "query_grid_profile",
        "name": "按网格查询网格经营情况",
        "desc": "按网格名称、网格ID和年份查询网格年度治理画像。",
        "entity": "dws_grid_wide",
        "request": [
            ("gridName", "网格名称", "string", False, "LIB_002#GRID_NAME", "LIST_TERM", ""),
            ("gridId", "网格ID", "string", False, "OBJECT#dws_grid_wide", "ONTOLOGY_TERM", "gridId"),
            ("dataYear", "数据年份", "integer", False, "OBJECT#dws_grid_wide", "ONTOLOGY_TERM", "dataYear"),
        ],
        "response": [
            ("gridId", "string", "gridId"),
            ("gridName", "string", "gridName"),
            ("enterpriseCnt", "integer", "enterpriseCnt"),
            ("totalAnnualRevenue", "double", "totalAnnualRevenue"),
            ("avgRiskScore", "double", "avgRiskScore"),
            ("vitalityIdx", "double", "vitalityIdx"),
            ("weaknessTag", "string", "weaknessTag"),
        ],
    },
    {
        "code": "query_industry_profile",
        "name": "按产业链查询产业链画像",
        "desc": "按产业链名称、产业链ID和年份查询产业链年度画像。",
        "entity": "dws_industry_wide",
        "request": [
            ("chainName", "产业链名称", "string", False, "LIB_002#CHAIN_NAME", "LIST_TERM", ""),
            ("chainId", "产业链ID", "string", False, "OBJECT#dws_industry_wide", "ONTOLOGY_TERM", "chainId"),
            ("dataYear", "数据年份", "integer", False, "OBJECT#dws_industry_wide", "ONTOLOGY_TERM", "dataYear"),
        ],
        "response": [
            ("chainId", "string", "chainId"),
            ("chainName", "string", "chainName"),
            ("parentChainName", "string", "parentChainName"),
            ("enterpriseCnt", "integer", "enterpriseCnt"),
            ("leadingEnterpriseCnt", "integer", "leadingEnterpriseCnt"),
            ("relationStrengthSum", "double", "relationStrengthSum"),
            ("avgRiskScore", "double", "avgRiskScore"),
        ],
    },
]


def read_tables() -> list[Table]:
    tables: list[Table] = []
    ddl_files = sorted(DDL_DIR.glob("*.sql"))
    col_pattern = re.compile(
        r"^\s*`(?P<name>[^`]+)`\s+(?P<type>[^ ]+)(?P<rest>.*?)(?:COMMENT\s+'(?P<comment>[^']*)')?,?\s*$",
        re.IGNORECASE,
    )
    pk_pattern = re.compile(r"PRIMARY KEY \((?P<cols>.+)\)", re.IGNORECASE)
    table_comment_pattern = re.compile(r"COMMENT='(?P<comment>[^']*)'")
    table_name_pattern = re.compile(r"CREATE TABLE `[^`]+`\.`(?P<name>[^`]+)`", re.IGNORECASE)

    for path in ddl_files:
        lines = path.read_text(encoding="utf-8").splitlines()
        columns: list[Column] = []
        primary_keys: list[str] = []
        table_code = ""
        table_name = ""
        for line in lines:
            if not table_code:
                match = table_name_pattern.search(line)
                if match:
                    table_code = match.group("name")
            col_match = col_pattern.match(line)
            if col_match:
                rest = col_match.group("rest") or ""
                columns.append(
                    Column(
                        name=col_match.group("name"),
                        sql_type=col_match.group("type"),
                        nullable="NOT NULL" not in rest.upper(),
                        comment=(col_match.group("comment") or "").strip(),
                        default=parse_default(rest),
                    )
                )
                continue
            pk_match = pk_pattern.search(line)
            if pk_match:
                primary_keys = [item.strip(" `") for item in pk_match.group("cols").split(",")]
            table_comment_match = table_comment_pattern.search(line)
            if table_comment_match:
                table_name = table_comment_match.group("comment")
        tables.append(
            Table(
                code=table_code,
                name=table_name,
                desc=TABLE_DESCRIPTIONS[table_code],
                columns=columns,
                primary_keys=primary_keys,
            )
        )
    return tables


def parse_default(rest: str) -> str:
    default_match = re.search(r"DEFAULT\s+([^ ]+)", rest, re.IGNORECASE)
    if not default_match:
        return ""
    raw = default_match.group(1).strip().rstrip(",")
    if raw.upper() in {"NULL", "CURRENT_TIMESTAMP"}:
        return ""
    return raw.strip("'")


def snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(item.capitalize() for item in parts[1:])


def xml(value: object) -> str:
    return escape(str(value), {'"': "&quot;"})


def data_type(sql_type: str, column_name: str) -> str:
    raw = sql_type.lower()
    if column_name.startswith("is_") or raw == "tinyint(1)":
        return "BOOLEAN"
    if raw.startswith("tinyint") or raw.startswith("int"):
        return "INT"
    if raw.startswith("bigint"):
        return "BIGINT"
    if raw.startswith("decimal") or raw.startswith("double") or raw.startswith("float"):
        return "DOUBLE"
    if raw.startswith("datetime") or raw.startswith("date") or raw.startswith("timestamp"):
        return "DATE"
    return "STRING"


def value_format(sql_type: str) -> str:
    raw = sql_type.lower()
    if raw.startswith("date") and not raw.startswith("datetime"):
        return "yyyy-MM-dd"
    if raw.startswith("datetime") or raw.startswith("timestamp"):
        return "yyyy-MM-dd HH:mm:ss"
    decimal_match = re.match(r"decimal\((\d+),(\d+)\)", raw)
    if decimal_match:
        scale = int(decimal_match.group(2))
        return "#,##0" if scale == 0 else "#,##0." + ("0" * scale)
    return ""


def measurement_unit(comment: str) -> str:
    if "亩" in comment:
        return "亩"
    if "平米" in comment or "平方米" in comment:
        return "平方米"
    if "千瓦时" in comment:
        return "千瓦时"
    if "吨" in comment:
        return "吨"
    if "公里" in comment:
        return "公里"
    if "日期" in comment or "时间" in comment:
        return ""
    if "指数" in comment:
        return "指数"
    return ""


def category(table_code: str, column_name: str) -> str:
    groups = {
        "dws_enterprise_wide": {
            "身份归属": {
                "enterprise_id",
                "data_year",
                "enterprise_name",
                "industry_code",
                "industry_name",
                "grid_id",
                "grid_name",
                "region_id",
                "region_name",
                "register_grid_id",
                "chain_id",
                "chain_name",
                "upstream_chain_name",
                "downstream_chain_name",
            },
            "空间定位": {"bus_adress", "reg_address", "poi_latitude", "poi_longitude", "poi_adress", "location_reality"},
            "经营申报": {
                "annual_revenue_report",
                "tax_declared",
                "revenue_ai_inferred",
                "tax_ai_inferred",
                "tax_gap_ratio",
                "data_source",
                "choose_who",
                "etl_time",
            },
            "风险研判": {
                "risk_score",
                "risk_level",
                "is_risk",
                "latest_judgment_time",
                "latest_pattern_id",
                "latest_pattern_name",
                "latest_risk_type_name",
                "latest_comprehensive_score",
                "latest_judgment_summary",
            },
            "创新资质": {
                "is_scale_enterprise",
                "is_high_tech",
                "high_level_talents",
                "patents_num",
                "rd_intensity",
                "is_listed",
                "enterprise_level",
            },
            "发票交易": {
                "invoice_issued_amount",
                "invoice_received_amount",
                "invoice_issued_count",
                "invoice_item_variance_score",
                "peak_invoicing_ratio",
                "invoice_issued_amt_year",
                "invoice_received_amt_year",
                "invoice_issued_cnt_year",
                "invoice_received_cnt_year",
            },
            "产业链关系": {
                "is_leading",
                "leading_levels",
                "supplier_rel_cnt",
                "buyer_rel_cnt",
                "supplier_strength_sum",
                "buyer_strength_sum",
                "max_influence_radius_km",
            },
            "资产占用": {
                "land_area_mu",
                "power_consumption",
                "water_consumption",
                "logistics_heat_index",
                "primary_asset_id",
                "primary_asset_name",
                "primary_asset_type",
                "primary_asset_status",
                "primary_asset_land_mu",
                "primary_asset_floor_sqm",
                "occupancy_asset_cnt",
                "occupancy_total_area_sqm",
                "occupancy_active_cnt",
            },
        },
        "dws_grid_wide": {
            "网格主键": {"grid_id", "data_year", "grid_code", "grid_name", "region_id", "region_name"},
            "空间几何": {"polygon", "area_mu", "area_kilometer", "center_point"},
            "经营汇总": {
                "enterprise_cnt",
                "scale_enterprise_cnt",
                "high_tech_cnt",
                "total_annual_revenue",
                "total_tax_declared",
                "avg_risk_score",
                "high_risk_cnt",
                "asset_cnt",
                "occupied_asset_cnt",
                "vacant_asset_cnt",
                "total_land_area_mu",
                "total_floor_area_sqm",
                "kpi_month_time",
                "output_per_mu",
                "vitality_idx",
                "weakness_tag",
            },
            "IoT活力": {
                "iot_latest_date",
                "human_flow_idx",
                "traffic_flow_idx_day",
                "night_light_idx_day",
                "logistics_heat_idx_day",
                "iot_month_time",
                "people_flow_idx_month",
                "traffic_flow_idx_month",
                "logistics_idx_month",
                "night_light_idx_month",
                "risk_weight_month",
                "etl_time",
            },
        },
        "dws_industry_wide": {
            "产业链主键": {"chain_id", "data_year", "chain_name", "parent_chain_id", "parent_chain_name", "chain_level"},
            "结构规模": {
                "chain_description",
                "node_cnt",
                "key_node_cnt",
                "enterprise_cnt",
                "scale_enterprise_cnt",
                "high_tech_cnt",
                "leading_enterprise_cnt",
                "grid_cnt",
                "region_cnt",
            },
            "经营风险": {
                "total_annual_revenue",
                "total_tax_declared",
                "avg_risk_score",
                "high_risk_cnt",
                "latest_judgment_time",
            },
            "关系网络": {
                "invoice_issued_amt_year",
                "invoice_received_amt_year",
                "intra_chain_rel_cnt",
                "supplier_rel_out_cnt",
                "buyer_rel_out_cnt",
                "relation_strength_sum",
                "etl_time",
            },
        },
    }
    for label, cols in groups[table_code].items():
        if column_name in cols:
            return label
    return "通用属性"


def term_type_path(term_type_code: str) -> str:
    return f"{LIBRARY_CODE}#{term_type_code}"


def safe_id(prefix: str, value: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    if candidate and candidate[0].isdigit():
        candidate = f"n_{candidate}"
    digest = hashlib.md5(value.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{candidate or 'value'}_{digest}"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def load_terms() -> dict[str, list[dict[str, str]]]:
    term_values: dict[str, OrderedDict[str, str]] = {key: OrderedDict() for key in TERM_TYPE_DEFS}
    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        table_code = csv_path.name.split("_202")[0]
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                for (tbl, col), term_type_code in TERM_BINDINGS.items():
                    if tbl != table_code:
                        continue
                    value = (row.get(col) or "").strip()
                    if not value:
                        continue
                    label = map_term_name(term_type_code, value)
                    term_values[term_type_code].setdefault(value, label)
    ontology_terms = {
        "OBJECT": OrderedDict(
            [
                ("dws_enterprise_wide", "企业年度画像"),
                ("dws_grid_wide", "网格年度治理画像"),
                ("dws_industry_wide", "产业链年度画像"),
            ]
        ),
        "VIEW": OrderedDict([("scene_01_data_analysis", "产业数据分析场景")]),
        "ACTION": OrderedDict(
            [
                ("query_enterprise_profile", "按企业名称或企业ID查询企业画像"),
                ("query_grid_profile", "按网格查询网格经营情况"),
                ("query_industry_profile", "按产业链查询产业链画像"),
            ]
        ),
    }
    for type_code, items in ontology_terms.items():
        for code, name in items.items():
            term_values[type_code][code] = name
    return {
        key: [{"code": code, "name": name} for code, name in values.items()]
        for key, values in term_values.items()
        if values
    }


def map_term_name(term_type_code: str, raw: str) -> str:
    boolean_names = {"0": "否", "1": "是"}
    if term_type_code in {
        "IS_SCALE_ENTERPRISE",
        "IS_HIGH_TECH",
        "IS_LISTED",
        "IS_LEADING",
        "IS_RISK",
        "LOCATION_REALITY",
    }:
        return boolean_names.get(raw, raw)
    if term_type_code == "CHAIN_LEVEL":
        return f"{raw}级链"
    if term_type_code == "RISK_LEVEL":
        mapping = {"HIGH": "高风险", "MEDIUM": "中风险", "LOW": "低风险", "Nothing": "未分级"}
        return mapping.get(raw, raw)
    if term_type_code == "WEAKNESS_TAG":
        return raw
    if term_type_code == "ENTERPRISE_LEVEL":
        return f"{raw}级企业"
    return raw


def render_domains() -> str:
    return f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/domain/ontology#">

    <owl:Class rdf:about="#DomainDefinition">
        <rdfs:label>领域定义</rdfs:label>
    </owl:Class>

    <owl:NamedIndividual rdf:about="#industry_management_domain">
        <rdf:type rdf:resource="#DomainDefinition"/>
        <domain_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{DOMAIN_CODE}</domain_code>
        <domain_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{DOMAIN_NAME}</domain_name>
        <parent_domain_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></parent_domain_code>
        <remark rdf:datatype="http://www.w3.org/2001/XMLSchema#string">亦庄产业大脑企业、网格、产业链联合分析领域</remark>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#domain_code"><rdfs:domain rdf:resource="#DomainDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#domain_name"><rdfs:domain rdf:resource="#DomainDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#parent_domain_code"><rdfs:domain rdf:resource="#DomainDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#remark"><rdfs:domain rdf:resource="#DomainDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#DomainDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
</rdf:RDF>
"""


def render_library() -> str:
    return f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/library/ontology#">

    <owl:Class rdf:about="#LibraryDefinition">
        <rdfs:label>本体库定义</rdfs:label>
    </owl:Class>

    <owl:NamedIndividual rdf:about="#industry_brain_library">
        <rdf:type rdf:resource="#LibraryDefinition"/>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{LIBRARY_CODE}</library_code>
        <library_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{LIBRARY_NAME}</library_name>
        <library_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">亦庄产业大脑企业、网格、产业链分析本体库</library_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#library_code"><rdfs:domain rdf:resource="#LibraryDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#library_name"><rdfs:domain rdf:resource="#LibraryDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#library_desc"><rdfs:domain rdf:resource="#LibraryDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#LibraryDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
</rdf:RDF>
"""


def render_term_types() -> str:
    items = []
    for type_code, (name, desc, term_data_type) in TERM_TYPE_DEFS.items():
        items.append(
            f"""    <owl:NamedIndividual rdf:about="#termtype_{type_code.lower()}">
        <rdf:type rdf:resource="#TermTypeDefinition"/>
        <term_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{term_type_path(type_code)}</term_type_code_path>
        <term_type_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{type_code}</term_type_code>
        <term_type_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(name)}</term_type_name>
        <term_type_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(desc)}</term_type_desc>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{term_data_type}</term_data_type>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""
        )
    return f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/termtype/ontology#">

    <owl:Class rdf:about="#TermTypeDefinition">
        <rdfs:label>术语类型定义</rdfs:label>
    </owl:Class>

{chr(10).join(items)}

    <owl:DatatypeProperty rdf:about="#term_type_code_path"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_type_code"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_type_name"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_type_desc"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_data_type"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#TermTypeDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
</rdf:RDF>
"""


def render_terms(term_values: dict[str, list[dict[str, str]]]) -> tuple[str, int]:
    items = []
    count = 0
    for type_code, values in term_values.items():
        term_name = TERM_TYPE_DEFS[type_code][0]
        for entry in values:
            count += 1
            term_code = entry["code"]
            term_label = entry["name"]
            if type_code in {"OBJECT", "VIEW", "ACTION"}:
                code_path = f"{type_code}#{term_code}"
                owl_doc_file = ontology_doc_path(type_code, term_code)
                term_desc = ontology_desc(type_code, term_code)
            else:
                code_path = f"{term_type_path(type_code)}#{term_code}"
                owl_doc_file = ""
                term_desc = f"{term_name}术语：{term_label}"
            items.append(
                f"""    <owl:NamedIndividual rdf:about="#{safe_id('term', code_path)}">
        <rdf:type rdf:resource="#TermDefinition"/>
        <term_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(code_path)}</term_code_path>
        <term_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(term_code)}</term_code>
        <term_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(term_label)}</term_name>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{LIBRARY_CODE}</library_code>
        <term_type_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{type_code}</term_type_code>
        <term_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(term_desc)}</term_desc>
        <synonyms rdf:datatype="http://www.w3.org/2001/XMLSchema#string">[]</synonyms>
        <terms_knowledge rdf:datatype="http://www.w3.org/2001/XMLSchema#string">[]</terms_knowledge>
        <domain_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{DOMAIN_CODE}</domain_code>
        <owl_doc_file rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(owl_doc_file)}</owl_doc_file>
        <ext_field rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></ext_field>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""
            )
    content = f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/term/ontology#">

    <owl:Class rdf:about="#TermDefinition">
        <rdfs:label>术语定义</rdfs:label>
    </owl:Class>

{chr(10).join(items)}

    <owl:DatatypeProperty rdf:about="#term_code_path"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_code"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_name"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#library_code"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_type_code"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_desc"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#synonyms"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#terms_knowledge"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#domain_code"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#owl_doc_file"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#ext_field"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#TermDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
</rdf:RDF>
"""
    return content, count


def ontology_doc_path(type_code: str, term_code: str) -> str:
    if type_code == "OBJECT":
        return f"ontology/objects/{term_code}/{term_code}_object.owl"
    if type_code == "VIEW":
        return "ontology/views/views.owl"
    return "ontology/actions/action.owl"


def ontology_desc(type_code: str, term_code: str) -> str:
    if type_code == "OBJECT":
        return TABLE_DESCRIPTIONS[term_code]
    if type_code == "VIEW":
        return "企业、网格、产业链三张宽表组成的产业数据联合分析视图"
    mapping = {item["code"]: item["desc"] for item in ACTION_SPECS}
    return mapping[term_code]


def render_dbsource() -> str:
    params = json.dumps(
        {
            "host": "${DB_HOST}",
            "port": "${DB_PORT}",
            "user": "${DB_USER}",
            "password": "${DB_PASSWORD}",
            "database": "${DB_NAME}",
            "schema": "e_commerce_demo",
            "charset": "utf8mb4",
        },
        ensure_ascii=False,
    )
    return f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/dbsource/ontology#">

    <owl:Class rdf:about="#DatabaseDefinition">
        <rdfs:label>数据源定义</rdfs:label>
    </owl:Class>

    <owl:NamedIndividual rdf:about="#dbsource_e_commerce_demo">
        <rdf:type rdf:resource="#DatabaseDefinition"/>
        <dbCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{DATASOURCE_CODE}</dbCode>
        <dbType rdf:datatype="http://www.w3.org/2001/XMLSchema#string">postgresql</dbType>
        <dbParams rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(params)}</dbParams>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#dbCode"><rdfs:domain rdf:resource="#DatabaseDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#dbType"><rdfs:domain rdf:resource="#DatabaseDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#dbParams"><rdfs:domain rdf:resource="#DatabaseDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
</rdf:RDF>
"""


def render_object(table: Table) -> str:
    field_refs = "\n".join(
        f'        <fields rdf:resource="#{snake_to_camel(column.name)}_field"/>'
        for column in table.columns
    )
    action_refs = json.dumps(ENTITY_ACTIONS[table.code], ensure_ascii=False)
    relation_refs = json.dumps(ENTITY_RELATIONS[table.code], ensure_ascii=False)
    field_items = []
    for column in table.columns:
        code = snake_to_camel(column.name)
        dtype = data_type(column.sql_type, column.name)
        term_type_code = TERM_BINDINGS.get((table.code, column.name), "")
        term_path = term_type_path(term_type_code) if term_type_code else ""
        library_code = LIBRARY_CODE if term_type_code else ""
        field_items.append(
            f"""    <owl:NamedIndividual rdf:about="#{code}_field">
        <rdf:type rdf:resource="#EntityField"/>
        <property_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{code}</property_code>
        <property_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(column.comment or column.name)}</property_name>
        <data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{dtype}(BIGINT:长整形，INT:整形, DOUBLE: 浮点形，STRING:字符，BOOLEAN:布尔，DATE:时间)</data_type>
        <is_required rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">{str(not column.nullable).lower()}</is_required>
        <default_value rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(column.default)}</default_value>
        <source_column rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{column.name}</source_column>
        <synonyms rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></synonyms>
        <data_format rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{value_format(column.sql_type)}</data_format>
        <measurement_unit rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{measurement_unit(column.comment)}</measurement_unit>
        <property_category rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{category(table.code, column.name)}</property_category>
        <property_group rdf:datatype="http://www.w3.org/2001/XMLSchema#string">STORAGE(STORAGE:存储属性,COMPUTE:计算属性,当为计算属性时需填写rel_action)</property_group>
        <ext_property rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></ext_property>
        <term_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{term_path}</term_type_code_path>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{library_code}</library_code>
        <rel_action rdf:datatype="http://www.w3.org/2001/XMLSchema#string">[]</rel_action>
    </owl:NamedIndividual>"""
        )
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
        <entity_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{table.code}</entity_code>
        <entity_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{ENTITY_NAMES[table.code]}</entity_name>
        <entity_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(table.desc)}</entity_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <entity_source rdf:datatype="http://www.w3.org/2001/XMLSchema#string">DB(DB:数据库，API:接口)</entity_source>
{field_refs}
        <action_refs rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(action_refs)}</action_refs>
        <relations rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(relation_refs)}</relations>
    </owl:NamedIndividual>

{chr(10).join(field_items)}

    <owl:DatatypeProperty rdf:about="#entity_code"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#entity_name"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#entity_desc"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#entity_source"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#fields"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#action_refs"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#relations"><rdfs:domain rdf:resource="#EntityDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#property_code"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#property_name"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#data_type"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#is_required"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#boolean"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#default_value"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#source_column"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#synonyms"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#data_format"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#measurement_unit"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#property_category"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#property_group"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#ext_property"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_type_code_path"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#library_code"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#rel_action"><rdfs:domain rdf:resource="#EntityField"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
</rdf:RDF>
"""


def render_mapping(table: Table) -> str:
    mapping_refs = "\n".join(
        f'        <mapping rdf:resource="#{snake_to_camel(column.name)}_mapping"/>'
        for column in table.columns
    )
    mapping_items = []
    for column in table.columns:
        code = snake_to_camel(column.name)
        mapping_items.append(
            f"""    <owl:NamedIndividual rdf:about="#{code}_mapping">
        <rdf:type rdf:resource="#Mapping"/>
        <property_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{code}</property_code>
        <property_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(column.comment or column.name)}</property_name>
        <source_table_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{table.code}</source_table_code>
        <source_column_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{column.name}</source_column_code>
        <source_datasource_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{DATASOURCE_CODE}</source_datasource_code>
    </owl:NamedIndividual>"""
        )
    return f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/entity/mapping#">

    <owl:Class rdf:about="#EntityMapping"><rdfs:label>实体映射</rdfs:label></owl:Class>
    <owl:Class rdf:about="#Mapping"><rdfs:label>映射关系</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#{table.code}_mapping">
        <rdf:type rdf:resource="#EntityMapping"/>
        <entity_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{table.code}</entity_code>
        <entity_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{ENTITY_NAMES[table.code]}</entity_name>
        <entity_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(table.desc)}</entity_desc>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
{mapping_refs}
    </owl:NamedIndividual>

{chr(10).join(mapping_items)}

    <owl:DatatypeProperty rdf:about="#entity_code"><rdfs:domain rdf:resource="#EntityMapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#entity_name"><rdfs:domain rdf:resource="#EntityMapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#entity_desc"><rdfs:domain rdf:resource="#EntityMapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#EntityMapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#mapping"><rdfs:domain rdf:resource="#EntityMapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#property_code"><rdfs:domain rdf:resource="#Mapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#property_name"><rdfs:domain rdf:resource="#Mapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#source_table_code"><rdfs:domain rdf:resource="#Mapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#source_column_code"><rdfs:domain rdf:resource="#Mapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#source_datasource_code"><rdfs:domain rdf:resource="#Mapping"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
</rdf:RDF>
"""


def render_relations() -> str:
    relations = [
        {
            "id": "rel_enterprise_grid",
            "source_code": "dws_enterprise_wide",
            "target_code": "dws_grid_wide",
            "name": "企业_归属_网格",
            "joinkeys": [{"sourceField": "grid_id", "targetField": "grid_id"}, {"sourceField": "data_year", "targetField": "data_year"}],
        },
        {
            "id": "rel_enterprise_industry",
            "source_code": "dws_enterprise_wide",
            "target_code": "dws_industry_wide",
            "name": "企业_归属_产业链",
            "joinkeys": [{"sourceField": "chain_id", "targetField": "chain_id"}, {"sourceField": "data_year", "targetField": "data_year"}],
        },
        {
            "id": "rel_industry_parent_industry",
            "source_code": "dws_industry_wide",
            "target_code": "dws_industry_wide",
            "name": "产业链_归属_父产业链",
            "joinkeys": [{"sourceField": "parent_chain_id", "targetField": "chain_id"}, {"sourceField": "data_year", "targetField": "data_year"}],
        },
    ]
    items = []
    for relation in relations:
        items.append(
            f"""    <owl:NamedIndividual rdf:about="#{relation['id']}">
        <rdf:type rdf:resource="#TermRelation"/>
        <source_libeary rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{LIBRARY_CODE}</source_libeary>
        <source_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">对象</source_type>
        <source_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{relation['source_code']}</source_code>
        <target_libeary rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{LIBRARY_CODE}</target_libeary>
        <target_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">对象</target_type>
        <target_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{relation['target_code']}</target_code>
        <relation_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{relation['name']}</relation_name>
        <relation_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">MANY_TO_ONE</relation_type>
        <joinkeys rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(json.dumps(relation['joinkeys'], ensure_ascii=False, separators=(',', ':')))}</joinkeys>
        <ext_field rdf:datatype="http://www.w3.org/2001/XMLSchema#string"></ext_field>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
    </owl:NamedIndividual>"""
        )
    return f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/relation/ontology#">

    <owl:Class rdf:about="#TermRelation"><rdfs:label>术语关系</rdfs:label></owl:Class>

{chr(10).join(items)}

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
</rdf:RDF>
"""


def render_view() -> str:
    object_codes = json.dumps(["dws_enterprise_wide", "dws_grid_wide", "dws_industry_wide"], ensure_ascii=False)
    relation_codes = json.dumps(["rel_enterprise_grid", "rel_enterprise_industry", "rel_industry_parent_industry"], ensure_ascii=False)
    return f"""<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
         xml:base="http://example.org/scene/ontology#">

    <owl:Class rdf:about="#SceneDefinition"><rdfs:label>视图定义</rdfs:label></owl:Class>

    <owl:NamedIndividual rdf:about="#scene_01_data_analysis_v1">
        <rdf:type rdf:resource="#SceneDefinition"/>
        <view_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">scene_01_data_analysis</view_code>
        <view_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">产业数据分析场景</view_name>
        <description rdf:datatype="http://www.w3.org/2001/XMLSchema#string">以企业明细为事实源头，联接网格空间治理视角与产业链主题视角的联合分析视图。</description>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <object_codes rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(object_codes)}</object_codes>
        <relations rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(relation_codes)}</relations>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#view_code"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#view_name"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#description"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#object_codes"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#relations"><rdfs:domain rdf:resource="#SceneDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
</rdf:RDF>
"""


def render_actions() -> str:
    action_items: list[str] = []
    request_items: list[str] = []
    response_items: list[str] = []
    for spec in ACTION_SPECS:
        req_refs = "\n".join(f'        <request_params rdf:resource="#param_{spec["code"]}_{name}"/>' for name, *_ in spec["request"])
        resp_refs = "\n".join(f'        <response_params rdf:resource="#resp_{spec["code"]}_{name}"/>' for name, *_ in spec["response"])
        action_items.append(
            f"""    <owl:NamedIndividual rdf:about="#action_{spec['code']}">
        <rdf:type rdf:resource="#ActionDefinition"/>
        <action_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{spec['code']}</action_code>
        <action_name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(spec['name'])}</action_name>
        <action_desc rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(spec['desc'])}</action_desc>
        <action_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">QUERY(UPDATE:操作, QUERY:查询)</action_type>
        <version rdf:datatype="http://www.w3.org/2001/XMLSchema#string">1.0</version>
        <function_refs rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(json.dumps([spec['code']], ensure_ascii=False))}</function_refs>
        <belong_entity rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(json.dumps([spec['entity']], ensure_ascii=False))}</belong_entity>
        <request_url rdf:datatype="http://www.w3.org/2001/XMLSchema#string">/{spec['code']}</request_url>
        <request_method rdf:datatype="http://www.w3.org/2001/XMLSchema#string">POST</request_method>
        <request_header rdf:resource="#http_header"/>
{req_refs}
{resp_refs}
    </owl:NamedIndividual>"""
        )
        for name, desc, field_type, required, path, term_data_type, rel_field in spec["request"]:
            request_items.append(
                f"""    <owl:NamedIndividual rdf:about="#param_{spec['code']}_{name}">
        <rdf:type rdf:resource="#RequestParameter"/>
        <paramCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{name}</paramCode>
        <type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{field_type}</type>
        <description rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{xml(desc)}</description>
        <isRequired rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">{str(required).lower()}</isRequired>
        <term_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{path}</term_type_code_path>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{LIBRARY_CODE}</library_code>
        <rel_term_codeorname rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{rel_field}</rel_term_codeorname>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{term_data_type}</term_data_type>
    </owl:NamedIndividual>"""
            )
        for name, field_type, obj_property in spec["response"]:
            response_items.append(
                f"""    <owl:NamedIndividual rdf:about="#resp_{spec['code']}_{name}">
        <rdf:type rdf:resource="#ResponseParameter"/>
        <fieldCode rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{name}</fieldCode>
        <fieldType rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{field_type}</fieldType>
        <term_type_code_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">OBJECT#{spec['entity']}</term_type_code_path>
        <library_code rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{LIBRARY_CODE}</library_code>
        <object_property rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{obj_property}</object_property>
        <json_path rdf:datatype="http://www.w3.org/2001/XMLSchema#string">data.{name}</json_path>
        <term_data_type rdf:datatype="http://www.w3.org/2001/XMLSchema#string">ONTOLOGY_TERM</term_data_type>
    </owl:NamedIndividual>"""
            )
    return f"""<?xml version="1.0"?>
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

{chr(10).join(action_items)}

{chr(10).join(request_items)}

{chr(10).join(response_items)}

    <owl:NamedIndividual rdf:about="#http_header">
        <rdf:type rdf:resource="#HeaderParameter"/>
        <name rdf:datatype="http://www.w3.org/2001/XMLSchema#string">Content-Type</name>
        <value rdf:datatype="http://www.w3.org/2001/XMLSchema#string">application/json</value>
    </owl:NamedIndividual>

    <owl:DatatypeProperty rdf:about="#action_code"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#action_name"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#action_desc"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#action_type"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#version"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#function_refs"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#belong_entity"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#request_url"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#request_method"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#request_header"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#request_params"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#response_params"><rdfs:domain rdf:resource="#ActionDefinition"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#paramCode"><rdfs:domain rdf:resource="#RequestParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#type"><rdfs:domain rdf:resource="#RequestParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#description"><rdfs:domain rdf:resource="#RequestParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#isRequired"><rdfs:domain rdf:resource="#RequestParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#boolean"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_type_code_path"><rdfs:domain rdf:resource="#RequestParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#library_code"><rdfs:domain rdf:resource="#RequestParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#rel_term_codeorname"><rdfs:domain rdf:resource="#RequestParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#term_data_type"><rdfs:domain rdf:resource="#RequestParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#fieldCode"><rdfs:domain rdf:resource="#ResponseParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#fieldType"><rdfs:domain rdf:resource="#ResponseParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#object_property"><rdfs:domain rdf:resource="#ResponseParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#json_path"><rdfs:domain rdf:resource="#ResponseParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#name"><rdfs:domain rdf:resource="#HeaderParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
    <owl:DatatypeProperty rdf:about="#value"><rdfs:domain rdf:resource="#HeaderParameter"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/></owl:DatatypeProperty>
</rdf:RDF>
"""


def render_manifest(file_counts: dict[str, int]) -> str:
    manifest = {
        "version": "1.0",
        "package_id": "e_commerce_demo_owl_20260326",
        "description": "亦庄产业大脑 OWL 导入包（基于 DDL 与 CSV 真实结构生成）",
        "created_at": "2026-03-26",
        "import_steps": [
            {"type": "meta", "file": "meta/domains.owl", "description": "领域定义"},
            {"type": "meta", "file": "meta/library.owl", "description": "本体库定义"},
            {"type": "term_types", "file": "term_types/term_types.owl", "description": "术语类型定义", "count": file_counts["term_types"]},
            {"type": "terms", "file": "terms/terms.owl", "description": "术语定义", "count": file_counts["terms"]},
            {"type": "relations", "file": "relations/relation.owl", "description": "对象关系定义", "count": 3},
            {"type": "ontology", "file": "ontology/dbsources/dbsource.owl", "description": "数据源定义", "count": 1},
            {"type": "ontology", "file": "ontology/actions/action.owl", "description": "动作定义", "count": 3},
            {"type": "ontology", "file": "ontology/views/views.owl", "description": "场景视图定义", "count": 1},
            {"type": "ontology", "file": "ontology/objects/dws_enterprise_wide/dws_enterprise_wide_object.owl", "description": "企业对象定义", "count": file_counts["dws_enterprise_wide_fields"]},
            {"type": "ontology", "file": "ontology/objects/dws_enterprise_wide/dws_enterprise_wide_mapping.owl", "description": "企业对象映射", "count": file_counts["dws_enterprise_wide_fields"]},
            {"type": "ontology", "file": "ontology/objects/dws_grid_wide/dws_grid_wide_object.owl", "description": "网格对象定义", "count": file_counts["dws_grid_wide_fields"]},
            {"type": "ontology", "file": "ontology/objects/dws_grid_wide/dws_grid_wide_mapping.owl", "description": "网格对象映射", "count": file_counts["dws_grid_wide_fields"]},
            {"type": "ontology", "file": "ontology/objects/dws_industry_wide/dws_industry_wide_object.owl", "description": "产业链对象定义", "count": file_counts["dws_industry_wide_fields"]},
            {"type": "ontology", "file": "ontology/objects/dws_industry_wide/dws_industry_wide_mapping.owl", "description": "产业链对象映射", "count": file_counts["dws_industry_wide_fields"]},
        ],
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2)


def main() -> None:
    tables = read_tables()
    term_values = load_terms()

    if OUTPUT_DIR.exists():
        for path in sorted(OUTPUT_DIR.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    write_text(OUTPUT_DIR / "meta" / "domains.owl", render_domains())
    write_text(OUTPUT_DIR / "meta" / "library.owl", render_library())
    write_text(OUTPUT_DIR / "term_types" / "term_types.owl", render_term_types())
    terms_content, terms_count = render_terms(term_values)
    write_text(OUTPUT_DIR / "terms" / "terms.owl", terms_content)
    write_text(OUTPUT_DIR / "relations" / "relation.owl", render_relations())
    write_text(OUTPUT_DIR / "ontology" / "dbsources" / "dbsource.owl", render_dbsource())
    write_text(OUTPUT_DIR / "ontology" / "actions" / "action.owl", render_actions())
    write_text(OUTPUT_DIR / "ontology" / "views" / "views.owl", render_view())

    counts = {
        "term_types": len(TERM_TYPE_DEFS),
        "terms": terms_count,
    }
    for table in tables:
        object_dir = OUTPUT_DIR / "ontology" / "objects" / table.code
        write_text(object_dir / f"{table.code}_object.owl", render_object(table))
        write_text(object_dir / f"{table.code}_mapping.owl", render_mapping(table))
        counts[f"{table.code}_fields"] = len(table.columns)

    write_text(OUTPUT_DIR / "manifest.json", render_manifest(counts))


if __name__ == "__main__":
    main()
