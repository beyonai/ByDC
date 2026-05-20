"""本体术语入库。

将实体及其字段作为术语写入术语库，绕过 OWL 文件解析管线，
直接使用 KPS 类型 + BulkImportAdapter 写入。
"""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import Any

from datacloud_knowledge.adapters import backfill_embeddings, create_bulk_importer
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

        # ── 属性术语 (prop) — 所有字段都创建 ──
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

        # ── HAS_FIELD 关系 — 所有字段都创建 ──
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
            # ── 内联值术语 + HAS_TERM ──
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
        elif term_type_code:
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

        stats: dict[str, Any] = {
            "term_types": {"inserted": 0, "updated": 0, "deleted": 0},
            "terms": {"inserted": 0, "updated": 0, "deleted": 0},
            "relations": {"inserted": 0, "updated": 0, "deleted": 0},
        }
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

        # 回填向量嵌入（仅本次创建的术语，30s 超时，失败不阻塞）
        _backfill_embeddings_optional(
            term_ids=list(term_id_by_key.values()),
            schema=schema,
            db_url=db_url,
            entity_code=entity_code,
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


def _backfill_embeddings_optional(
    *,
    term_ids: list[str],
    schema: str | None,
    db_url: str | None,
    entity_code: str = "",
    timeout: float = 30.0,
) -> None:
    """回填向量嵌入（best-effort，超时或失败只打 warning，不抛异常）。

    失败时写 shell 脚本到 /tmp，包含完整环境变量和命令，可直接执行。
    """
    if not term_ids:
        return

    result_holder: dict[str, object] = {}
    error_holder: dict[str, BaseException] = {}

    def _run() -> None:
        try:
            result_holder["value"] = backfill_embeddings(
                schema=schema, db_url=db_url, term_ids=term_ids
            )
        except BaseException as exc:
            error_holder["exc"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        _write_backfill_script(term_ids, entity_code, schema, db_url)
        logger.warning(
            "向量回填超时（%.0fs），请执行: bash %s",
            timeout,
            _script_path(entity_code),
        )
    elif "exc" in error_holder:
        _write_backfill_script(term_ids, entity_code, schema, db_url)
        logger.warning(
            "向量回填失败: %s，请执行: bash %s",
            error_holder["exc"],
            _script_path(entity_code),
        )
    else:
        logger.info("向量回填完成: %s 条", len(term_ids))


def _script_path(entity_code: str) -> str:
    return f"/tmp/datacloud_backfill_{entity_code}.sh"  # noqa: S108


def _write_backfill_script(
    term_ids: list[str],
    entity_code: str,
    schema: str | None,
    db_url: str | None,
) -> None:
    """写可执行的 shell 脚本，缓存当前环境变量 + 完整 CLI 命令。"""
    import os
    from pathlib import Path

    # 收集 embedding 相关的环境变量
    embedding_env = ""
    for var in (
        "DATACLOUD_EMBEDDING_API_BASE",
        "DATACLOUD_EMBEDDING_API_KEY",
        "DATACLOUD_EMBEDDING_MODEL",
        "DATACLOUD_EMBEDDING_BATCH_SIZE",
        "DATACLOUD_EMBEDDING_DIMS",
    ):
        val = os.getenv(var, "")
        if val:
            embedding_env += f"export {var}='{val}'\n"

    # 收集 DB 相关的环境变量
    db_env = ""
    for var in (
        "DATACLOUD_DB_URL",
        "DATACLOUD_DB_HOST",
        "DATACLOUD_DB_PORT",
        "DATACLOUD_DB_DATABASE",
        "DATACLOUD_DB_USER",
        "DATACLOUD_DB_PASSWORD",
        "DATACLOUD_DB_SCHEMA",
    ):
        val = os.getenv(var, "")
        if val:
            db_env += f"export {var}='{val}'\n"

    # 构建 CLI 命令
    cmd = "datacloud-knowledge backfill-embeddings"
    if schema:
        cmd += f" --schema {schema}"
    if db_url:
        cmd += f" --db-url '{db_url}'"

    script = (
        "#!/bin/bash\n"
        "# 向量嵌入补填脚本 — 由 build_terms 自动生成\n"
        f"# 待补填 term_ids 数量: {len(term_ids)}\n"
        "#\n"
        "# 环境变量（来自运行 build_terms 时的缓存）:\n"
        f"{embedding_env}"
        f"{db_env}"
        "\n"
        f"{cmd}\n"
    )

    path = Path(_script_path(entity_code))
    try:
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)
        # 同时写 term_ids 列表，方便手动 SQL 精准补填
        ids_path = Path(f"/tmp/datacloud_backfill_{entity_code}_ids.txt")  # noqa: S108
        ids_path.write_text("\n".join(term_ids), encoding="utf-8")
        logger.info("补填脚本已生成: %s", path)
    except OSError:
        logger.warning("无法写入补填脚本: %s", path)


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
