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
from psycopg import Connection, Cursor

from . import owl_converter, owl_parser
from .snowflake import _next_snowflake_id, _next_snowflake_ids


# execute_values 在 psycopg3 中不可用，使用自定义实现
def _execute_values(
    cur: Cursor,
    sql: str,
    argslist: list[tuple[Any, ...]],
    page_size: int = 1000,
    _template: str | None = None,
) -> None:
    """批量执行 INSERT/UPDATE，模拟 psycopg2 的 execute_values。

    psycopg3 不内置 execute_values，此实现使用 executemany 或分批执行。
    template 参数用于兼容性（在 psycopg3 中不使用，因为通过 executemany 实现）。
    """
    if not argslist:
        return
    # 将 VALUES %s 格式转换为 (%s,%s,...) 元组格式
    # 使用 executemany 进行批量执行
    placeholders = "(" + ",".join(["%s"] * len(argslist[0])) + ")"
    sql_with_placeholders = sql.replace("VALUES %s", f"VALUES {placeholders}")
    # 忽略 template 参数 - 在 psycopg3 中不需要，executemany 会自动处理类型转换
    for i in range(0, len(argslist), page_size):
        batch = argslist[i : i + page_size]
        cur.executemany(sql_with_placeholders, batch)


logger = logging.getLogger(__name__)


# JSONL 每批解析后入库的行数（环境变量可覆盖，过大可能增加单次事务内存）
# 性能优化：默认 2000，提速 4x（原 500）
def _import_batch_size() -> int:
    raw = os.getenv("DATACLOUD_KNOWLEDGE_IMPORT_BATCH_SIZE", "2000").strip()
    if not raw.isdigit() or int(raw) < 1:
        return 2000
    return min(int(raw), 10_000)


def _iter_jsonl_obj_batches(file_path: Path, batch_size: int) -> Any:
    """流式按批产出 JSON 对象，按行读文件，避免整文件载入内存。"""
    batch: list[dict[str, Any]] = []
    with file_path.open(encoding="utf-8") as f:
        for raw_line in f:
            stripped_line = raw_line.strip()
            if not stripped_line:
                continue
            batch.append(json.loads(stripped_line))
            if len(batch) >= batch_size:
                yield batch
                batch = []
    if batch:
        yield batch


def _normalize_term_code(s: str) -> str:
    """Normalize term_code to satisfy DB constraint ^[A-Z][A-Z0-9_]{1,63}$.

    Replace non-alphanumeric with underscore, uppercase, ensure first char is letter.
    """
    return s
    # if not s:
    #     return "T_EMPTY"
    # normalized = re.sub(r"[^A-Za-z0-9_]", "_", s).upper()[:64]
    # if not normalized or normalized[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    #     normalized = "T" + (normalized or "0")
    # return normalized[:64]


def _term_name_row_tuples(
    term_id: str, term_name: str, aliases: list[str]
) -> list[tuple[str, str, str]]:
    """name 行构造（name_id, term_id, name_text）；name_id 每条均为雪花 ID。"""
    rows: list[tuple[str, str, str]] = [(_next_snowflake_id(), term_id, term_name)]
    rows.extend(
        (_next_snowflake_id(), term_id, alias) for alias in aliases if alias and alias != term_name
    )
    return rows


def _lookup_term_ids_by_norm_codes(cur: Cursor, norm_codes: list[str]) -> dict[str, str]:
    """规范化 term_code → term.term_id（用于 relation / knowledge 等仅含 term_code 的引用）。"""
    uniq = list(dict.fromkeys(norm_codes))
    if not uniq:
        return {}
    cur.execute(
        """SELECT term_code, term_id FROM whale_datacloud.term
            WHERE term_code = ANY(%s)""",
        (uniq,),
    )
    return {r[0]: r[1] for r in cur.fetchall()}


def _str_id_if_set(obj: dict[str, Any], key: str) -> str | None:
    """JSON 中若显式提供 id（非空字符串），返回该值，用于写入外键 term_id 列。"""
    v = obj.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _term_id_from_obj_or_code(
    obj: dict[str, Any],
    *,
    id_key: str,
    code_key: str,
    code_to_tid: dict[str, str],
) -> str:
    """优先 JSON 中的 *term_id，否则用规范化 term_code 查 code_to_tid。"""
    tid = _str_id_if_set(obj, id_key)
    if tid is not None:
        return tid
    nc = _normalize_term_code(obj[code_key])
    return code_to_tid[nc]


def _optional_term_id_from_obj(
    obj: dict[str, Any],
    *,
    id_key: str,
    code_key: str,
    code_to_tid: dict[str, str],
) -> str | None:
    """与 _term_id_from_obj_or_code 类似，但 code 可缺省；用于 action_term 等可选外键。"""
    tid = _str_id_if_set(obj, id_key)
    if tid is not None:
        return tid
    raw = obj.get(code_key)
    if not raw:
        return None
    nc = _normalize_term_code(raw)
    return code_to_tid.get(nc)


def _term_id_from_obj_or_code_direct(
    obj: dict[str, Any],
    *,
    id_key: str,
    code_key: str,
) -> str:
    """优先 JSON 中的 *term_id，否则直接使用 code_key 的值作为 term_id。

    适用于新版 convert_relation 返回的 source_term_code/target_term_code，
    它们的格式已经是 {library}#{type}#{code}，即 term_id 格式。
    """
    tid = _str_id_if_set(obj, id_key)
    if tid is not None:
        return tid
    # 新版 code 字段值即为 term_id，直接返回
    return str(obj[code_key])


# ── DB 连接 ───────────────────────────────────────────────────────────────────


def _connect() -> Connection:
    """从环境变量建立 psycopg3 连接。

    可选环境变量：
    - DATACLOUD_DB_CONNECT_TIMEOUT：连接超时（秒），默认 30；仅影响建连阶段。
    - DATACLOUD_DB_LOCK_TIMEOUT_MS：锁等待超时（毫秒）。>0 时执行 SET lock_timeout，
      避免 INSERT/UPDATE 在等表锁/行锁时无限挂起；未设置则不启用（与 PostgreSQL 默认一致）。
    - DATACLOUD_DB_APPLICATION_NAME：会话 application_name（默认 datacloud_knowledge_import），
      便于在 pg_stat_activity / OpenGauss 监控里区分 Python 入库连接与 DBeaver。

    若入库卡在 domain 首条 INSERT，多为其他会话持有 whale_datacloud.* 上的锁且未提交，
    请在库上查阻塞会话或设置 DATACLOUD_DB_LOCK_TIMEOUT_MS=30000 快速得到 lock timeout 报错。
    """

    def _req(name: str) -> str:
        v = os.getenv(name, "").strip()
        if not v:
            raise ValueError(f"缺少环境变量: {name}")
        return v

    ct_raw = os.getenv("DATACLOUD_DB_CONNECT_TIMEOUT", "30").strip()
    connect_timeout = int(ct_raw) if ct_raw.isdigit() else 30

    app_name = os.getenv("DATACLOUD_DB_APPLICATION_NAME", "datacloud_knowledge_import").strip()
    if not app_name:
        app_name = "datacloud_knowledge_import"

    _kw: dict[str, Any] = {
        "host": _req("DB_HOST"),
        "port": int(_req("DB_PORT")),
        "user": _req("DB_USER"),
        "password": _req("DB_PASSWORD"),
        "dbname": _req("DB_NAME"),
        "connect_timeout": connect_timeout,
    }
    try:
        conn = psycopg.connect(**_kw, application_name=app_name)
    except TypeError:
        # 极旧 psycopg2 / 部分驱动不支持 application_name
        conn = psycopg.connect(**_kw)

    lock_raw = os.getenv("DATACLOUD_DB_LOCK_TIMEOUT_MS", "").strip()
    if lock_raw.isdigit() and int(lock_raw) > 0:
        lock_ms = int(lock_raw)
        prev_autocommit = conn.autocommit
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute("SET lock_timeout = %s", (lock_ms,))
        finally:
            conn.autocommit = prev_autocommit

    return conn


# ── 各实体入库处理器（批量优先；单行接口委托 _batch_*）──────────────────────────────


def _resolve_type_category(obj: dict[str, Any]) -> int:
    category_map = {"LIST_TERM": 1, "DICT_TERM": 2, "ONTOLOGY_TERM": 3, "DOCUMENT_TERM": 4}
    raw_cat = obj["type_category"]
    type_category = category_map.get(str(raw_cat))
    if type_category is None:
        type_category = int(raw_cat)
    return type_category


def _batch_process_domain(cur: Cursor, objs: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """批量写入 whale_datacloud.domain。"""
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
            "DELETE FROM whale_datacloud.domain WHERE domain_id = ANY(%s)",
            (deletes,),
        )
        stats["domains"]["deleted"] += cur.rowcount
    for obj in updates:
        cur.execute(
            """UPDATE whale_datacloud.domain
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
        "SELECT domain_id FROM whale_datacloud.domain WHERE domain_id = ANY(%s)",
        (ids,),
    )
    existing = {r[0] for r in cur.fetchall()}
    to_insert = [o for o in upserts if o["domain_code"] not in existing]
    to_update = [o for o in upserts if o["domain_code"] in existing]
    for obj in to_update:
        parent_code = obj.get("parent_code")
        cur.execute(
            """UPDATE whale_datacloud.domain
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
            """INSERT INTO whale_datacloud.domain
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
                    """UPDATE whale_datacloud.domain
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
    """批量写入 whale_datacloud.term_library。"""
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
            "DELETE FROM whale_datacloud.term_library WHERE library_id = ANY(%s)",
            (deletes,),
        )
        stats["libraries"]["deleted"] += cur.rowcount
    for obj in updates:
        library_id = obj["library_code"]
        cur.execute(
            """UPDATE whale_datacloud.term_library
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
        "SELECT library_id FROM whale_datacloud.term_library WHERE library_id = ANY(%s)",
        (ids,),
    )
    existing = {r[0] for r in cur.fetchall()}
    to_insert = [o for o in upserts if o["library_code"] not in existing]
    to_update = [o for o in upserts if o["library_code"] in existing]
    for obj in to_update:
        library_id = obj["library_code"]
        cur.execute(
            """UPDATE whale_datacloud.term_library
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
            """INSERT INTO whale_datacloud.term_library (library_id, library_code, library_name)
               VALUES %s""",
            rows,
            page_size=min(500, len(rows)),
        )
        stats["libraries"]["inserted"] += len(to_insert)


def _batch_process_term_type(
    cur: Cursor, objs: list[dict[str, Any]], stats: dict[str, Any]
) -> None:
    """批量写入 whale_datacloud.term_type(内置类型不允许删除)。"""
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
            "DELETE FROM whale_datacloud.term_type WHERE type_code = ANY(%s) AND is_builtin = FALSE",
            (deletes,),
        )
        stats["term_types"]["deleted"] += cur.rowcount
    for obj in updates:
        type_code = obj["type_code"]
        cur.execute(
            """UPDATE whale_datacloud.term_type
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
        "SELECT type_code FROM whale_datacloud.term_type WHERE type_code = ANY(%s)",
        (ids,),
    )
    existing = {r[0] for r in cur.fetchall()}
    to_insert = [o for o in upserts if o["type_code"] not in existing]
    to_update = [o for o in upserts if o["type_code"] in existing]
    for obj in to_update:
        type_code = obj["type_code"]
        cur.execute(
            """UPDATE whale_datacloud.term_type
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
            """INSERT INTO whale_datacloud.term_type
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
        "DELETE FROM whale_datacloud.term_name WHERE term_id = ANY(%s)",
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
        """INSERT INTO whale_datacloud.term_name (name_id, term_id, name_text)
           VALUES %s""",
        all_rows,
        page_size=1000,  # 增大 page_size
    )
    words = list({row[2] for row in all_rows})
    if words:
        cur.execute(
            """INSERT INTO whale_datacloud.term_vocabulary (word)
               SELECT w FROM unnest(%s::text[]) AS t(w)
               WHERE NOT EXISTS (
                   SELECT 1 FROM whale_datacloud.term_vocabulary v WHERE v.word = t.w
               )""",
            (words,),
        )
    return len(all_rows)


def _batch_process_term(cur: Cursor, objs: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """批量写入 whale_datacloud.term 并批量同步 term_name / term_vocabulary。

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
                "DELETE FROM whale_datacloud.term_name WHERE term_id = ANY(%s)",
                (tids,),
            )
            cur.execute(
                "DELETE FROM whale_datacloud.term WHERE term_id = ANY(%s)",
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
                """UPDATE whale_datacloud.term
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
                "SELECT term_id, term_name FROM whale_datacloud.term WHERE term_id = ANY(%s)",
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
                UPDATE whale_datacloud.term t
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
            """INSERT INTO whale_datacloud.term
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
    """批量写入 whale_datacloud.term_relation。

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
            "DELETE FROM whale_datacloud.term_relation WHERE relation_id = ANY(%s)",
            (deletes,),
        )
        stats["relations"]["deleted"] += cur.rowcount
    for obj in updates:
        relation_id = obj["relation_code"]
        cur.execute(
            """UPDATE whale_datacloud.term_relation
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
        "SELECT relation_id FROM whale_datacloud.term_relation WHERE relation_id = ANY(%s)",
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
            """UPDATE whale_datacloud.term_relation
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
            """INSERT INTO whale_datacloud.term_relation
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
    """批量写入 whale_datacloud.term_knowledge(term_id 外键；可显式传 term_id 或仅 term_code)。"""
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
            "DELETE FROM whale_datacloud.term_knowledge WHERE knowledge_id = ANY(%s)",
            (deletes,),
        )
        stats["knowledge"]["deleted"] += cur.rowcount
    for obj in updates:
        knowledge_id = obj["knowledge_id"]
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
    if not upserts:
        return
    ids = [o["knowledge_id"] for o in upserts]
    cur.execute(
        "SELECT knowledge_id FROM whale_datacloud.term_knowledge WHERE knowledge_id = ANY(%s)",
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
            """UPDATE whale_datacloud.term_knowledge
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
            """INSERT INTO whale_datacloud.term_knowledge
                   (knowledge_id, term_id, desc_summary, "desc",
                    ext_system, ext_kb_id, ext_doc_id, sort_order)
               VALUES %s""",
            rows,
            page_size=min(500, len(rows)),
        )
        stats["knowledge"]["inserted"] += len(to_insert)


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
        with conn.cursor() as cur:
            for step in import_steps:
                rel_file: str = step.get("file", "")
                step_type: str = step.get("type", "")
                entity_type = _step_entity_type(step_type, rel_file)
                batch_handler = _STEP_BATCH_HANDLERS.get(entity_type)
                if batch_handler is None:
                    logger.warning("未知 step type '%s', 跳过 %s", step_type, rel_file)
                    continue

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
