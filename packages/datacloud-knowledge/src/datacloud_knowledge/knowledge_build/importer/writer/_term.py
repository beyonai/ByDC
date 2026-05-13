"""term 批量写入处理器（含 term_name 同步与递归 CTE 删除）。"""

from __future__ import annotations

import json
from typing import Any

from psycopg import Cursor

from datacloud_knowledge.knowledge_build.importer._helpers import (
    _execute_values,
    _lookup_term_ids_by_term_keys,
    _normalize_term_code,
    _str_id_if_set,
)
from datacloud_knowledge.knowledge_build.importer.snowflake import _next_snowflake_ids

from ._base import _term_name_search_scope_payload
from ._vocabulary import _batch_insert_vocabulary_words


def _dedupe_term_name_sync_items(
    items: list[tuple[str, str, list[str]]],
) -> list[tuple[str, str, list[str]]]:
    """同一 term_id 出现多行时只保留最后一次，避免重复写入标准名/别名行。"""
    by_tid: dict[str, tuple[str, str, list[str]]] = {}
    for tid, name, aliases in items:
        by_tid[tid] = (tid, name, aliases)
    return list(by_tid.values())


def _delete_global_prop_term_names(
    cur: Cursor,
    items: list[tuple[str, str, list[str]]],
    *,
    skip_delete_ids: set[str] | None = None,
) -> int:
    """删除历史导入产生的全局属性名称，避免跨对象/视图召回泄漏。"""
    if skip_delete_ids is not None:
        delete_ids = [
            term_id for term_id, _term_name, _aliases in items if term_id not in skip_delete_ids
        ]
    else:
        delete_ids = [term_id for term_id, _term_name, _aliases in items]
    if not delete_ids:
        return 0

    cur.execute(
        """DELETE FROM term_name
           WHERE term_id = ANY(%s)
             AND (
                 search_scope @> %s::jsonb
                 OR search_scope = '{}'::jsonb
             )""",
        (
            list(dict.fromkeys(delete_ids)),
            _term_name_search_scope_payload({"scope": "global"}),
        ),
    )
    return int(cur.rowcount or 0)


def _split_term_name_items_by_prop_scope(
    items: list[tuple[str, str, str, list[str]]],
) -> tuple[list[tuple[str, str, list[str]]], list[tuple[str, str, list[str]]]]:
    """将属性术语与非属性术语的名称同步项拆分。"""
    prop_items: list[tuple[str, str, list[str]]] = []
    other_items: list[tuple[str, str, list[str]]] = []
    for term_id, term_type_code, term_name, aliases in items:
        item = (term_id, term_name, aliases)
        if term_type_code == "prop":
            prop_items.append(item)
        else:
            other_items.append(item)
    return prop_items, other_items


def _batch_sync_term_names(
    cur: Cursor,
    items: list[tuple[str, str, list[str]]],
    *,
    skip_delete_ids: set[str] | None = None,
    search_scope: dict[str, str] | None = None,
) -> int:
    """批量同步 term_name，并一次性补全 term_vocabulary。

    skip_delete_ids: 这些 term_id 是新插入的，跳过 DELETE（无旧数据）。
    """
    if not items:
        return 0
    items = _dedupe_term_name_sync_items(items)

    # 只对已有 term 做 DELETE（新增 term 无旧 name 行）
    if skip_delete_ids is not None:
        delete_ids = [t[0] for t in items if t[0] not in skip_delete_ids]
    else:
        delete_ids = [t[0] for t in items]
    if delete_ids:
        if search_scope is None:
            cur.execute(
                "DELETE FROM term_name WHERE term_id = ANY(%s)",
                (delete_ids,),
            )
        else:
            cur.execute(
                "DELETE FROM term_name WHERE term_id = ANY(%s) AND search_scope @> %s::jsonb",
                (delete_ids, _term_name_search_scope_payload(search_scope)),
            )

    # 预计算需要多少个 ID（每个 term_name + aliases）
    total_names = sum(
        1 + len([a for a in aliases if a and a != term_name]) for _, term_name, aliases in items
    )
    if total_names == 0:
        return 0

    # 批量生成雪花 ID
    name_ids = _next_snowflake_ids(total_names)

    all_rows: list[tuple[str, str, str, str]] = []
    id_idx = 0
    scope_payload = _term_name_search_scope_payload(search_scope)
    for term_id, term_name, aliases in items:
        # 主名称
        all_rows.append((name_ids[id_idx], term_id, term_name, scope_payload))
        id_idx += 1
        # 别名
        for alias in aliases:
            if alias and alias != term_name:
                all_rows.append((name_ids[id_idx], term_id, alias, scope_payload))
                id_idx += 1

    if not all_rows:
        return 0
    _execute_values(
        cur,
        """INSERT INTO term_name (name_id, term_id, name_text, search_scope)
           VALUES %s""",
        all_rows,
        page_size=2000,
    )
    words = list({row[2] for row in all_rows})
    _batch_insert_vocabulary_words(cur, words)
    return len(all_rows)


def _batch_process_term(cur: Cursor, objs: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """批量写入 term 并批量同步 term_name / term_vocabulary。

    按唯一 term_code 更新已有行时不改 term_id。
    """
    if not objs:
        return

    def _term_key(obj: dict[str, Any]) -> tuple[str | None, str, str | None, str]:
        parent_term_id = _str_id_if_set(obj, "parent_term_id")
        return (
            _str_id_if_set(obj, "library_id") or _str_id_if_set(obj, "library_code"),
            str(obj["term_type_code"]),
            parent_term_id,
            _normalize_term_code(obj["term_code"]),
        )

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
        delete_tid_map = _lookup_term_ids_by_term_keys(cur, [_term_key(o) for o in deletes])
        tids = [delete_tid_map[_term_key(o)] for o in deletes if _term_key(o) in delete_tid_map]
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
        upd_tid_by_code = _lookup_term_ids_by_term_keys(cur, [_term_key(o) for o in updates])
        for obj in updates:
            term_id = upd_tid_by_code.get(_term_key(obj))
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
        tid_by_code = _lookup_term_ids_by_term_keys(cur, [_term_key(o) for o in need_sync_upd])
        id_list = list(dict.fromkeys(tid_by_code.values()))
        if id_list:
            cur.execute(
                "SELECT term_id, term_name FROM term WHERE term_id = ANY(%s)",
                (id_list,),
            )
            db_names = {r[0]: r[1] for r in cur.fetchall()}
            sync_items: list[tuple[str, str, str, list[str]]] = []
            for o in need_sync_upd:
                tid = tid_by_code.get(_term_key(o))
                if tid and tid in db_names:
                    sync_items.append(
                        (
                            tid,
                            str(o.get("term_type_code") or ""),
                            db_names[tid],
                            o.get("aliases") or [],
                        )
                    )
            if sync_items:
                prop_items, other_items = _split_term_name_items_by_prop_scope(sync_items)
                if other_items:
                    _batch_sync_term_names(cur, other_items)
                if prop_items:
                    _delete_global_prop_term_names(cur, prop_items)
    if not upserts:
        return
    # 按 term_id 判断是否已存在（term_id = library#type#code，全局唯一）
    upsert_ids = list(dict.fromkeys(o["term_id"] for o in upserts))
    cur.execute(
        "SELECT term_id FROM term WHERE term_id = ANY(%s)",
        (upsert_ids,),
    )
    existing_ids: set[str] = {r[0] for r in cur.fetchall()}
    to_insert = [o for o in upserts if o["term_id"] not in existing_ids]
    to_update = [o for o in upserts if o["term_id"] in existing_ids]
    # 批量 UPDATE：使用临时表 + UPDATE JOIN，避免逐行 SQL
    if to_update:
        update_rows = []
        for obj in to_update:
            term_id = obj["term_id"]
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
                    obj.get("parent_term_id"),
                    obj.get("library_code"),
                    obj.get("owl_doc_file"),
                    term_tags,
                )
            )
        if update_rows:
            # 使用临时表 + UPDATE JOIN，避免逐行 SQL
            # OpenGauss 不支持 ON COMMIT DROP，使用 PRESERVE ROWS + 手动删除
            cur.execute(
                "CREATE TEMP TABLE _tmp_term_upd (term_id VARCHAR, term_code VARCHAR, term_name VARCHAR, desc_summary VARCHAR, domain_id VARCHAR, term_type_code VARCHAR, parent_term_id VARCHAR(1000), library_id VARCHAR, owl_doc_id VARCHAR, term_tags JSONB) ON COMMIT PRESERVE ROWS"
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
                    parent_term_id = tmp.parent_term_id,
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
                    obj.get("parent_term_id"),
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
                    term_type_code, parent_term_id, library_id, owl_doc_id, term_tags, ext_attrs)
               VALUES %s""",
            insert_rows,
            page_size=1000,  # 增大 page_size
        )
        stats["terms"]["inserted"] += len(to_insert)
    # 直接使用 obj["term_id"]，不再依赖 existing_map
    sync_upsert: list[tuple[str, str, str, list[str]]] = []
    for o in upserts:
        sync_upsert.append(
            (
                o["term_id"],
                str(o.get("term_type_code") or ""),
                o["term_name"],
                o.get("aliases") or [],
            )
        )
    # 新增 term 无旧 name 行，跳过 DELETE 加速
    new_ids = {o["term_id"] for o in to_insert}
    prop_items, other_items = _split_term_name_items_by_prop_scope(sync_upsert)
    if other_items:
        _batch_sync_term_names(cur, other_items, skip_delete_ids=new_ids)
    if prop_items:
        _delete_global_prop_term_names(cur, prop_items, skip_delete_ids=new_ids)
