"""知识包入库执行器：按 manifest 顺序在单个事务内写入数据库。

前提：调用方已通过 precheck.run() 校验，此处不再做格式校验。
字段映射（JSONL → DB）：
  domain_code   → domain.domain_id
  library_code  → term_library.library_id
  type_code     → term_type.type_code  （用 type_code 做 upsert key）
  term_code     → term.term_id
  relation_code → term_relation.relation_id
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import psycopg2
import psycopg2.extensions

logger = logging.getLogger(__name__)

# ── DB 连接 ───────────────────────────────────────────────────────────────────

def _connect() -> psycopg2.extensions.connection:
    """从环境变量建立 psycopg2 连接。"""
    def _req(name: str) -> str:
        v = os.getenv(name, "").strip()
        if not v:
            raise ValueError(f"缺少环境变量: {name}")
        return v

    return psycopg2.connect(
        host=_req("DB_HOST"),
        port=int(_req("DB_PORT")),
        user=_req("DB_USER"),
        password=_req("DB_PASSWORD"),
        dbname=_req("DB_NAME"),
    )


# ── 各实体入库处理器 ───────────────────────────────────────────────────────────

def _process_domain(cur: psycopg2.extensions.cursor, obj: dict, stats: dict) -> None:
    """写入 whale_datacloud.domain。"""
    op = obj.get("op", "add")
    domain_id = obj["domain_code"]

    if op == "delete":
        cur.execute(
            "DELETE FROM whale_datacloud.domain WHERE domain_id = %s",
            (domain_id,),
        )
        stats["domains"]["deleted"] += cur.rowcount
    elif op == "update":
        cur.execute(
            """UPDATE whale_datacloud.domain
                  SET domain_name  = COALESCE(%s, domain_name),
                      domain_desc  = COALESCE(%s, domain_desc),
                      updated_time = CURRENT_TIMESTAMP
                WHERE domain_id = %s""",
            (obj.get("domain_name"), obj.get("domain_desc"), domain_id),
        )
        stats["domains"]["updated"] += cur.rowcount
    else:  # add / upsert
        parent_code = obj.get("parent_code")
        cur.execute(
            "SELECT 1 FROM whale_datacloud.domain WHERE domain_id = %s", (domain_id,)
        )
        if cur.fetchone():
            cur.execute(
                """UPDATE whale_datacloud.domain
                      SET domain_name  = %s,
                          domain_desc  = COALESCE(%s, domain_desc),
                          parent_id    = %s,
                          updated_time = CURRENT_TIMESTAMP
                    WHERE domain_id = %s""",
                (obj["domain_name"], obj.get("domain_desc"), parent_code, domain_id),
            )
            stats["domains"]["updated"] += 1
        else:
            cur.execute(
                """INSERT INTO whale_datacloud.domain
                       (domain_id, domain_name, parent_id, domain_desc)
                   VALUES (%s, %s, %s, %s)""",
                (domain_id, obj["domain_name"], parent_code, obj.get("domain_desc")),
            )
            stats["domains"]["inserted"] += 1


def _process_library(cur: psycopg2.extensions.cursor, obj: dict, stats: dict) -> None:
    """写入 whale_datacloud.term_library。"""
    op = obj.get("op", "add")
    library_id = obj["library_code"]

    if op == "delete":
        cur.execute(
            "DELETE FROM whale_datacloud.term_library WHERE library_id = %s",
            (library_id,),
        )
        stats["libraries"]["deleted"] += cur.rowcount
    elif op == "update":
        cur.execute(
            """UPDATE whale_datacloud.term_library
                  SET library_name = COALESCE(%s, library_name),
                      updated_time = CURRENT_TIMESTAMP
                WHERE library_id = %s""",
            (obj.get("library_name"), library_id),
        )
        stats["libraries"]["updated"] += cur.rowcount
    else:
        cur.execute(
            "SELECT 1 FROM whale_datacloud.term_library WHERE library_id = %s", (library_id,)
        )
        if cur.fetchone():
            cur.execute(
                """UPDATE whale_datacloud.term_library
                      SET library_name = %s,
                          updated_time = CURRENT_TIMESTAMP
                    WHERE library_id = %s""",
                (obj["library_name"], library_id),
            )
            stats["libraries"]["updated"] += 1
        else:
            cur.execute(
                "INSERT INTO whale_datacloud.term_library (library_id, library_name) VALUES (%s, %s)",
                (library_id, obj["library_name"]),
            )
            stats["libraries"]["inserted"] += 1


def _process_term_type(cur: psycopg2.extensions.cursor, obj: dict, stats: dict) -> None:
    """写入 whale_datacloud.term_type（内置类型不允许删除）。"""
    op = obj.get("op", "add")
    type_code = obj["type_code"]

    if op == "delete":
        cur.execute(
            "DELETE FROM whale_datacloud.term_type WHERE type_code = %s AND is_builtin = FALSE",
            (type_code,),
        )
        stats["term_types"]["deleted"] += cur.rowcount
    elif op == "update":
        cur.execute(
            """UPDATE whale_datacloud.term_type
                  SET type_name     = COALESCE(%s, type_name),
                      type_desc     = COALESCE(%s, type_desc),
                      updated_time  = CURRENT_TIMESTAMP
                WHERE type_code = %s AND is_builtin = FALSE""",
            (obj.get("type_name"), obj.get("type_desc"), type_code),
        )
        stats["term_types"]["updated"] += cur.rowcount
    else:
        # type_category 支持中文名（"列表术语"）和数字（1）两种形式
        category_map = {"列表术语": 1, "字典术语": 2, "本体术语": 3, "文档名称术语": 4}
        raw_cat = obj["type_category"]
        type_category = category_map.get(str(raw_cat))
        if type_category is None:
            type_category = int(raw_cat)
        cur.execute(
            "SELECT 1 FROM whale_datacloud.term_type WHERE type_code = %s", (type_code,)
        )
        if cur.fetchone():
            cur.execute(
                """UPDATE whale_datacloud.term_type
                      SET type_name    = %s,
                          type_desc    = COALESCE(%s, type_desc),
                          updated_time = CURRENT_TIMESTAMP
                    WHERE type_code = %s AND is_builtin = FALSE""",
                (obj["type_name"], obj.get("type_desc"), type_code),
            )
            stats["term_types"]["updated"] += 1
        else:
            cur.execute(
                """INSERT INTO whale_datacloud.term_type
                       (type_code, type_name, type_desc, type_category, is_builtin)
                   VALUES (%s, %s, %s, %s, FALSE)""",
                (type_code, obj["type_name"], obj.get("type_desc"), type_category),
            )
            stats["term_types"]["inserted"] += 1


def _sync_term_names(
    cur: psycopg2.extensions.cursor,
    term_id: str,
    term_name: str,
    aliases: list[str],
) -> int:
    """同步 term_name 表，并顺带维护 term_vocabulary。

    逻辑：
      1. 删除该 term 的旧 term_name 行（支持幂等重入）
      2. 写入标准名 + 所有有效别名到 term_name
      3. 对每个 name_text，INSERT INTO term_vocabulary WHERE NOT EXISTS
         ── term_vocabulary 物理表 + 唯一索引，查询无需 DISTINCT，极速

    Note:
      删除 term 时不同步删除 vocabulary 条目（词汇只增不减，jieba 词典可接受）。

    Returns:
        写入的 term_name 行数。
    """
    cur.execute(
        "DELETE FROM whale_datacloud.term_name WHERE term_id = %s", (term_id,)
    )
    names: list[tuple[str, str, str]] = [
        (f"{term_id}__STD", term_id, term_name)
    ]
    for i, alias in enumerate(aliases):
        if alias and alias != term_name:
            names.append((f"{term_id}__ALIAS{i:03d}", term_id, alias))

    for name_id, tid, name_text in names:
        cur.execute(
            """INSERT INTO whale_datacloud.term_name (name_id, term_id, name_text)
               VALUES (%s, %s, %s)""",
            (name_id, tid, name_text),
        )
        # 同步写 term_vocabulary（物理去重表）
        cur.execute(
            """INSERT INTO whale_datacloud.term_vocabulary (word)
               SELECT %s
               WHERE NOT EXISTS (
                   SELECT 1 FROM whale_datacloud.term_vocabulary WHERE word = %s
               )""",
            (name_text, name_text),
        )
    return len(names)


def _process_term(cur: psycopg2.extensions.cursor, obj: dict, stats: dict) -> None:
    """写入 whale_datacloud.term 及同步 term_name。"""
    op = obj.get("op", "add")
    term_id = obj["term_code"]

    if op == "delete":
        cur.execute(
            "DELETE FROM whale_datacloud.term_name WHERE term_id = %s", (term_id,)
        )
        cur.execute(
            "DELETE FROM whale_datacloud.term WHERE term_id = %s",
            (term_id,),
        )
        stats["terms"]["deleted"] += cur.rowcount
    elif op == "update":
        new_name = obj.get("term_name")
        cur.execute(
            """UPDATE whale_datacloud.term
                  SET term_name      = COALESCE(%s, term_name),
                      desc_summary   = COALESCE(%s, desc_summary),
                      updated_time   = CURRENT_TIMESTAMP
                WHERE term_id = %s""",
            (new_name, obj.get("desc_summary"), term_id),
        )
        stats["terms"]["updated"] += cur.rowcount
        if new_name or obj.get("aliases") is not None:
            cur.execute(
                "SELECT term_name FROM whale_datacloud.term WHERE term_id = %s", (term_id,)
            )
            row = cur.fetchone()
            if row:
                _sync_term_names(
                    cur, term_id, row[0], obj.get("aliases") or []
                )
    else:
        aliases = obj.get("aliases") or []
        term_tags = json.dumps({"aliases": aliases}, ensure_ascii=False) if aliases else "{}"
        cur.execute(
            "SELECT 1 FROM whale_datacloud.term WHERE term_id = %s", (term_id,)
        )
        if cur.fetchone():
            cur.execute(
                """UPDATE whale_datacloud.term
                      SET term_name      = %s,
                          desc_summary   = COALESCE(%s, desc_summary),
                          domain_id      = %s,
                          term_type_code = %s,
                          library_id     = %s,
                          owl_doc_id     = %s,
                          term_tags      = %s::jsonb,
                          updated_time   = CURRENT_TIMESTAMP
                    WHERE term_id = %s""",
                (
                    obj["term_name"],
                    obj.get("desc_summary"),
                    obj["domain_code"],
                    obj["term_type_code"],
                    obj.get("library_code"),
                    obj.get("owl_doc_file"),
                    term_tags,
                    term_id,
                ),
            )
            stats["terms"]["updated"] += 1
        else:
            cur.execute(
                """INSERT INTO whale_datacloud.term
                       (term_id, term_name, desc_summary, domain_id,
                        term_type_code, library_id, owl_doc_id, term_tags)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
                (
                    term_id,
                    obj["term_name"],
                    obj.get("desc_summary"),
                    obj["domain_code"],
                    obj["term_type_code"],
                    obj.get("library_code"),
                    obj.get("owl_doc_file"),
                    term_tags,
                ),
            )
            stats["terms"]["inserted"] += 1
        _sync_term_names(cur, term_id, obj["term_name"], aliases)


def _process_relation(cur: psycopg2.extensions.cursor, obj: dict, stats: dict) -> None:
    """写入 whale_datacloud.term_relation。"""
    op = obj.get("op", "add")
    relation_id = obj["relation_code"]

    if op == "delete":
        cur.execute(
            "DELETE FROM whale_datacloud.term_relation WHERE relation_id = %s",
            (relation_id,),
        )
        stats["relations"]["deleted"] += cur.rowcount
    elif op == "update":
        cur.execute(
            """UPDATE whale_datacloud.term_relation
                  SET relation_name = COALESCE(%s, relation_name),
                      updated_time  = CURRENT_TIMESTAMP
                WHERE relation_id = %s""",
            (obj.get("relation_name"), relation_id),
        )
        stats["relations"]["updated"] += cur.rowcount
    else:
        cur.execute(
            "SELECT 1 FROM whale_datacloud.term_relation WHERE relation_id = %s", (relation_id,)
        )
        if cur.fetchone():
            cur.execute(
                """UPDATE whale_datacloud.term_relation
                      SET source_term_id    = %s,
                          target_term_id    = %s,
                          relation_name     = %s,
                          relation_category = %s,
                          cardinality       = %s,
                          updated_time      = CURRENT_TIMESTAMP
                    WHERE relation_id = %s""",
                (
                    obj["source_term_code"],
                    obj["target_term_code"],
                    obj["relation_name"],
                    obj.get("relation_category", "BUSINESS"),
                    obj.get("cardinality"),
                    relation_id,
                ),
            )
            stats["relations"]["updated"] += 1
        else:
            cur.execute(
                """INSERT INTO whale_datacloud.term_relation
                       (relation_id, source_term_id, target_term_id,
                        relation_name, relation_category, cardinality)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    relation_id,
                    obj["source_term_code"],
                    obj["target_term_code"],
                    obj["relation_name"],
                    obj.get("relation_category", "BUSINESS"),
                    obj.get("cardinality"),
                ),
            )
            stats["relations"]["inserted"] += 1


def _process_knowledge(cur: psycopg2.extensions.cursor, obj: dict, stats: dict) -> None:
    """写入 whale_datacloud.term_knowledge。

    JSONL 字段：
      knowledge_id  主键
      term_code     归属术语 ID
      desc_summary  知识摘要（约 200 字）
      desc          知识原文（完整内容）
      ext_system    外部系统编码（可选）
      ext_kb_id     外部知识库 ID（可选）
      ext_doc_id    外部文档 ID（可选）
      sort_order    排序（默认 0）
    """
    op = obj.get("op", "add")
    knowledge_id = obj["knowledge_id"]

    if op == "delete":
        cur.execute(
            "DELETE FROM whale_datacloud.term_knowledge WHERE knowledge_id = %s",
            (knowledge_id,),
        )
        stats["knowledge"]["deleted"] += cur.rowcount
    elif op == "update":
        cur.execute(
            """UPDATE whale_datacloud.term_knowledge
                  SET desc_summary = COALESCE(%s, desc_summary),
                      "desc"       = COALESCE(%s, "desc"),
                      sort_order   = COALESCE(%s, sort_order),
                      updated_time = CURRENT_TIMESTAMP
                WHERE knowledge_id = %s""",
            (
                obj.get("desc_summary"),
                obj.get("desc"),
                obj.get("sort_order"),
                knowledge_id,
            ),
        )
        stats["knowledge"]["updated"] += cur.rowcount
    else:
        cur.execute(
            "SELECT 1 FROM whale_datacloud.term_knowledge WHERE knowledge_id = %s",
            (knowledge_id,),
        )
        if cur.fetchone():
            cur.execute(
                """UPDATE whale_datacloud.term_knowledge
                      SET desc_summary = %s,
                          "desc"       = %s,
                          ext_system   = %s,
                          ext_kb_id    = %s,
                          ext_doc_id   = %s,
                          sort_order   = %s,
                          updated_time = CURRENT_TIMESTAMP
                    WHERE knowledge_id = %s""",
                (
                    obj.get("desc_summary"),
                    obj.get("desc"),
                    obj.get("ext_system"),
                    obj.get("ext_kb_id"),
                    obj.get("ext_doc_id"),
                    obj.get("sort_order", 0),
                    knowledge_id,
                ),
            )
            stats["knowledge"]["updated"] += 1
        else:
            cur.execute(
                """INSERT INTO whale_datacloud.term_knowledge
                       (knowledge_id, term_id, desc_summary, "desc",
                        ext_system, ext_kb_id, ext_doc_id, sort_order)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    knowledge_id,
                    obj["term_code"],
                    obj.get("desc_summary"),
                    obj.get("desc"),
                    obj.get("ext_system"),
                    obj.get("ext_kb_id"),
                    obj.get("ext_doc_id"),
                    obj.get("sort_order", 0),
                ),
            )
            stats["knowledge"]["inserted"] += 1


# ── 路由分发 ──────────────────────────────────────────────────────────────────

_STEP_HANDLERS = {
    "meta_domain":  _process_domain,
    "meta_library": _process_library,
    "term_type":    _process_term_type,
    "term":         _process_term,
    "relation":     _process_relation,
    "knowledge":    _process_knowledge,
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


# ── 公开入口 ──────────────────────────────────────────────────────────────────

def run(folder_path: str) -> dict:
    """按 manifest 顺序在单个事务内导入所有数据。

    Args:
        folder_path: 导入包根目录的本地绝对路径（预检已通过）。

    Returns:
        dict，字段：status / stats / error。

    Raises:
        不抛异常，所有错误封装在返回值 error 字段中。
    """
    root = Path(folder_path)
    stats: dict[str, dict] = {
        "domains":    {"inserted": 0, "updated": 0, "deleted": 0},
        "libraries":  {"inserted": 0, "updated": 0, "deleted": 0},
        "term_types": {"inserted": 0, "updated": 0, "deleted": 0},
        "terms":      {"inserted": 0, "updated": 0, "deleted": 0},
        "relations":  {"inserted": 0, "updated": 0, "deleted": 0},
        "knowledge":  {"inserted": 0, "updated": 0, "deleted": 0},
    }

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    import_steps: list[dict] = manifest.get("import_steps", [])

    conn = _connect()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            for step in import_steps:
                rel_file: str = step.get("file", "")
                step_type: str = step.get("type", "")
                entity_type = _step_entity_type(step_type, rel_file)
                handler = _STEP_HANDLERS.get(entity_type)
                if handler is None:
                    logger.warning("未知 step type '%s'，跳过 %s", step_type, rel_file)
                    continue

                file_path = root / rel_file
                logger.info("importing %s (%s)", rel_file, entity_type)
                for raw in file_path.read_text(encoding="utf-8").splitlines():
                    raw = raw.strip()
                    if not raw:
                        continue
                    obj = json.loads(raw)
                    handler(cur, obj, stats)

        conn.commit()
        logger.info("import committed: %s", stats)
        return {"status": "success", "stats": stats, "error": None}

    except Exception as exc:
        conn.rollback()
        logger.exception("import failed, rolled back")
        return {"status": "failed", "stats": stats, "error": str(exc)}
    finally:
        conn.close()
