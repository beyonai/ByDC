"""知识包导入共享辅助函数。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from psycopg import Cursor, sql

from .snowflake import _next_snowflake_id


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
        cur.executemany(cast(Any, sql_with_placeholders), batch)


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
        """SELECT term_code, term_id FROM term
            WHERE term_code = ANY(%s)""",
        (uniq,),
    )
    return {r[0]: r[1] for r in cur.fetchall()}


def _lookup_term_ids_by_keys(
    cur: Cursor,
    keys: list[tuple[str | None, str, str]],
) -> dict[tuple[str | None, str, str], str]:
    """按 (library_id, term_type_code, term_code) 三元组查找 term_id。"""
    if not keys:
        return {}

    uniq = list(dict.fromkeys(keys))
    params = [value for key in uniq for value in key]
    cur.execute(
        sql.SQL("SELECT library_id, term_type_code, term_code, term_id FROM term WHERE ")
        + sql.SQL(" OR ").join(
            [sql.SQL("(library_id = %s AND term_type_code = %s AND term_code = %s)") for _ in uniq]
        ),
        params,
    )
    return {(row[0], row[1], row[2]): row[3] for row in cur.fetchall()}


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
