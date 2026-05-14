"""term_type 批量写入处理器（内置类型不允许删除）。"""

from __future__ import annotations

from typing import Any

from psycopg import Cursor

from datacloud_knowledge.ingestion.owl_import.importer._helpers import _execute_values


def _resolve_type_category(obj: dict[str, Any]) -> int:
    category_map = {"列表术语": 1, "字典术语": 2, "本体术语": 3, "文档术语": 4}
    raw_cat = obj["type_category"]
    type_category = category_map.get(str(raw_cat))
    if type_category is None:
        type_category = int(raw_cat)
    return type_category


def _batch_process_term_type(
    cur: Cursor, objs: list[dict[str, Any]], stats: dict[str, Any]
) -> None:
    """批量写入 term_type(内置类型不允许删除)。"""
    if not objs:
        return
    deletes: list[str] = []
    updates: list[dict[str, Any]] = []
    upserts: list[dict[str, Any]] = []
    for obj in objs:
        op = obj.get("op", "add")
        if op == "delete":
            deletes.append(obj["type_code"])
        elif op == "update":
            updates.append(obj)
        else:
            upserts.append(obj)
    if deletes:
        cur.execute(
            "DELETE FROM term_type WHERE type_code = ANY(%s) AND is_builtin = FALSE",
            (deletes,),
        )
        stats["term_types"]["deleted"] += cur.rowcount
    for obj in updates:
        type_code = obj["type_code"]
        cur.execute(
            """UPDATE term_type
                  SET type_name     = COALESCE(%s, type_name),
                      type_desc     = COALESCE(%s, type_desc),
                      updated_time  = CURRENT_TIMESTAMP
                WHERE type_code = %s AND is_builtin = FALSE""",
            (obj.get("type_name"), obj.get("type_desc"), type_code),
        )
        stats["term_types"]["updated"] += cur.rowcount
    if not upserts:
        return
    ids = [o["type_code"] for o in upserts]
    cur.execute(
        "SELECT type_code FROM term_type WHERE type_code = ANY(%s)",
        (ids,),
    )
    existing = {r[0] for r in cur.fetchall()}
    to_insert = [o for o in upserts if o["type_code"] not in existing]
    to_update = [o for o in upserts if o["type_code"] in existing]
    for obj in to_update:
        type_code = obj["type_code"]
        cur.execute(
            """UPDATE term_type
                  SET type_name    = %s,
                      type_desc    = COALESCE(%s, type_desc),
                      updated_time = CURRENT_TIMESTAMP
                WHERE type_code = %s AND is_builtin = FALSE""",
            (obj["type_name"], obj.get("type_desc"), type_code),
        )
        stats["term_types"]["updated"] += 1
    if to_insert:
        rows = [
            (o["type_code"], o["type_name"], o.get("type_desc"), _resolve_type_category(o), False)
            for o in to_insert
        ]
        _execute_values(
            cur,
            """INSERT INTO term_type
                   (type_code, type_name, type_desc, type_category, is_builtin)
               VALUES %s""",
            rows,
            page_size=min(500, len(rows)),
        )
        stats["term_types"]["inserted"] += len(to_insert)
