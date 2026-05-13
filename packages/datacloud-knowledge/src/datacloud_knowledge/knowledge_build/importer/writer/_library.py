"""term_library 批量写入处理器。"""

from __future__ import annotations

from typing import Any

from psycopg import Cursor

from datacloud_knowledge.knowledge_build.importer._helpers import _execute_values


def _batch_process_library(cur: Cursor, objs: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """批量写入 term_library。"""
    if not objs:
        return
    deletes: list[str] = []
    updates: list[dict[str, Any]] = []
    upserts: list[dict[str, Any]] = []
    for obj in objs:
        op = obj.get("op", "add")
        if op == "delete":
            deletes.append(obj["library_code"])
        elif op == "update":
            updates.append(obj)
        else:
            upserts.append(obj)
    if deletes:
        cur.execute(
            "DELETE FROM term_library WHERE library_id = ANY(%s)",
            (deletes,),
        )
        stats["libraries"]["deleted"] += cur.rowcount
    for obj in updates:
        library_id = obj["library_code"]
        cur.execute(
            """UPDATE term_library
                  SET library_code = %s,
                      library_name = COALESCE(%s, library_name),
                      updated_time = CURRENT_TIMESTAMP
                WHERE library_id = %s""",
            (library_id, obj.get("library_name"), library_id),
        )
        stats["libraries"]["updated"] += cur.rowcount
    if not upserts:
        return
    ids = [o["library_code"] for o in upserts]
    cur.execute(
        "SELECT library_id FROM term_library WHERE library_id = ANY(%s)",
        (ids,),
    )
    existing = {r[0] for r in cur.fetchall()}
    to_insert = [o for o in upserts if o["library_code"] not in existing]
    to_update = [o for o in upserts if o["library_code"] in existing]
    for obj in to_update:
        library_id = obj["library_code"]
        cur.execute(
            """UPDATE term_library
                  SET library_code = %s,
                      library_name = %s,
                      updated_time = CURRENT_TIMESTAMP
                WHERE library_id = %s""",
            (library_id, obj["library_name"], library_id),
        )
        stats["libraries"]["updated"] += 1
    if to_insert:
        rows = [(o["library_code"], o["library_code"], o["library_name"]) for o in to_insert]
        _execute_values(
            cur,
            """INSERT INTO term_library (library_id, library_code, library_name)
               VALUES %s""",
            rows,
            page_size=min(500, len(rows)),
        )
        stats["libraries"]["inserted"] += len(to_insert)
