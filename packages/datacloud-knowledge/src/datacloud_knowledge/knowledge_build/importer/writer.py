"""知识包导入批量写入处理器。"""

from __future__ import annotations

import json
import logging
from typing import Any

from psycopg import Cursor

from ._helpers import (
    _execute_values,
    _lookup_term_ids_by_term_keys,
    _normalize_term_code,
    _str_id_if_set,
    _term_id_from_obj_or_code_direct,
)
from .snowflake import _next_snowflake_ids

logger = logging.getLogger(__name__)


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


def _is_prop_term_id(term_id: str) -> bool:
    """判断 term_id 本身是否为属性术语，而不是属性下的值术语。"""

    parts = term_id.split("#")
    return len(parts) >= 2 and parts[-2] == "prop"


def _term_name_search_scope_payload(search_scope: dict[str, str] | None) -> str:
    """序列化 term_name.search_scope。"""
    return json.dumps(search_scope or {}, ensure_ascii=False)


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


def _parse_relation_ext_field(ext_field: Any) -> dict[str, Any]:
    """解析 relation.ext_field JSON，失败时降级为空字典。"""
    if isinstance(ext_field, dict):
        return ext_field
    if not isinstance(ext_field, str):
        return {}

    raw = ext_field.strip()
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("relation ext_field JSON 解析失败，已跳过 scoped term_name 同步: %s", raw)
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _normalize_relation_scope_names(ext_field: dict[str, Any]) -> list[str]:
    """从 HAS_FIELD relation.ext_field 中提取并清洗 field_alias / synonyms。"""
    names: list[str] = []

    field_alias = ext_field.get("field_alias")
    if field_alias is not None:
        alias_text = str(field_alias).strip()
        if alias_text:
            names.append(alias_text)

    raw_synonyms = ext_field.get("synonyms")
    if isinstance(raw_synonyms, list):
        for item in raw_synonyms:
            synonym = str(item).strip()
            if synonym:
                names.append(synonym)

    return list(dict.fromkeys(names))


def _relation_scope_from_source_term_id(source_term_id: str) -> dict[str, str] | None:
    """根据 relation.source_term_id 推导对象/视图作用域。"""
    if "#object#" in source_term_id:
        _, _, object_code = source_term_id.partition("#object#")
        if object_code:
            return {"scope": "object", "code": object_code}

    if "#view#" in source_term_id:
        _, _, view_code = source_term_id.partition("#view#")
        if view_code:
            return {"scope": "view", "code": view_code}

    return None


def _batch_insert_relation_term_names(cur: Cursor, relation_ids: list[str]) -> int:
    """从 HAS_FIELD relation.ext_attrs 追加写入 scoped term_name。"""
    unique_relation_ids = list(dict.fromkeys(relation_ids))
    if not unique_relation_ids:
        return 0

    cur.execute(
        """SELECT relation_id, source_term_id, target_term_id, ext_attrs
           FROM term_relation
           WHERE relation_id = ANY(%s)""",
        (unique_relation_ids,),
    )

    scope_rows: list[tuple[str, str, str, str]] = []
    for _relation_id, source_term_id, target_term_id, ext_attrs in cur.fetchall():
        source_id = str(source_term_id)
        target_id = str(target_term_id)
        if not _is_prop_term_id(target_id):
            continue

        search_scope = _relation_scope_from_source_term_id(source_id)
        if search_scope is None:
            continue

        names = _normalize_relation_scope_names(_parse_relation_ext_field(ext_attrs))
        if not names:
            continue

        scope_payload = _term_name_search_scope_payload(search_scope)
        name_ids = _next_snowflake_ids(len(names))
        scope_rows.extend(
            (name_ids[index], target_id, name_text, scope_payload)
            for index, name_text in enumerate(names)
        )

    if not scope_rows:
        return 0

    cur.execute(
        "CREATE TEMP TABLE _tmp_rel_term_name (name_id VARCHAR, term_id VARCHAR, name_text VARCHAR, search_scope TEXT) ON COMMIT PRESERVE ROWS"
    )
    _execute_values(cur, "INSERT INTO _tmp_rel_term_name VALUES %s", scope_rows)
    cur.execute(
        """INSERT INTO term_name (name_id, term_id, name_text, search_scope)
           SELECT t.name_id, t.term_id, t.name_text, t.search_scope::jsonb
            FROM _tmp_rel_term_name t
            WHERE NOT EXISTS (
                SELECT 1 FROM term_name tn
                WHERE tn.term_id = t.term_id
                  AND tn.name_text = t.name_text
                  AND tn.search_scope @> t.search_scope::jsonb
            )"""
    )
    inserted_count = cur.rowcount
    cur.execute("DROP TABLE _tmp_rel_term_name")

    words = list({row[2] for row in scope_rows})
    if words:
        cur.execute(
            """INSERT INTO term_vocabulary (word)
               SELECT w FROM unnest(%s::text[]) AS t(w)
               WHERE NOT EXISTS (
                   SELECT 1 FROM term_vocabulary v WHERE v.word = t.w
               )""",
            (words,),
        )
    return inserted_count


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
    if updates:
        upd_rows = [
            (obj["relation_code"], obj.get("relation_name"), obj.get("ext_field"))
            for obj in updates
        ]
        cur.execute(
            "CREATE TEMP TABLE _tmp_rel_patch ("
            "  relation_id VARCHAR, relation_name VARCHAR, ext_attrs TEXT"
            ") ON COMMIT PRESERVE ROWS"
        )
        _execute_values(cur, "INSERT INTO _tmp_rel_patch VALUES %s", upd_rows)
        cur.execute("""
            UPDATE term_relation t
            SET relation_name = COALESCE(tmp.relation_name, t.relation_name),
                ext_attrs     = COALESCE(tmp.ext_attrs::jsonb, t.ext_attrs),
                updated_time  = CURRENT_TIMESTAMP
            FROM _tmp_rel_patch tmp
            WHERE t.relation_id = tmp.relation_id
        """)
        stats["relations"]["updated"] += cur.rowcount
        cur.execute("DROP TABLE _tmp_rel_patch")
    if not upserts:
        synced_term_name_count = _batch_insert_relation_term_names(
            cur,
            [obj["relation_code"] for obj in updates],
        )
        if synced_term_name_count:
            logger.info(
                "已从 HAS_FIELD relation 同步 scoped term_name: %s 条", synced_term_name_count
            )
        return
    ids = [o["relation_code"] for o in upserts]
    cur.execute(
        "SELECT relation_id FROM term_relation WHERE relation_id = ANY(%s)",
        (ids,),
    )
    existing = {r[0] for r in cur.fetchall()}
    to_insert = [o for o in upserts if o["relation_code"] not in existing]
    to_update = [o for o in upserts if o["relation_code"] in existing]

    if to_update:
        update_rows = [
            (
                obj["relation_code"],
                _term_id_from_obj_or_code_direct(
                    obj, id_key="source_term_id", code_key="source_term_code"
                ),
                _term_id_from_obj_or_code_direct(
                    obj, id_key="target_term_id", code_key="target_term_code"
                ),
                obj["relation_name"],
                obj.get("relation_category", "BUSINESS"),
                obj.get("cardinality"),
                obj.get("action_term_id"),
                obj.get("ext_field"),
            )
            for obj in to_update
        ]
        cur.execute(
            "CREATE TEMP TABLE _tmp_rel_upd ("
            "  relation_id VARCHAR,"
            "  source_term_id VARCHAR,"
            "  target_term_id VARCHAR,"
            "  relation_name VARCHAR,"
            "  relation_category VARCHAR,"
            "  cardinality VARCHAR,"
            "  action_term_id VARCHAR,"
            "  ext_attrs TEXT"
            ") ON COMMIT PRESERVE ROWS"
        )
        _execute_values(
            cur,
            "INSERT INTO _tmp_rel_upd VALUES %s",
            update_rows,
        )
        cur.execute("""
            UPDATE term_relation t
            SET source_term_id    = tmp.source_term_id,
                target_term_id    = tmp.target_term_id,
                relation_name     = tmp.relation_name,
                relation_category = tmp.relation_category,
                cardinality       = tmp.cardinality,
                action_term_id    = COALESCE(tmp.action_term_id, t.action_term_id),
                ext_attrs         = COALESCE(tmp.ext_attrs::jsonb, t.ext_attrs),
                updated_time      = CURRENT_TIMESTAMP
            FROM _tmp_rel_upd tmp
            WHERE t.relation_id = tmp.relation_id
        """)
        cur.execute("DROP TABLE _tmp_rel_upd")
        stats["relations"]["updated"] += len(update_rows)
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
                o.get("action_term_id"),
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

    synced_term_name_count = _batch_insert_relation_term_names(
        cur,
        [obj["relation_code"] for obj in updates]
        + [obj["relation_code"] for obj in to_update]
        + [obj["relation_code"] for obj in to_insert],
    )
    if synced_term_name_count:
        logger.info("已从 HAS_FIELD relation 同步 scoped term_name: %s 条", synced_term_name_count)


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
