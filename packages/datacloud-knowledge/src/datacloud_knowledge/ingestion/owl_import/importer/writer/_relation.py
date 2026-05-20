"""term_relation 批量写入处理器（含 scoped term_name 同步）。"""

from __future__ import annotations

import json
import logging
from typing import Any

from psycopg import Cursor

from datacloud_knowledge.ingestion.owl_import.importer._helpers import (
    _execute_values,
    _term_id_from_obj_or_code_direct,
)
from datacloud_knowledge.ingestion.owl_import.importer.snowflake import _next_snowflake_ids

from ._base import _is_prop_term_id, _term_name_search_scope_payload
from ._term import _backfill_jieba_tsvector_batch
from ._vocabulary import _batch_insert_vocabulary_words

logger = logging.getLogger(__name__)


def _warn_missing_category(obj: dict[str, Any], legacy_default: str) -> str:
    """当 relation_category 缺失时记录警告并返回安全默认值。

    正常情况下数据经 KPS pipeline 传递后 relation_category 总是存在，
    此函数仅作为兼容旧格式数据的最后兜底。
    """
    logger.warning(
        "relation_category 缺失 (relation_code=%s, relation_name=%s)，"
        "回退为旧默认值 '%s'。请检查上游 KPS pipeline 是否正确设置。",
        obj.get("relation_code", "?"),
        obj.get("relation_name", "?"),
        legacy_default,
    )
    return legacy_default


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

    # 回填 name_keywords_jieba（prop 术语走 relation term_name 路径，不走 _batch_sync_term_names）
    _backfill_jieba_tsvector_batch(cur, scope_rows)

    words = list({row[2] for row in scope_rows})
    _batch_insert_vocabulary_words(cur, words)
    return inserted_count


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
                obj.get("relation_category") or _warn_missing_category(obj, "HAS_OBJECT"),
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
                o.get("relation_category") or _warn_missing_category(o, "HAS_OBJECT"),
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
