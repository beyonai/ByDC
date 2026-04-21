"""知识包导入批量写入处理器。"""

from __future__ import annotations

import json
from typing import Any

from psycopg import Cursor

from ._helpers import (
    _execute_values,
    _lookup_term_ids_by_norm_codes,
    _normalize_term_code,
    _optional_term_id_from_obj,
    _str_id_if_set,
    _term_id_from_obj_or_code_direct,
)
from .snowflake import _next_snowflake_ids


def _resolve_type_category(obj: dict[str, Any]) -> int:
    category_map = {"列表术语": 1, "字典术语": 2, "本体术语": 3, "文档术语": 4}
    raw_cat = obj["type_category"]
    type_category = category_map.get(str(raw_cat))
    if type_category is None:
        type_category = int(raw_cat)
    return type_category


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


def _dedupe_term_name_sync_items(
    items: list[tuple[str, str, list[str]]],
) -> list[tuple[str, str, list[str]]]:
    """同一 term_id 出现多行时只保留最后一次，避免重复写入标准名/别名行。"""
    by_tid: dict[str, tuple[str, str, list[str]]] = {}
    for tid, name, aliases in items:
        by_tid[tid] = (tid, name, aliases)
    return list(by_tid.values())


def _batch_sync_term_names(
    cur: Cursor,
    items: list[tuple[str, str, list[str]]],
) -> int:
    """批量同步 term_name，并一次性补全 term_vocabulary（仍用 NOT EXISTS，兼容无 ON CONFLICT 的库）。"""
    if not items:
        return 0
    items = _dedupe_term_name_sync_items(items)
    term_ids = [t[0] for t in items]
    cur.execute(
        "DELETE FROM term_name WHERE term_id = ANY(%s)",
        (term_ids,),
    )

    # 预计算需要多少个 ID（每个 term_name + aliases）
    total_names = sum(
        1 + len([a for a in aliases if a and a != term_name]) for _, term_name, aliases in items
    )
    if total_names == 0:
        return 0

    # 批量生成雪花 ID
    name_ids = _next_snowflake_ids(total_names)

    all_rows: list[tuple[str, str, str]] = []
    id_idx = 0
    for term_id, term_name, aliases in items:
        # 主名称
        all_rows.append((name_ids[id_idx], term_id, term_name))
        id_idx += 1
        # 别名
        for alias in aliases:
            if alias and alias != term_name:
                all_rows.append((name_ids[id_idx], term_id, alias))
                id_idx += 1

    if not all_rows:
        return 0
    _execute_values(
        cur,
        """INSERT INTO term_name (name_id, term_id, name_text)
           VALUES %s""",
        all_rows,
        page_size=1000,  # 增大 page_size
    )
    words = list({row[2] for row in all_rows})
    if words:
        cur.execute(
            """INSERT INTO term_vocabulary (word)
               SELECT w FROM unnest(%s::text[]) AS t(w)
               WHERE NOT EXISTS (
                   SELECT 1 FROM term_vocabulary v WHERE v.word = t.w
               )""",
            (words,),
        )
    return len(all_rows)


def _batch_process_term(cur: Cursor, objs: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """批量写入 term 并批量同步 term_name / term_vocabulary。

    按唯一 term_code 更新已有行时不改 term_id。
    """
    if not objs:
        return
    deletes: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    upserts: list[dict[str, Any]] = []
    for obj in objs:
        op = obj.get("op", "add")
        if op == "delete":
            deletes.append(obj)
        elif op == "update":
            updates.append(obj)
        else:
            upserts.append(obj)
    if deletes:
        delete_norms = [_normalize_term_code(o["term_code"]) for o in deletes]
        delete_tid_map = _lookup_term_ids_by_norm_codes(cur, delete_norms)
        tids = [delete_tid_map[n] for n in delete_norms if n in delete_tid_map]
        if tids:
            cur.execute(
                "DELETE FROM term_name WHERE term_id = ANY(%s)",
                (tids,),
            )
            cur.execute(
                "DELETE FROM term WHERE term_id = ANY(%s)",
                (tids,),
            )
            stats["terms"]["deleted"] += cur.rowcount
    if updates:
        upd_codes = [_normalize_term_code(o["term_code"]) for o in updates]
        upd_tid_by_code = _lookup_term_ids_by_norm_codes(cur, upd_codes)
        for obj in updates:
            term_id = upd_tid_by_code.get(_normalize_term_code(obj["term_code"]))
            if not term_id:
                continue
            new_name = obj.get("term_name")
            cur.execute(
                """UPDATE term
                      SET term_name      = COALESCE(%s, term_name),
                          desc_summary   = COALESCE(%s, desc_summary),
                          updated_time   = CURRENT_TIMESTAMP
                    WHERE term_id = %s""",
                (new_name, obj.get("desc_summary"), term_id),
            )
            stats["terms"]["updated"] += cur.rowcount
    need_sync_upd = [o for o in updates if o.get("term_name") or o.get("aliases") is not None]
    if need_sync_upd:
        tids_nc = [_normalize_term_code(o["term_code"]) for o in need_sync_upd]
        tid_by_code = _lookup_term_ids_by_norm_codes(cur, tids_nc)
        id_list = list(dict.fromkeys(tid_by_code.values()))
        if id_list:
            cur.execute(
                "SELECT term_id, term_name FROM term WHERE term_id = ANY(%s)",
                (id_list,),
            )
            db_names = {r[0]: r[1] for r in cur.fetchall()}
            sync_items: list[tuple[str, str, list[str]]] = []
            for o in need_sync_upd:
                tid = tid_by_code.get(_normalize_term_code(o["term_code"]))
                if tid and tid in db_names:
                    sync_items.append((tid, db_names[tid], o.get("aliases") or []))
            if sync_items:
                _batch_sync_term_names(cur, sync_items)
    if not upserts:
        return
    upsert_norms = [_normalize_term_code(o["term_code"]) for o in upserts]
    existing_map = _lookup_term_ids_by_norm_codes(cur, upsert_norms)
    to_insert = [o for o in upserts if _normalize_term_code(o["term_code"]) not in existing_map]
    to_update = [o for o in upserts if _normalize_term_code(o["term_code"]) in existing_map]
    # 批量 UPDATE：使用临时表 + UPDATE JOIN，避免逐行 SQL
    if to_update:
        update_rows = []
        for obj in to_update:
            term_id = existing_map[_normalize_term_code(obj["term_code"])]
            term_code = _normalize_term_code(obj["term_code"])
            aliases = obj.get("aliases") or []
            term_tags = json.dumps({"aliases": aliases}, ensure_ascii=False) if aliases else "{}"
            update_rows.append(
                (
                    term_id,
                    term_code,
                    obj["term_name"],
                    obj.get("desc_summary"),
                    obj["domain_code"],
                    obj["term_type_code"],
                    obj.get("library_code"),
                    obj.get("owl_doc_file"),
                    term_tags,
                )
            )
        if update_rows:
            # 使用临时表 + UPDATE JOIN，避免逐行 SQL
            # OpenGauss 不支持 ON COMMIT DROP，使用 PRESERVE ROWS + 手动删除
            cur.execute(
                "CREATE TEMP TABLE _tmp_term_upd (term_id VARCHAR, term_code VARCHAR, term_name VARCHAR, desc_summary VARCHAR, domain_id VARCHAR, term_type_code VARCHAR, library_id VARCHAR, owl_doc_id VARCHAR, term_tags JSONB) ON COMMIT PRESERVE ROWS"
            )
            _execute_values(
                cur,
                "INSERT INTO _tmp_term_upd VALUES %s",
                update_rows,
            )
            cur.execute("""
                UPDATE term t
                SET term_code      = tmp.term_code,
                    term_name      = tmp.term_name,
                    desc_summary   = COALESCE(tmp.desc_summary, t.desc_summary),
                    domain_id      = tmp.domain_id,
                    term_type_code = tmp.term_type_code,
                    library_id     = tmp.library_id,
                    owl_doc_id     = tmp.owl_doc_id,
                    term_tags      = tmp.term_tags,
                    updated_time   = CURRENT_TIMESTAMP
                FROM _tmp_term_upd tmp
                WHERE t.term_id = tmp.term_id
            """)
            cur.execute("DROP TABLE _tmp_term_upd")
            stats["terms"]["updated"] += len(update_rows)
    if to_insert:
        insert_rows: list[tuple[Any, ...]] = []
        for _i, obj in enumerate(to_insert):
            term_code = _normalize_term_code(obj["term_code"])
            term_tags = "{}"
            insert_rows.append(
                (
                    obj["term_id"],
                    term_code,
                    obj["term_name"],
                    obj.get("term_desc"),
                    obj["domain_code"],
                    obj["term_type_code"],
                    obj.get("library_code"),
                    obj.get("owl_doc_file"),
                    term_tags,
                    obj.get("ext_field"),
                )
            )
        _execute_values(
            cur,
            """INSERT INTO term
                   (term_id, term_code, term_name, desc_summary, domain_id,
                    term_type_code, library_id, owl_doc_id, term_tags, ext_attrs)
               VALUES %s""",
            insert_rows,
            page_size=1000,  # 增大 page_size
        )
        stats["terms"]["inserted"] += len(to_insert)
        # 复用 existing_map，避免重复查询
        for obj in to_insert:
            existing_map[_normalize_term_code(obj["term_code"])] = obj["term_id"]
    # 使用 existing_map 代替 after_map，避免重复查询
    sync_upsert: list[tuple[str, str, list[str]]] = []
    for o in upserts:
        tid = _str_id_if_set(o, "term_id")
        if tid is None:
            tid = existing_map[_normalize_term_code(o["term_code"])]
        sync_upsert.append((tid, o["term_name"], o.get("aliases") or []))
    _batch_sync_term_names(cur, sync_upsert)


def _batch_process_relation(cur: Cursor, objs: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """批量写入 term_relation。

    新版 convert_relation 返回:
    - source_term_code: 格式为 {library}_{type}_{code}，即 term_id 格式
    - target_term_code: 格式为 {library}_{type}_{code}，即 term_id 格式
    - ext_field: 包含 joinkeys 的 JSON，存入 ext_attrs
    """
    if not objs:
        return
    deletes: list[str] = []
    updates: list[dict[str, Any]] = []
    upserts: list[dict[str, Any]] = []
    for obj in objs:
        op = obj.get("op", "add")
        if op == "delete":
            deletes.append(obj["relation_code"])
        elif op == "update":
            updates.append(obj)
        else:
            upserts.append(obj)
    if deletes:
        cur.execute(
            "DELETE FROM term_relation WHERE relation_id = ANY(%s)",
            (deletes,),
        )
        stats["relations"]["deleted"] += cur.rowcount
    for obj in updates:
        relation_id = obj["relation_code"]
        cur.execute(
            """UPDATE term_relation
                  SET relation_name = COALESCE(%s, relation_name),
                      ext_attrs     = COALESCE(%s::jsonb, ext_attrs),
                      updated_time  = CURRENT_TIMESTAMP
                WHERE relation_id = %s""",
            (obj.get("relation_name"), obj.get("ext_field"), relation_id),
        )
        stats["relations"]["updated"] += cur.rowcount
    if not upserts:
        return
    ids = [o["relation_code"] for o in upserts]
    cur.execute(
        "SELECT relation_id FROM term_relation WHERE relation_id = ANY(%s)",
        (ids,),
    )
    existing = {r[0] for r in cur.fetchall()}
    to_insert = [o for o in upserts if o["relation_code"] not in existing]
    to_update = [o for o in upserts if o["relation_code"] in existing]

    # 收集需要查找 term_id 的 code（仅用于 action_term_code）
    # 收集需要查找 term_id 的 code（仅用于 action_term_code）
    ref_codes: list[str] = [
        _normalize_term_code(o["action_term_code"])
        for o in to_insert + to_update
        if _str_id_if_set(o, "action_term_id") is None and o.get("action_term_code")
    ]
    code_to_tid = _lookup_term_ids_by_norm_codes(cur, ref_codes) if ref_codes else {}

    for obj in to_update:
        relation_id = obj["relation_code"]
        cur.execute(
            """UPDATE term_relation
                  SET source_term_id    = %s,
                      target_term_id    = %s,
                      relation_name     = %s,
                      relation_category = %s,
                      cardinality       = %s,
                      action_term_id    = COALESCE(%s, action_term_id),
                      ext_attrs         = COALESCE(%s::jsonb, ext_attrs),
                      updated_time      = CURRENT_TIMESTAMP
                WHERE relation_id = %s""",
            (
                _term_id_from_obj_or_code_direct(
                    obj, id_key="source_term_id", code_key="source_term_code"
                ),
                _term_id_from_obj_or_code_direct(
                    obj, id_key="target_term_id", code_key="target_term_code"
                ),
                obj["relation_name"],
                obj.get("relation_category", "BUSINESS"),
                obj.get("cardinality"),
                _optional_term_id_from_obj(
                    obj,
                    id_key="action_term_id",
                    code_key="action_term_code",
                    code_to_tid=code_to_tid,
                ),
                obj.get("ext_field"),
                relation_id,
            ),
        )
        stats["relations"]["updated"] += 1
    if to_insert:
        rows = [
            (
                o["relation_code"],
                _term_id_from_obj_or_code_direct(
                    o, id_key="source_term_id", code_key="source_term_code"
                ),
                _term_id_from_obj_or_code_direct(
                    o, id_key="target_term_id", code_key="target_term_code"
                ),
                o["relation_name"],
                o.get("relation_category", "BUSINESS"),
                o.get("cardinality"),
                _optional_term_id_from_obj(
                    o,
                    id_key="action_term_id",
                    code_key="action_term_code",
                    code_to_tid=code_to_tid,
                ),
                o.get("ext_field"),
            )
            for o in to_insert
        ]
        _execute_values(
            cur,
            """INSERT INTO term_relation
                   (relation_id, source_term_id, target_term_id,
                    relation_name, relation_category, cardinality, action_term_id, ext_attrs)
               VALUES %s""",
            rows,
            page_size=min(500, len(rows)),
        )
        stats["relations"]["inserted"] += len(to_insert)


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
    kn_upd_codes: list[str] = [
        _normalize_term_code(obj["term_code"])
        for obj in to_update
        if _str_id_if_set(obj, "term_id") is None and obj.get("term_code")
    ]
    kn_upd_tid_map = _lookup_term_ids_by_norm_codes(cur, kn_upd_codes)
    for obj in to_update:
        knowledge_id = obj["knowledge_id"]
        tid_new = _str_id_if_set(obj, "term_id")
        if tid_new is None and obj.get("term_code"):
            tid_new = kn_upd_tid_map.get(_normalize_term_code(obj["term_code"]))
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
        k_codes = [
            _normalize_term_code(o["term_code"])
            for o in to_insert
            if _str_id_if_set(o, "term_id") is None
        ]
        k_code_to_tid = _lookup_term_ids_by_norm_codes(cur, k_codes)
        rows = []
        for o in to_insert:
            tid = _str_id_if_set(o, "term_id")
            if tid is None:
                tid = k_code_to_tid[_normalize_term_code(o["term_code"])]
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
