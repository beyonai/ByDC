"""对象术语同步 — 供 server 直接调用的术语入库/清除接口。

提供两个公开函数：
- sync_object_terms(): 将对象的实体+字段术语写入知识库（不生成 OWL，不注册资源）
- remove_object_terms(): 从知识库中清除对象的所有术语（级联删除）
"""

from __future__ import annotations

import logging
from typing import Any, cast

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.contracts.kps import RelationDef, TermDef, TermTypeDef
from datacloud_knowledge.ingestion.ontology_terms import _register_type, _write_kps_batch

logger = logging.getLogger(__name__)

_ENTITY_TYPE = "object"
_LIBRARY_CODE = "PERSONAL_LIB"
_DOMAIN_CODES = ("PERSONAL_DOMAIN",)


class _ScopeDeletingReader:
    """delete_scope 协议 — TermReader 的运行时可调用方法。"""

    def delete_scope(self, scope: str) -> dict[str, Any]: ...  # type: ignore[empty-body]


def sync_object_terms(
    entity_code: str,
    entity_name: str,
    entity_desc: str = "",
    entity_source: str = "DYNAMIC_TABLE",
    fields: list[dict[str, Any]] | None = None,
    *,
    backfill_vectors: bool = False,
) -> dict[str, Any]:
    """同步对象术语到知识库（不生成 OWL，不注册资源）。

    调用 BulkImportAdapter 写入 term/term_relation/term_type，
    可选回填 tsvector + embedding。

    Args:
        entity_code: 对象编码
        entity_name: 对象名称
        entity_desc: 对象描述
        entity_source: DYNAMIC_TABLE / KNOWLEDGE_BASE / DB / API
        fields: 字段列表 [{"property_code": ..., "property_name": ..., "data_type": ...}]
        backfill_vectors: 是否回填 tsvector + embedding

    Returns:
        {"ok": True} 或 {"ok": False, "error": "..."}
    """
    field_list = fields or []

    # ── 1. 构建 KPS 对象 ────────────────────────────────────────────────
    entity_term = TermDef(
        term_code=entity_code,
        term_name=entity_name,
        term_type_code=_ENTITY_TYPE,
        library_code=_LIBRARY_CODE,
        domain_codes=_DOMAIN_CODES,
        term_desc=entity_desc,
    )
    entity_term_id = entity_term.compute_term_id()

    terms: list[TermDef] = [entity_term]
    relations: list[RelationDef] = []
    term_types: list[TermTypeDef] = []
    seen_type_codes: set[str] = set()

    # 注册内置 TermTypeDef
    _register_type(term_types, seen_type_codes, _ENTITY_TYPE, _ENTITY_TYPE, "", 3)
    _register_type(term_types, seen_type_codes, "prop", "prop", "", 3)

    for field in field_list:
        property_code: str = field.get("property_code", "")
        if not property_code:
            continue
        property_name: str = field.get("property_name", property_code)

        # 属性术语 (prop)
        prop_term = TermDef(
            term_code=property_code,
            term_name=property_name,
            term_type_code="prop",
            library_code=_LIBRARY_CODE,
            domain_codes=_DOMAIN_CODES,
            parent_term_code=entity_code,
        )
        terms.append(prop_term)
        prop_term_id = prop_term.compute_term_id(parent_term_id=entity_term_id)

        # HAS_FIELD 关系
        relations.append(
            RelationDef(
                source_term_code=entity_term_id,
                target_term_code=prop_term_id,
                relation_name=f"{entity_name}_拥有字段_{property_name}",
                relation_category="HAS_FIELD",
                cardinality="1:N",
                ext_field={"field_alias": property_name},
            )
        )

    if len(terms) <= 1:
        logger.info(
            "sync_object_terms: entity=%s source=%s — 无字段术语需要入库",
            entity_code,
            entity_source,
        )
        return {"ok": True, "message": "无字段术语需要入库"}

    logger.info(
        "sync_object_terms: entity=%s source=%s fields=%d backfill=%s",
        entity_code,
        entity_source,
        len(field_list),
        backfill_vectors,
    )

    # ── 2. 通过 BulkImportAdapter 写入术语库 ────────────────────────────
    return _write_kps_batch(
        terms=terms,
        relations=relations,
        term_types=term_types,
        entity_term_id=entity_term_id,
        entity_code=entity_code,
        entity_type=_ENTITY_TYPE,
        schema=None,
        db_url=None,
        backfill_vectors=backfill_vectors,
        caller_label="sync_object_terms",
    )


def remove_object_terms(entity_code: str) -> dict[str, Any]:
    """从知识库中清除对象的所有术语（级联删除）。

    通过 delete_scope("object:{entity_code}") 级联删除
    term / term_name / term_relation / term_knowledge 表中
    该对象下的全部数据。

    Args:
        entity_code: 对象编码

    Returns:
        {"ok": True} 或 {"ok": False, "error": "..."}
    """
    logger.info("remove_object_terms: entity=%s", entity_code)
    scope = f"object:{entity_code}"
    try:
        reader = cast(_ScopeDeletingReader, create_reader())
        result = reader.delete_scope(scope)
        if not result.get("ok"):
            error_msg = result.get("error", "未知错误")
            logger.error("remove_object_terms 删除失败: entity=%s error=%s", entity_code, error_msg)
            return {"ok": False, "error": str(error_msg)}
        logger.info("remove_object_terms 完成: entity=%s", entity_code)
        return {"ok": True}
    except Exception as exc:
        logger.exception("remove_object_terms 异常: entity=%s", entity_code)
        return {"ok": False, "error": str(exc)}
