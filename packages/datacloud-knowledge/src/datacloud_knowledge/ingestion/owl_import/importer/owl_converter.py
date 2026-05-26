"""OWL 实体字段转换器。

将 ``owl_parser`` 产出的实体字典转换为 KnowledgePackage (KPS) 类型或 executor 可消费的 dict。

KPS 是生成/导入/校验的统一契约（contracts/kps.py），本模块的 KPS 版本函数
（convert_*_to_kps）产出 frozen dataclass 对象，供 executor 消费后再序列化为
writer 层需要的 dict。

旧版 dict 版本函数（convert_*）保留作为过渡兼容层，待 executor 迁移完成后删除。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Final

from datacloud_knowledge.contracts.kps import (
    DomainDef,
    LibraryDef,
    RelationDef,
    TermDef,
    TermTypeDef,
)

from .snowflake import _next_snowflake_id

logger = logging.getLogger(__name__)

# ── 类型类别映射：字符串 → 整数 ────────────────────────────────────────────────
# OWL 文件中 type_category 为字符串（如 "ONTOLOGY_TERM"），
# DB 列 term_type.type_category 为整数（1/2/3/4），KPS TermTypeDef.type_category 为 int。
_TYPE_CATEGORY_MAP: dict[str, int] = {
    "列表术语": 1,
    "LIST_TERM": 1,
    "字典术语": 2,
    "DICT_TERM": 2,
    "本体术语": 3,
    "ONTOLOGY_TERM": 3,
    "文档名称术语": 4,
    "DOC_NAME_TERM": 4,
}

_TYPE_ALIAS: Final[dict[str, str]] = {
    "对象": "object",
    "视图": "view",
    "场景": "view",  # 外部 OWL 历史数据使用"场景"表示视图，归一化到 view
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
    "HAS_TERM": "1:1",
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
    """将 relation_type 映射为 cardinality。

    旧版 dict 版本的 converter 仍依赖此函数。
    KPS 版本的 convert_relation_to_kps 直接使用 RelationDef 的 cardinality 字段。
    """
    normalized = (relation_type or "").strip().upper()
    if not normalized:
        logger.debug("relation_type 为空，将从 relationCategory 映射 cardinality")
        return None

    cardinality = RELATION_TYPE_TO_CARDINALITY.get(normalized)
    if cardinality is None:
        logger.warning("未知 relation_type，无法映射 cardinality: %s", relation_type)
    return cardinality


def _resolve_type_category(raw_category: str | None) -> int:
    """将 type_category 字符串解析为整数（1-4）。

    OWL 文件中 type_category 为字符串（如"ONTOLOGY_TERM"或"本体术语"），
    DB 列 term_type.type_category 为整数（1=列表, 2=字典, 3=本体, 4=文档）。
    KPS TermTypeDef.type_category 要求 int。
    """
    if not raw_category:
        logger.warning("type_category 为空，默认使用 3（本体术语）")
        return 3
    key = str(raw_category).strip().upper()
    if key.isdigit():
        val = int(key)
        if 1 <= val <= 4:
            return val
    return _TYPE_CATEGORY_MAP.get(key, 3)


# ═══════════════════════════════════════════════════════════════════════════════════
# KPS 版本转换器 — 产出 frozen dataclass，供 executor 消费
# ═══════════════════════════════════════════════════════════════════════════════════


def convert_domain_to_kps(owl_entity: dict[str, Any]) -> DomainDef:
    """将领域实体转换为 DomainDef（KPS 类型）。

    业务逻辑：
    - 从 OWL DomainDefinition 实体中提取领域基础信息
    - domain_code 映射为 DB 的 domain.domain_id（主键）
    - parent_domain_code 映射为 domain.parent_id（自引用外键）
    """
    return DomainDef(
        domain_code=_pick_str(owl_entity, "domain_code") or "",
        domain_name=_pick_str(owl_entity, "domain_name") or "",
        parent_code=_pick_str(owl_entity, "parent_domain_code"),
        domain_desc=_pick_str(owl_entity, "remark") or "",
    )


def convert_library_to_kps(owl_entity: dict[str, Any]) -> LibraryDef:
    """将术语库实体转换为 LibraryDef（KPS 类型）。

    业务逻辑：
    - library_code 同时作为 DB 的 term_library.library_id（PK）和 library_code（UK）
    - library_desc 处于 KPS 中但当前 DB 不使用（预留扩展）
    """
    return LibraryDef(
        library_code=_pick_str(owl_entity, "library_code") or "",
        library_name=_pick_str(owl_entity, "library_name") or "",
        library_desc=_pick_str(owl_entity, "library_desc") or "",
    )


def convert_term_type_to_kps(owl_entity: dict[str, Any]) -> TermTypeDef:
    """将术语类型实体转换为 TermTypeDef（KPS 类型）。

    业务逻辑：
    - type_code/type_name/type_desc 从 OWL 字段直接提取
    - type_category 从字符串（ONTOLOGY_TERM/本体术语等）解析为整数（1-4）
    - domain_code 不从 term_type_code_path 提取（DB 不存储）
    """
    raw_category = (
        _pick_str(owl_entity, "type_category", "term_type_category", "term_data_type") or ""
    )

    return TermTypeDef(
        type_code=_pick_str(owl_entity, "type_code", "term_type_code") or "",
        type_name=_pick_str(owl_entity, "type_name", "term_type_name") or "",
        type_category=_resolve_type_category(raw_category),
        type_desc=_pick_str(owl_entity, "type_desc", "term_type_desc") or "",
    )


def convert_term_to_kps(owl_entity: dict[str, Any]) -> tuple[TermDef, dict[str, Any]]:
    """将术语实体转换为 TermDef + 附加字段（tuple 返回）。

    业务逻辑：
    - 基础字段（code/name/type/library/domain/parent）→ TermDef
    - 附加字段（aliases、owl_doc_file、ext_field）→ dict（供 writer 层使用）
    - synonyms 从 OWL 的 JSON 字段解析，清洗空白项
    - ext_field 合并 OWL 原始 ext_field 与 aliases

    Returns:
        (term_def, extras) — extras 包含 aliases, owl_doc_file, ext_field,
        parent_term_type_code 等 KPS 之外的字段。
    """
    term_code = _pick_str(owl_entity, "term_code") or ""
    term_name = _pick_str(owl_entity, "term_name") or ""
    term_type_code = _pick_str(owl_entity, "term_type_code") or ""
    library_code = _pick_str(owl_entity, "library_code") or ""
    domain_code = _pick_str(owl_entity, "domain_code") or ""
    parent_term_code = _pick_str(owl_entity, "parent_term_code") or ""

    # 解析同义词列表
    synonyms_raw = parse_json_field(_pick_str(owl_entity, "synonyms"), [])
    if not isinstance(synonyms_raw, list):
        logger.warning("synonyms 不是列表，已降级为空列表: %s", synonyms_raw)
        synonyms_raw = []
    normalized_synonyms: tuple[str, ...] = tuple(
        text for item in synonyms_raw if (text := str(item).strip())
    )

    # 派生 aliases：同义词中去除标准名称的部分
    aliases = [s for s in normalized_synonyms if s != term_name]

    # 构建 ext_field（合并原始 ext_field + aliases）
    ext_field_json = parse_json_field(_pick_str(owl_entity, "ext_field"), {})
    ext_field_json["aliases"] = aliases
    ext_field_str = json.dumps(ext_field_json, ensure_ascii=False)

    # 附加字段（KPS 不包含，writer 层需要）
    extras: dict[str, Any] = {
        "aliases": aliases,
        "owl_doc_file": _pick_str(owl_entity, "owl_doc_file"),
        "ext_field": ext_field_str,
        "parent_term_type_code": _pick_str(owl_entity, "parent_term_type_code") or "",
    }

    term_def = TermDef(
        term_code=term_code,
        term_name=term_name,
        term_type_code=term_type_code,
        library_code=library_code,
        domain_code=domain_code,
        parent_term_code=parent_term_code or None,
        synonyms=normalized_synonyms,
        term_desc=_pick_str(owl_entity, "term_desc") or "",
    )

    return term_def, extras


def convert_relation_to_kps(owl_entity: dict[str, Any]) -> RelationDef:
    """将关系实体转换为 RelationDef（KPS 类型）。

    兼容两种 OWL 格式：
    1. 旧格式（_xml.py 产出）：source_library + source_type + source_code 三字段分离，
       relation_type 字段存储关系类型
    2. 新格式（GraphBuilder 产出）：sourceTermCode + targetTermCode 合成字段，
       relationCategory 字段存储关系类型

    业务逻辑（修正 relation_category/cardinality 混淆）：
    - relation_category 取 OWL 字段原值（HAS_FIELD/HAS_OBJECT/HAS_TERM/MANY_TO_ONE），
      不再混入 cardinality 映射
    - cardinality 从 relation_type 字段映射（ONE_TO_ONE → "1:1" 等），
      若 relation_type 本身就是 relation_category 类值则使用默认 "1:N"
    - source_term_code / target_term_code 构造为 {lib}#{type}#{code} 格式
    - joinkeys 合并到 ext_field 中供 writer 层使用
    """
    # 解析 joinkeys
    joinkeys_list: list[dict[str, str]] = parse_json_field(_pick_str(owl_entity, "joinkeys"), [])
    if not isinstance(joinkeys_list, list):
        logger.warning("joinkeys 不是列表，已降级为空列表: %s", joinkeys_list)
        joinkeys_list = []

    # ── 新格式（GraphBuilder）：sourceTermCode / targetTermCode 单字段 ──
    source_term_raw = _pick_str(owl_entity, "sourceTermCode") or ""
    target_term_raw = _pick_str(owl_entity, "targetTermCode") or ""

    if source_term_raw and target_term_raw:
        # 新格式：sourceTermCode="L1#object#by_customer" → 直接使用
        source_term_code = source_term_raw
        target_term_code = target_term_raw
    else:
        # ── 旧格式：source_library + source_type + source_code 三字段 ──
        source_library = _pick_str(owl_entity, "source_library") or ""
        source_type_raw = _pick_str(owl_entity, "source_type") or ""
        source_code = _pick_str(owl_entity, "source_code") or ""
        target_library = _pick_str(owl_entity, "target_library") or ""
        target_type_raw = _pick_str(owl_entity, "target_type") or ""
        target_code = _pick_str(owl_entity, "target_code") or ""

        source_type = _TYPE_ALIAS.get(source_type_raw, source_type_raw)
        target_type = _TYPE_ALIAS.get(target_type_raw, target_type_raw)

        source_term_code = f"{source_library}#{source_type}#{source_code}"
        if target_type == "prop" and source_type in {"object", "view"}:
            target_term_code = (
                f"{source_library}#{source_type}#{source_code}#{target_type}#{target_code}"
            )
        else:
            target_term_code = f"{target_library}#{target_type}#{target_code}"

    # KPS 修正：relation_category 取原值（HAS_FIELD 等），不再映射为 cardinality
    # relation_category 先取新字段 relationCategory，再取旧字段 relation_category，
    # 最后回退到 relation_type
    relation_category_raw = (
        _pick_str(owl_entity, "relationCategory")
        or _pick_str(owl_entity, "relation_category")
        or _pick_str(owl_entity, "relation_type")
        or "BUSINESS"
    )
    # 若 relation_category 已经是具体关系类型（HAS_FIELD/HAS_OBJECT 等），
    # 保留原值；若为 BUSINESS/ONTOLOGY 等旧值，也保留（等后续迁移）
    relation_category = relation_category_raw.strip().upper()

    # cardinality 从 relation_type 映射（优先），否则从 relation_category 映射
    relation_type_raw = _pick_str(owl_entity, "relation_type") or ""
    cardinality = map_cardinality(relation_type_raw)
    if cardinality is None:
        # relation_type 为空时，尝试从 relation_category 查找映射
        cardinality = map_cardinality(relation_category) or "1:N"

    # 构建 ext_field（合并原始 ext_field + joinkeys）
    ext_field_json = parse_json_field(_pick_str(owl_entity, "ext_field"), {})
    ext_field_json["joinkeys"] = joinkeys_list

    return RelationDef(
        source_term_code=source_term_code,
        target_term_code=target_term_code,
        relation_name=_pick_str(owl_entity, "relationName")
        or _pick_str(owl_entity, "relation_name")
        or "",
        relation_category=relation_category,
        cardinality=cardinality,
        joinkeys=tuple(joinkeys_list),
        ext_field=ext_field_json,
    )


# ═══════════════════════════════════════════════════════════════════════════════════
# KPS → Dict 序列化辅助函数（供 executor 将 KPS 转为 writer 层可消费的 dict）
# ═══════════════════════════════════════════════════════════════════════════════════


def domain_kps_to_dict(domain: DomainDef) -> dict[str, Any]:
    """将 DomainDef 序列化为 writer 层期望的 dict。"""
    return {
        "domain_code": domain.domain_code,
        "domain_name": domain.domain_name,
        "parent_code": domain.parent_code,
        "domain_desc": domain.domain_desc,
    }


def library_kps_to_dict(library: LibraryDef) -> dict[str, Any]:
    """将 LibraryDef 序列化为 writer 层期望的 dict。"""
    return {
        "library_code": library.library_code,
        "library_name": library.library_name,
    }


def term_type_kps_to_dict(term_type: TermTypeDef) -> dict[str, Any]:
    """将 TermTypeDef 序列化为 writer 层期望的 dict。

    type_category 为 int（1-4），writer 的 _resolve_type_category() 可处理 int。
    """
    return {
        "type_code": term_type.type_code,
        "type_name": term_type.type_name,
        "type_desc": term_type.type_desc,
        "type_category": term_type.type_category,
    }


def term_kps_to_dict(
    term_def: TermDef,
    extras: dict[str, Any],
    *,
    term_id: str,
    parent_term_id: str | None = None,
) -> dict[str, Any]:
    """将 TermDef + 附加字段 + 计算字段序列化为 writer 层期望的 dict。

    Args:
        term_def: KPS 术语定义。
        extras: convert_term_to_kps 返回的附加字段（aliases, owl_doc_file, ext_field）。
        term_id: 计算完成的 term_id（由 executor 根据 scope 逻辑确定）。
        parent_term_id: 计算完成的 parent_term_id（由 executor 根据 scope 逻辑确定）。
    """
    return {
        "term_id": term_id,
        "term_code": term_def.term_code,
        "term_name": term_def.term_name,
        "term_desc": term_def.term_desc,
        "domain_code": term_def.domain_code,
        "library_code": term_def.library_code,
        "term_type_code": term_def.term_type_code,
        "parent_term_code": term_def.parent_term_code,
        "parent_term_type_code": extras.get("parent_term_type_code", ""),
        "parent_term_id": parent_term_id,
        "synonyms": list(term_def.synonyms),
        "aliases": extras.get("aliases", []),
        "owl_doc_file": extras.get("owl_doc_file"),
        "ext_field": extras.get("ext_field", "{}"),
    }


def relation_kps_to_dict(
    rel: RelationDef,
    *,
    relation_code: str,
) -> dict[str, Any]:
    """将 RelationDef + 计算字段序列化为 writer 层期望的 dict。

    Args:
        rel: KPS 关系定义。
        relation_code: 唯一关系编码（由 executor 生成或从 OWL 提取）。
    """
    ext_field_str = json.dumps(rel.ext_field, ensure_ascii=False) if rel.ext_field else "{}"
    return {
        "relation_code": relation_code,
        "source_term_code": rel.source_term_code,
        "target_term_code": rel.target_term_code,
        "relation_name": rel.relation_name,
        "relation_category": rel.relation_category,
        "cardinality": rel.cardinality,
        "ext_field": ext_field_str,
        "action_term_id": None,
    }


# ═══════════════════════════════════════════════════════════════════════════════════
# 旧版 dict 版本转换器（保留过渡，待 executor 迁移完成后删除）
# ═══════════════════════════════════════════════════════════════════════════════════


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
    "convert_domain_to_kps",
    "convert_library_to_kps",
    "convert_relation",
    "convert_relation_to_kps",
    "convert_scene_field",
    "convert_term",
    "convert_term_to_kps",
    "convert_term_type",
    "convert_term_type_to_kps",
    "domain_kps_to_dict",
    "extract_knowledge_records",
    "library_kps_to_dict",
    "map_cardinality",
    "parse_json_field",
    "relation_kps_to_dict",
    "term_kps_to_dict",
    "term_type_kps_to_dict",
]
