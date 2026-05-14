"""OWL 实体字段转换器。

将 ``owl_parser`` 产出的实体字典转换为 executor 可消费的标准字段结构。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Final

from .snowflake import _next_snowflake_id

logger = logging.getLogger(__name__)

_TYPE_ALIAS: Final[dict[str, str]] = {
    "对象": "object",
    "视图": "view",
    "属性": "prop",
    "动作": "action",
    "术语类型": "term_type",
    "术语": "term_type",
}


# relation_type 到 cardinality 的标准映射。
RELATION_TYPE_TO_CARDINALITY: Final[dict[str, str]] = {
    "ONE_TO_ONE": "1:1",
    "ONE_TO_MANY": "1:N",
    "MANY_TO_ONE": "N:1",
    "MANY_TO_MANY": "N:N",
    # 本体结构关系（owl_gen 生成）
    "HAS_OBJECT": "1:N",
    "HAS_FIELD": "1:N",
    "HAS_ACTION": "1:N",
    "HAS_TERM": "1:N",
}


def parse_json_field(value: Any, default: Any) -> Any:
    """安全解析 JSON 字符串。

    解析失败时返回 default，并记录 warning，不抛出异常。
    """

    if value is None:
        return default

    if isinstance(value, (list, dict)):
        return value

    if not isinstance(value, str):
        return default

    raw = value.strip()
    if not raw:
        return default

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("JSON 字段解析失败，已返回默认值: %s", raw)
        return default


def map_cardinality(relation_type: str | None) -> str | None:
    """将 relation_type 映射为 cardinality。"""

    normalized = (relation_type or "").strip().upper()
    if not normalized:
        logger.warning("relation_type 为空，无法映射 cardinality")
        return None

    cardinality = RELATION_TYPE_TO_CARDINALITY.get(normalized)
    if cardinality is None:
        logger.warning("未知 relation_type，无法映射 cardinality: %s", relation_type)
    return cardinality


def convert_domain(owl_entity: dict[str, Any]) -> dict[str, Any]:
    """转换领域实体字段。"""

    return {
        "domain_code": _pick_str(owl_entity, "domain_code"),
        "domain_name": _pick_str(owl_entity, "domain_name"),
        "parent_code": _pick_str(owl_entity, "parent_domain_code"),
        "domain_desc": _pick_str(owl_entity, "remark"),
    }


def convert_term_type(owl_entity: dict[str, Any]) -> dict[str, Any]:
    """转换术语类型实体字段，并提取 domain_code。"""

    type_code_path = _pick_str(owl_entity, "term_type_code_path", "trem_type_code_path")

    return {
        "type_code": _pick_str(owl_entity, "type_code", "term_type_code"),
        "type_name": _pick_str(owl_entity, "type_name", "term_type_name"),
        "type_desc": _pick_str(owl_entity, "type_desc", "term_type_desc"),
        "type_category": _pick_str(owl_entity, "type_category", "term_data_type") or "字典术语",
        "domain_code": _extract_domain_code(type_code_path),
    }


def convert_term(owl_entity: dict[str, Any]) -> dict[str, Any]:
    """转换术语实体字段。"""

    term_code = _pick_str(owl_entity, "term_code")
    term_name = _pick_str(owl_entity, "term_name")
    term_type_code = _pick_str(owl_entity, "term_type_code")
    library_code = _pick_str(owl_entity, "library_code")
    domain_code = _pick_str(owl_entity, "domain_code")
    parent_term_code = _pick_str(owl_entity, "parent_term_code") or ""
    parent_term_type_code = _pick_str(owl_entity, "parent_term_type_code") or ""
    parent_term_id = None
    parent_term_key = f"{parent_term_code}" if parent_term_code else None

    synonyms = parse_json_field(_pick_str(owl_entity, "synonyms"), [])
    if not isinstance(synonyms, list):
        logger.warning("synonyms 不是列表，已降级为空列表: %s", synonyms)
        synonyms = []

    # 统一清洗同义词，避免空白与非字符串值污染。
    normalized_synonyms = [text for item in synonyms if (text := str(item).strip())]

    aliases = [alias for alias in normalized_synonyms if alias != term_name]

    ext_field_json = parse_json_field(_pick_str(owl_entity, "ext_field"), {})
    ext_field_json["aliases"] = aliases
    ext_field = json.dumps(ext_field_json, ensure_ascii=False)

    return {
        "term_id": (
            f"{parent_term_key}#{term_type_code}#{term_code}"
            if parent_term_key
            else "#".join(
                [
                    str(library_code),
                    str(term_type_code),
                    str(term_code),
                ]
            )
        ),
        "term_code": term_code,
        "term_name": term_name,
        "term_desc": _pick_str(owl_entity, "term_desc"),
        "domain_code": domain_code,
        "library_code": library_code,
        "term_type_code": term_type_code,
        "parent_term_code": parent_term_code or None,
        "parent_term_type_code": parent_term_type_code or None,
        "parent_term_id": parent_term_id,
        "synonyms": normalized_synonyms,
        "aliases": aliases,
        "owl_doc_file": _pick_str(owl_entity, "owl_doc_file"),
        "ext_field": ext_field,
    }


def convert_scene_field(owl_entity: dict[str, Any]) -> dict[str, Any]:
    """转换视图字段实体。"""

    return {
        "field_code": _pick_str(owl_entity, "property_code"),
        "field_name": _pick_str(owl_entity, "property_name"),
        "source_object_code": _pick_str(owl_entity, "source_object_code"),
        "source_object_column_code": _pick_str(owl_entity, "source_object_column_code"),
        "synonyms": parse_json_field(_pick_str(owl_entity, "synonyms"), []),
        "ext_property": parse_json_field(_pick_str(owl_entity, "ext_property"), {}),
    }


def extract_knowledge_records(owl_term: dict[str, Any], term_id: str) -> list[dict[str, Any]]:
    """从术语实体中提取可写入 term_knowledge 的记录列表。"""

    # terms_knowledge 既可能是 JSON 字符串，也可能已经是解析后的列表。
    knowledges = parse_json_field(owl_term.get("terms_knowledge"), [])
    if not isinstance(knowledges, list):
        logger.warning("terms_knowledge 不是列表，已降级为空列表: %s", knowledges)
        return []

    records: list[dict[str, Any]] = []
    for knowledge in knowledges:
        # 非对象项无法映射到 term_knowledge 字段，直接跳过避免脏数据落库。
        if not isinstance(knowledge, dict):
            logger.warning("terms_knowledge 子项不是对象，已跳过: %s", knowledge)
            continue

        records.append(
            {
                "knowledge_id": _next_snowflake_id(),
                "term_id": term_id,
                "desc_summary": _pick_str(knowledge, "name"),
                "desc": _pick_str(knowledge, "content"),
            }
        )
    return records


def convert_relation(owl_entity: dict[str, Any]) -> dict[str, Any]:
    """转换关系实体字段，包含 cardinality 与 joinkeys 处理。"""

    # 解析 joinkeys
    joinkeys = parse_json_field(_pick_str(owl_entity, "joinkeys"), [])
    if not isinstance(joinkeys, list):
        logger.warning("joinkeys 不是列表，已降级为空列表: %s", joinkeys)
        joinkeys = []

    # 构造 source_term_code 和 target_term_code
    source_library = _pick_str(owl_entity, "source_library") or ""
    source_type = _pick_str(owl_entity, "source_type") or ""
    source_code = _pick_str(owl_entity, "source_code") or ""
    target_library = _pick_str(owl_entity, "target_library") or ""
    target_type = _pick_str(owl_entity, "target_type") or ""
    target_code = _pick_str(owl_entity, "target_code") or ""

    source_type = _TYPE_ALIAS.get(source_type, source_type)
    target_type = _TYPE_ALIAS.get(target_type, target_type)

    source_term_code = f"{source_library}#{source_type}#{source_code}"
    if target_type == "prop" and source_type in {"object", "view"}:
        target_term_code = (
            f"{source_library}#{source_type}#{source_code}#{target_type}#{target_code}"
        )
    else:
        target_term_code = f"{target_library}#{target_type}#{target_code}"

    # 解析 ext_field，合并 joinkeys
    ext_field_json = parse_json_field(_pick_str(owl_entity, "ext_field"), {})
    ext_field_json["joinkeys"] = joinkeys
    ext_field = json.dumps(ext_field_json, ensure_ascii=False)

    return {
        "source_term_code": source_term_code,
        "target_term_code": target_term_code,
        "relation_name": _pick_str(owl_entity, "relation_name"),
        "cardinality": map_cardinality(_pick_str(owl_entity, "relation_category", "relation_type")),
        "ext_field": ext_field,
    }


def _extract_domain_code(term_type_code_path: str | None) -> str | None:
    """从 term_type_code_path（如 SALE#OBJECT）中提取 domain_code。"""

    if not term_type_code_path:
        return None

    domain_code, _, _ = term_type_code_path.partition("#")
    return domain_code or None


def _pick_str(data: dict[str, Any], *keys: str) -> str | None:
    """从候选 key 中取第一个非空字符串值。"""

    for key in keys:
        value = data.get(key)
        if value is None:
            continue

        if isinstance(value, list):
            value = value[0] if value else None
            if value is None:
                continue

        text = str(value).strip()
        if text:
            return text

    return None


__all__ = [
    "RELATION_TYPE_TO_CARDINALITY",
    "_TYPE_ALIAS",
    "convert_domain",
    "convert_relation",
    "convert_term",
    "convert_term_type",
    "extract_knowledge_records",
    "map_cardinality",
    "parse_json_field",
]
