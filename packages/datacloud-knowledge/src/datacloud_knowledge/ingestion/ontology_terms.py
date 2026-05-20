"""本体术语入库。

将实体及其字段作为术语写入术语库，绕过 OWL 文件解析管线，
直接使用 KPS 类型 + BulkImportAdapter 写入。
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from datacloud_knowledge.adapters import create_bulk_importer
from datacloud_knowledge.contracts.kps import RelationDef, TermDef, TermTypeDef
from datacloud_knowledge.ingestion.owl_generate.renderers.term_types import (
    _term_data_type_to_category,
)
from datacloud_knowledge.ingestion.owl_import.importer.owl_converter import (
    relation_kps_to_dict,
    term_kps_to_dict,
    term_type_kps_to_dict,
)

logger = logging.getLogger(__name__)


def build_terms(
    entity_code: str,
    entity_name: str,
    fields: list[dict[str, Any]],
    *,
    library_code: str = "PERSONAL_LIB",
    domain_code: str = "PERSONAL_DOMAIN",
    entity_type: str = "object",
    entity_desc: str = "",
    schema: str | None = None,
    db_url: str | None = None,
) -> dict[str, Any]:
    """本体术语入库 — 直接写术语库，不走 OWL 文件解析。

    Args:
        entity_code: 实体编码（唯一）。
        entity_name: 实体中文名称。
        fields: 字段列表，每个字段含 property_code/term_type_code/term_values 等。
        library_code: 术语库编码，默认 PERSONAL_LIB。
        domain_code: 领域编码，默认 PERSONAL_DOMAIN。
        entity_type: "object" 或 "view"。
        entity_desc: 实体描述。
        schema: 知识库 schema 名称。
        db_url: 数据库连接 URL。

    Returns:
        {"ok": True, "stats": {...}} 或 {"ok": False, "error": "..."}
    """
    # ── 1. 构建 KPS 对象 ──────────────────────────────────────────────────
    entity_term = TermDef(
        term_code=entity_code,
        term_name=entity_name,
        term_type_code=entity_type,
        library_code=library_code,
        domain_code=domain_code,
        term_desc=entity_desc,
    )
    entity_term_id = entity_term.compute_term_id()

    terms: list[TermDef] = [entity_term]
    relations: list[RelationDef] = []
    term_types: list[TermTypeDef] = []
    seen_type_codes: set[str] = set()

    # 注册内置 TermTypeDef
    _register_type(term_types, seen_type_codes, entity_type, entity_type, "", 3)
    _register_type(term_types, seen_type_codes, "prop", "prop", "", 3)

    for field in fields:
        property_code: str = field.get("property_code", "")
        if not property_code:
            continue
        property_name: str = field.get("property_name", property_code)
        term_type_code: str = field.get("term_type_code", "")
        term_values: list[dict[str, str]] = field.get("term_values") or []
        term_data_type: str = field.get("term_data_type", "LIST_TERM")

        if not term_type_code and not term_values:
            continue  # 无术语绑定的字段，跳过

        # 属性术语 (prop)
        prop_term = TermDef(
            term_code=property_code,
            term_name=property_name,
            term_type_code="prop",
            library_code=library_code,
            domain_code=domain_code,
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

        if term_values:
            # ── 内联值术语 ──
            value_type_code = property_code
            type_category = _term_data_type_to_category(term_data_type)
            _register_type(
                term_types, seen_type_codes, value_type_code, property_name, "", type_category
            )

            for entry in term_values:
                if not isinstance(entry, dict):
                    continue
                value_code: str = entry.get("code", "")
                value_name: str = entry.get("name", value_code)
                if not value_code:
                    continue

                value_term = TermDef(
                    term_code=value_code,
                    term_name=value_name,
                    term_type_code=value_type_code,
                    library_code=library_code,
                    domain_code=domain_code,
                    parent_term_code=property_code,
                )
                terms.append(value_term)
                value_term_id = value_term.compute_term_id(parent_term_id=prop_term_id)

                # HAS_TERM 关系
                type_node_id = f"{library_code}#{value_type_code}#{value_type_code}"
                relations.append(
                    RelationDef(
                        source_term_code=type_node_id,
                        target_term_code=value_term_id,
                        relation_name=f"{value_type_code}包含{value_name}",
                        relation_category="HAS_TERM",
                        cardinality="1:N",
                    )
                )
        else:
            # ── 绑定已有术语库（term_type_code 非空，值术语已存在）──
            type_category = _term_data_type_to_category(term_data_type)
            _register_type(
                term_types, seen_type_codes, term_type_code, term_type_code, "", type_category
            )

    if len(terms) <= 1:  # 只有实体术语，无字段
        return {"ok": True, "message": "无字段术语需要入库"}

    # ── 2. 计算所有 term_id，构建映射表 ──────────────────────────────────
    term_id_by_key: dict[tuple[str, str, str | None], str] = {}
    for t in terms:
        key = (t.term_code, t.term_type_code, t.parent_term_code)
        if key in term_id_by_key:
            continue
        if t.term_type_code == entity_type and t.parent_term_code is None:
            term_id_by_key[key] = t.compute_term_id()
        elif t.term_type_code == "prop":
            term_id_by_key[key] = t.compute_term_id(parent_term_id=entity_term_id)
        elif t.parent_term_code:
            # 值术语：父项是 prop
            parent_key = (t.parent_term_code, "prop", entity_code)
            parent_id = term_id_by_key.get(parent_key, "")
            term_id_by_key[key] = (
                t.compute_term_id(parent_term_id=parent_id) if parent_id else t.compute_term_id()
            )
        else:
            term_id_by_key[key] = t.compute_term_id()

    # ── 3. KPS → Dict 转换 ───────────────────────────────────────────────
    term_dicts: list[dict[str, Any]] = []
    for t in terms:
        tid = term_id_by_key[(t.term_code, t.term_type_code, t.parent_term_code)]
        parent_tid: str | None = None
        if t.parent_term_code:
            if t.parent_term_code == entity_code:
                parent_tid = entity_term_id
            else:
                parent_key = (t.parent_term_code, "prop", entity_code)
                parent_tid = term_id_by_key.get(parent_key)

        extras: dict[str, Any] = {
            "aliases": [],
            "owl_doc_file": None,
            "ext_field": "{}",
            "parent_term_type_code": (
                entity_type
                if t.parent_term_code == entity_code
                else ("prop" if t.parent_term_code else "")
            ),
        }
        term_dicts.append(term_kps_to_dict(t, extras, term_id=tid, parent_term_id=parent_tid))

    relation_dicts: list[dict[str, Any]] = []
    for r in relations:
        relation_code = f"{r.source_term_code}/{r.target_term_code}/{r.relation_category}"
        relation_dicts.append(relation_kps_to_dict(r, relation_code=relation_code))

    term_type_dicts = [term_type_kps_to_dict(tt) for tt in term_types]

    # ── 4. 通过 BulkImportAdapter 写入术语库 ────────────────────────────
    try:
        adapter = create_bulk_importer(schema=schema, db_url=db_url)
    except Exception as exc:
        logger.exception("创建 BulkImportAdapter 失败")
        return {"ok": False, "error": f"创建数据库连接失败: {exc}"}

    try:
        scopes = [{"scope": entity_type, "code": entity_code}]
        root_term_ids = [entity_term_id]
        adapter.begin_import(scopes=scopes, root_term_ids=root_term_ids)

        stats: dict[str, Any] = {}
        if term_type_dicts:
            adapter.batch_process_term_type(term_type_dicts, stats)
        adapter.batch_process_term(term_dicts, stats)
        if relation_dicts:
            adapter.batch_process_relation(relation_dicts, stats)
        adapter.commit()

        logger.info(
            "build_terms 完成: entity=%s, terms=%d, relations=%d, types=%d",
            entity_code,
            len(term_dicts),
            len(relation_dicts),
            len(term_type_dicts),
        )
        return {"ok": True, "stats": stats}
    except Exception as exc:
        logger.exception("build_terms 写入失败")
        with contextlib.suppress(Exception):
            adapter.rollback()
        return {"ok": False, "error": f"术语写入失败: {exc}"}
    finally:
        with contextlib.suppress(Exception):
            adapter.close()


def _register_type(
    term_types: list[TermTypeDef],
    seen: set[str],
    type_code: str,
    type_name: str,
    type_desc: str,
    type_category: int,
) -> None:
    """注册 TermTypeDef（去重）。"""
    if type_code not in seen:
        seen.add(type_code)
        term_types.append(
            TermTypeDef(
                type_code=type_code,
                type_name=type_name,
                type_category=type_category,
                type_desc=type_desc,
            )
        )
