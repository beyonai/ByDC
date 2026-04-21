"""知识包入库执行器：按 manifest 顺序在单个事务内写入数据库。

环境变量 DATACLOUD_KNOWLEDGE_IMPORT_BATCH_SIZE（默认 500，上限 10000）控制每个文件按批解析并入库的行数，减少与数据库的往返次数。

前提：调用方已通过 precheck.run() 校验，此处不再做格式校验。
字段映射（JSONL → DB）：
  domain_code   → domain.domain_id
  library_code  → term_library.library_id 与 term_library.library_code（同值）
  type_code     → term_type.type_code  （用 type_code 做 upsert key）
  term_code     → term.term_code
  term_name.name_id → 雪花 ID
  relation_code → term_relation.relation_id
  relation / term_name / term_knowledge 等外键列均存 term_id；JSONL 可同时提供
  term_id, 由 library_code+type_code+term_code 唯一决定

  雪花 ID：可选环境变量 DATACLOUD_KNOWLEDGE_SNOWFLAKE_DATACENTER_ID、
  DATACLOUD_KNOWLEDGE_SNOWFLAKE_WORKER_ID（各 0–31，默认 1）。
"""

from __future__ import annotations

import json
import logging
import os
from importlib import import_module
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection, sql

from datacloud_knowledge.db.context import DatabaseContext
from datacloud_knowledge.db_url import build_postgres_connection_uri

from . import _helpers, owl_converter, owl_parser
from .writer import (
    _batch_process_domain,
    _batch_process_knowledge,
    _batch_process_library,
    _batch_process_relation,
    _batch_process_term,
    _batch_process_term_type,
)

_execute_values = _helpers._execute_values
_import_batch_size = _helpers._import_batch_size
_iter_jsonl_obj_batches = _helpers._iter_jsonl_obj_batches
_lookup_term_ids_by_norm_codes = _helpers._lookup_term_ids_by_norm_codes
_normalize_term_code = _helpers._normalize_term_code
_optional_term_id_from_obj = _helpers._optional_term_id_from_obj
_str_id_if_set = _helpers._str_id_if_set
_term_id_from_obj_or_code = _helpers._term_id_from_obj_or_code
_term_id_from_obj_or_code_direct = _helpers._term_id_from_obj_or_code_direct

logger = logging.getLogger(__name__)


# ── DB 连接 ───────────────────────────────────────────────────────────────────


def _connect() -> Connection:
    """从环境变量建立 psycopg3 连接。

    可选环境变量：
    - DATACLOUD_DB_CONNECT_TIMEOUT：连接超时（秒），默认 30；仅影响建连阶段。
    - DATACLOUD_DB_LOCK_TIMEOUT_MS：锁等待超时（毫秒）。>0 时执行 SET lock_timeout，
      避免 INSERT/UPDATE 在等表锁/行锁时无限挂起；未设置则不启用（与 PostgreSQL 默认一致）。
    若入库卡在 domain 首条 INSERT，多为其他会话持有 whale_datacloud.* 上的锁且未提交，
    请在库上查阻塞会话或设置 DATACLOUD_DB_LOCK_TIMEOUT_MS=30000 快速得到 lock timeout 报错。
    """

    ct_raw = os.getenv("DATACLOUD_DB_CONNECT_TIMEOUT", "30").strip()
    connect_timeout = int(ct_raw) if ct_raw.isdigit() else 30

    app_name = "datacloud_knowledge_import"

    _kw: dict[str, Any] = {
        "conninfo": build_postgres_connection_uri(),
        "connect_timeout": connect_timeout,
    }
    try:
        conn = psycopg.connect(**_kw, application_name=app_name)
    except TypeError:
        conn = psycopg.connect(**_kw)

    return conn


# ── 路由分发 ──────────────────────────────────────────────────────────────────

_STEP_BATCH_HANDLERS = {
    "meta_domain": _batch_process_domain,
    "meta_library": _batch_process_library,
    "term_type": _batch_process_term_type,
    "term": _batch_process_term,
    "relation": _batch_process_relation,
    "knowledge": _batch_process_knowledge,
}


def _step_entity_type(step_type: str, filename: str) -> str:
    """与 precheck 保持相同推断逻辑。"""
    if step_type == "meta":
        return "meta_domain" if "domain" in filename else "meta_library"
    if step_type == "term_types":
        return "term_type"
    if step_type == "terms":
        return "term"
    if step_type == "relations":
        return "relation"
    return step_type


def _convert_owl_entities(
    step_type: str, rel_file: str, owl_entities: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """将 OWL 解析结果转换为各批处理器可消费的数据结构。"""
    del step_type, rel_file

    converter = owl_converter
    if converter is None:
        converter = import_module("datacloud_knowledge.knowledge_build.importer.owl_converter")

    converted: dict[str, list[dict[str, Any]]] = {
        "meta_domain": [],
        "meta_library": [],
        "term_type": [],
        "term": [],
        "relation": [],
        "knowledge": [],
    }
    term_type_map: dict[str, dict[str, Any]] = {}
    type_category_map = {
        "LIST_TERM": "列表术语",
        "DICT_TERM": "字典术语",
        "ONTOLOGY_TERM": "本体术语",
        "DOC_NAME_TERM": "文档名称术语",
    }

    for entity in owl_entities:
        entity_type = str(entity.get("entity_type", "")).strip()
        if not entity_type:
            continue

        if entity_type == "domain":
            converted["meta_domain"].append(converter.convert_domain(entity))
            continue

        if entity_type == "library":
            library_code = converter._pick_str(entity, "library_code")
            library_name = converter._pick_str(entity, "library_name")
            if library_code:
                converted["meta_library"].append(
                    {
                        "library_code": library_code,
                        "library_name": library_name,
                    }
                )
            continue

        if entity_type == "term_type":
            term_type_obj = converter.convert_term_type(entity)
            raw_category = term_type_obj.get("type_category")
            if isinstance(raw_category, str):
                term_type_obj["type_category"] = type_category_map.get(
                    raw_category.strip().upper(), raw_category
                )
            type_code = term_type_obj.get("type_code")
            if isinstance(type_code, str) and type_code.strip():
                term_type_map[type_code] = term_type_obj
            converted["term_type"].append(term_type_obj)
            continue

        if entity_type == "term":
            term_obj = converter.convert_term(entity)
            converted["term"].append(term_obj)
            # terms_knowledge 需要拆成独立 knowledge 记录，沿用原有 term_code 外键解析。
            for knowledge_obj in converter.extract_knowledge_records(entity, ""):
                knowledge_obj["term_id"] = term_obj.get("term_id")
                knowledge_obj["term_code"] = term_obj.get("term_code")
                converted["knowledge"].append(knowledge_obj)
            continue

        if entity_type == "relation":
            relation_obj = converter.convert_relation(entity)
            relation_obj["relation_code"] = (
                converter._pick_str(entity, "relation_code")
                or f"{relation_obj.get('source_term_code', '')}/{relation_obj.get('target_term_code', '')}/{relation_obj.get('relation_name', '')}"
            )
            converted["relation"].append(relation_obj)

    return converted


# ── 公开入口 ──────────────────────────────────────────────────────────────────


def run(folder_path: str) -> dict[str, Any]:
    """按 manifest 顺序在单个事务内导入所有数据。

    Args:
        folder_path: 导入包根目录的本地绝对路径（预检已通过）。

    Returns:
        dict，字段：status / stats / error。

    Raises:
        不抛异常，所有错误封装在返回值 error 字段中。
    """
    root = Path(folder_path)
    stats: dict[str, Any] = {
        "domains": {"inserted": 0, "updated": 0, "deleted": 0},
        "libraries": {"inserted": 0, "updated": 0, "deleted": 0},
        "term_types": {"inserted": 0, "updated": 0, "deleted": 0},
        "terms": {"inserted": 0, "updated": 0, "deleted": 0},
        "relations": {"inserted": 0, "updated": 0, "deleted": 0},
        "knowledge": {"inserted": 0, "updated": 0, "deleted": 0},
    }

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    import_steps: list[dict[str, Any]] = manifest.get("import_steps", [])
    batch_size = _import_batch_size()

    conn = _connect()
    try:
        conn.autocommit = False
        db_ctx = DatabaseContext()
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(db_ctx.schema))
            )
            for step in import_steps:
                rel_file: str = step.get("file", "")
                step_type: str = step.get("type", "")
                entity_type = _step_entity_type(step_type, rel_file)
                batch_handler = _STEP_BATCH_HANDLERS.get(entity_type)
                if batch_handler is None and step_type != "ontology":
                    logger.warning("未知 step type '%s', 跳过 %s", step_type, rel_file)
                    continue
                if step_type == "ontology":
                    logger.info("ontology %s (reference file, parse but skip DB)", rel_file)

                file_path = root / rel_file
                logger.info(
                    "importing %s (%s), batch_size=%s",
                    rel_file,
                    entity_type,
                    batch_size,
                )
                if rel_file.endswith(".owl"):
                    owl_entities = owl_parser.parse_owl_file(file_path)
                    converted = _convert_owl_entities(step_type, rel_file, owl_entities)
                    for entity_type_key, objs in converted.items():
                        if not objs:
                            continue
                        handler = _STEP_BATCH_HANDLERS.get(entity_type_key)
                        if handler is None:
                            logger.warning(
                                "OWL 实体类型 '%s', 无处理器, 跳过 %s", entity_type_key, rel_file
                            )
                            continue
                        handler(cur, objs, stats)
                else:
                    logger.warning("不支持的文件扩展名, 跳过 %s", rel_file)

        conn.commit()
        logger.info("import committed: %s", stats)
        return {"status": "success", "stats": stats, "error": None}

    except Exception as exc:
        conn.rollback()
        logger.exception("import failed, rolled back")
        return {"status": "failed", "stats": stats, "error": str(exc)}
    finally:
        conn.close()
