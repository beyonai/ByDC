"""domain 批量写入处理器。"""

from __future__ import annotations

from typing import Any

from psycopg import Cursor

from datacloud_knowledge.knowledge_build.importer._helpers import _execute_values


def _batch_process_domain(cur: Cursor, objs: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """批量写入 domain。"""
    if not objs:
        return
    deletes: list[str] = []
    updates: list[dict[str, Any]] = []
    upserts: list[dict[str, Any]] = []
    for obj in objs:
        op = obj.get("op", "add")
        if op == "delete":
            deletes.append(obj["domain_code"])
        elif op == "update":
            updates.append(obj)
        else:
            upserts.append(obj)
    if deletes:
        cur.execute(
            "DELETE FROM domain WHERE domain_id = ANY(%s)",
            (deletes,),
        )
        stats["domains"]["deleted"] += cur.rowcount
    for obj in updates:
        cur.execute(
            """UPDATE domain
                  SET domain_name  = COALESCE(%s, domain_name),
                      domain_desc  = COALESCE(%s, domain_desc),
                      updated_time = CURRENT_TIMESTAMP
                WHERE domain_id = %s""",
            (obj.get("domain_name"), obj.get("domain_desc"), obj["domain_code"]),
        )
        stats["domains"]["updated"] += cur.rowcount
    if not upserts:
        return
    ids = [o["domain_code"] for o in upserts]
    cur.execute(
        "SELECT domain_id FROM domain WHERE domain_id = ANY(%s)",
        (ids,),
    )
    existing = {r[0] for r in cur.fetchall()}
    to_insert = [o for o in upserts if o["domain_code"] not in existing]
    to_update = [o for o in upserts if o["domain_code"] in existing]
    for obj in to_update:
        parent_code = obj.get("parent_code")
        cur.execute(
            """UPDATE domain
                  SET domain_name  = %s,
                      domain_desc  = COALESCE(%s, domain_desc),
                      parent_id    = %s,
                      updated_time = CURRENT_TIMESTAMP
                WHERE domain_id = %s""",
            (obj["domain_name"], obj.get("domain_desc"), parent_code, obj["domain_code"]),
        )
        stats["domains"]["updated"] += 1
    if not to_insert:
        return
    rows = [
        (o["domain_code"], o["domain_name"], o.get("parent_code"), o.get("domain_desc"))
        for o in to_insert
    ]
    try:
        _execute_values(
            cur,
            """INSERT INTO domain
                   (domain_id, domain_name, parent_id, domain_desc)
               VALUES %s""",
            rows,
            page_size=min(500, len(rows)),
        )
        stats["domains"]["inserted"] += len(to_insert)
    except Exception as e:
        if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
            for obj in to_insert:
                parent_code = obj.get("parent_code")
                cur.execute(
                    """UPDATE domain
                          SET domain_name  = %s,
                              domain_desc  = COALESCE(%s, domain_desc),
                              parent_id    = %s,
                              updated_time = CURRENT_TIMESTAMP
                        WHERE domain_id = %s""",
                    (obj["domain_name"], obj.get("domain_desc"), parent_code, obj["domain_code"]),
                )
                stats["domains"]["updated"] += 1
        else:
            raise
