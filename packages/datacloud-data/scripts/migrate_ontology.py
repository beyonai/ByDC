#!/usr/bin/env python3
"""将 datacloud-mock 的 objects_registry.json 迁移为 OntologyLoader 标准格式。

用法:
    python scripts/migrate_ontology.py [--src SOURCE] [--dst DEST]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

OBJECT_TYPE_MAP: dict[str, str] = {
    "API": "API",
    "ANALYTICS_DB": "DB",
    "KNOWLEDGE_BASE": "KNOWLEDGE_BASE",
}

DEFAULT_SRC = (
    Path(__file__).resolve().parents[2]
    / "datacloud-mock/mock-resource/ontology/crm_demo/modules/objects_registry.json"
)
DEFAULT_DST = (
    Path(__file__).resolve().parents[1] / "resources/ontology/crm_demo/objects_registry.json"
)


def _convert_term_meta(term_meta: dict[str, Any]) -> str:
    """将 termMeta 转换为 term_set 标识字符串。"""
    return f"{term_meta['termTypeCode']}.{term_meta['termField']}"


def _convert_property(prop: dict[str, Any]) -> dict[str, Any]:
    """将源格式 property 转换为标准 field。"""
    field: dict[str, Any] = {
        "field_code": prop["property_code"],
        "field_name": prop.get("property_name", prop["property_code"]),
        "field_type": prop.get("property_type", "STRING"),
    }
    if prop.get("description"):
        field["description"] = prop["description"]
    if prop.get("required"):
        field["required"] = True
    if prop.get("is_primary_key"):
        field["is_primary_key"] = True
    if prop.get("source_column"):
        field["source_column"] = prop["source_column"]
    if prop.get("aliases"):
        field["aliases"] = prop["aliases"]
    if "termMeta" in prop:
        field["term_set"] = _convert_term_meta(prop["termMeta"])
    return field


def _convert_param(param: dict[str, Any]) -> dict[str, Any]:
    """将源格式 action param 转换为标准 param。"""
    p: dict[str, Any] = {
        "param_code": param["param_code"],
        "param_name": param.get("param_name", param["param_code"]),
        "param_type": param.get("param_type", "STRING"),
        "direction": param.get("direction", "IN"),
    }
    if param.get("required"):
        p["required"] = True
    if param.get("default_value") is not None:
        p["default_value"] = param["default_value"]
    if param.get("mapping_path"):
        p["mapping_path"] = param["mapping_path"]
    if "termMeta" in param:
        p["term_set"] = _convert_term_meta(param["termMeta"])
    return p


def _convert_action(action: dict[str, Any]) -> dict[str, Any]:
    """将源格式 action 转换为标准 action。"""
    return {
        "action_code": action["action_code"],
        "action_name": action.get("action_name", action["action_code"]),
        "description": action.get("description", ""),
        "params": [_convert_param(p) for p in action.get("params", [])],
        "function_refs": action.get("function_refs", []),
        "script": action.get("script"),
    }


def _convert_object(obj: dict[str, Any]) -> dict[str, Any]:
    """将源格式 object 转换为标准 object。"""
    source_type = OBJECT_TYPE_MAP.get(obj.get("object_type", ""), "DB")
    sc = obj.get("source_config", {})

    result: dict[str, Any] = {
        "object_code": obj["object_code"],
        "object_name": obj.get("object_name", obj["object_code"]),
        "description": obj.get("description", ""),
        "source_type": source_type,
        "tags": obj.get("tags", []),
        "fields": [_convert_property(p) for p in obj.get("properties", [])],
        "actions": [_convert_action(a) for a in obj.get("actions", [])],
    }

    if source_type == "DB" or source_type == "KNOWLEDGE_BASE":
        result["datasource_alias"] = sc.get("datasource_id", "crm_db")
        result["table_name"] = sc.get("table_name")
    else:
        result["datasource_alias"] = None
        result["table_name"] = None

    return result


def _convert_relation(rel: dict[str, Any], idx: int) -> dict[str, Any]:
    """将源格式 relation 转换为标准 relation。"""
    src = rel.get("source_object_ref", "")
    tgt = rel.get("target_object_ref", "")
    code = rel.get("relation_code") or f"rel_{src}__{tgt}_{idx}"

    join_keys: list[dict[str, str]] = []
    src_prop = rel.get("source_property_ref")
    tgt_prop = rel.get("target_property_ref")
    if src_prop and tgt_prop:
        join_keys.append({"from_field": src_prop, "to_field": tgt_prop})

    rel_type = rel.get("relation_type", "ONE_TO_MANY")
    if rel_type == "BELONGS_TO":
        rel_type = "MANY_TO_ONE"
    elif rel_type == "ASSOCIATES":
        rel_type = "ONE_TO_MANY"

    return {
        "relation_code": code,
        "relation_name": rel.get("relation_name", ""),
        "source_class": src,
        "target_class": tgt,
        "relation_type": rel_type,
        "join_keys": join_keys,
    }


def _convert_function(fn: dict[str, Any]) -> dict[str, Any]:
    """将源格式 function 转换为标准 function。"""
    return {
        "function_code": fn["function_code"],
        "function_name": fn.get("function_name", fn["function_code"]),
        "description": fn.get("description", ""),
        "function_type": fn.get("function_type", "API"),
        "api_schema": fn.get("api_schema", {}),
    }


def migrate(src_path: Path, dst_path: Path) -> dict[str, Any]:
    """执行迁移，返回标准格式 dict。"""
    raw = json.loads(src_path.read_text(encoding="utf-8"))

    result: dict[str, Any] = {
        "functions": [_convert_function(fn) for fn in raw.get("functions", [])],
        "objects": [_convert_object(obj) for obj in raw.get("objects", [])],
        "relations": [_convert_relation(rel, i) for i, rel in enumerate(raw.get("relations", []))],
    }

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Migrated: {src_path}")
    print(f"  -> {dst_path}")
    print(f"  functions: {len(result['functions'])}")
    print(f"  objects:   {len(result['objects'])}")
    print(f"  relations: {len(result['relations'])}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate ontology to standard format")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--dst", type=Path, default=DEFAULT_DST)
    args = parser.parse_args()
    migrate(args.src, args.dst)


if __name__ == "__main__":
    main()
