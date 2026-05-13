"""term_knowledge 批量写入处理器。"""

from __future__ import annotations

from typing import Any

from psycopg import Cursor

from datacloud_knowledge.ingestion.owl_import.importer._helpers import (
    _execute_values,
    _str_id_if_set,
    _term_id_from_obj_or_code_direct,
)


def _batch_process_knowledge(
    cur: Cursor, objs: list[dict[str, Any]], stats: dict[str, Any]
) -> None:
    """批量写入 term_knowledge(term_id 外键；可显式传 term_id 或仅 term_code)。"""
    if not objs:
        return
    deletes: list[str] = []
    updates: list[dict[str, Any]] = []
    upserts: list[dict[str, Any]] = []
    for obj in objs:
        op = obj.get("op", "add")
        if op == "delete":
            deletes.append(obj["knowledge_id"])
        elif op == "update":
            updates.append(obj)
        else:
            upserts.append(obj)
    if deletes:
        cur.execute(
            "DELETE FROM term_knowledge WHERE knowledge_id = ANY(%s)",
            (deletes,),
        )
        stats["knowledge"]["deleted"] += cur.rowcount
    for obj in updates:
        knowledge_id = obj["knowledge_id"]
        cur.execute(
            """UPDATE term_knowledge
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
    if not upserts:
        return
    ids = [o["knowledge_id"] for o in upserts]
    cur.execute(
        "SELECT knowledge_id FROM term_knowledge WHERE knowledge_id = ANY(%s)",
        (ids,),
    )
    existing = {r[0] for r in cur.fetchall()}
    to_insert = [o for o in upserts if o["knowledge_id"] not in existing]
    to_update = [o for o in upserts if o["knowledge_id"] in existing]
    for obj in to_update:
        knowledge_id = obj["knowledge_id"]
        tid_new = _str_id_if_set(obj, "term_id")
        if tid_new is None and obj.get("term_code"):
            tid_new = _term_id_from_obj_or_code_direct(obj, id_key="term_id", code_key="term_code")
        cur.execute(
            """UPDATE term_knowledge
                  SET term_id      = COALESCE(%s, term_id),
                      desc_summary = %s,
                      "desc"       = %s,
                      ext_system   = %s,
                      ext_kb_id    = %s,
                      ext_doc_id   = %s,
                      sort_order   = %s,
                      updated_time = CURRENT_TIMESTAMP
                WHERE knowledge_id = %s""",
            (
                tid_new,
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
    if to_insert:
        rows = []
        for o in to_insert:
            tid = _str_id_if_set(o, "term_id")
            if tid is None and o.get("term_code"):
                tid = _term_id_from_obj_or_code_direct(o, id_key="term_id", code_key="term_code")
            rows.append(
                (
                    o["knowledge_id"],
                    tid,
                    o.get("desc_summary"),
                    o.get("desc"),
                    o.get("ext_system"),
                    o.get("ext_kb_id"),
                    o.get("ext_doc_id"),
                    o.get("sort_order", 0),
                )
            )
        _execute_values(
            cur,
            """INSERT INTO term_knowledge
                   (knowledge_id, term_id, desc_summary, "desc",
                    ext_system, ext_kb_id, ext_doc_id, sort_order)
               VALUES %s""",
            rows,
            page_size=min(500, len(rows)),
        )
        stats["knowledge"]["inserted"] += len(to_insert)
