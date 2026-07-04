"""个人 SQLite 动态表管理 — 直接操作本地 personal_object.db。

数据库路径：/byclaw-datacloud/personal_object.db
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Any

logger = logging.getLogger(__name__)

_TYPE_MAP: dict[str, str] = {
    "STRING": "TEXT",
    "INTEGER": "INTEGER",
    "FLOAT": "REAL",
    "BOOLEAN": "INTEGER",
    "DATE": "TEXT",
}

FIXED_DB_NAME = "personal_object.db"
_DDL_LOCK_TIMEOUT = 5.0  # 等待其他连接释放锁的最大秒数
_DDL_RETRY_INTERVAL = 0.1


def _db_path() -> str:
    mount = os.environ.get("FILE_STORAGE_MINIO_MOUNT_PATH", "")
    if not mount:
        raise RuntimeError("FILE_STORAGE_MINIO_MOUNT_PATH 环境变量未设置")
    return os.path.join(mount, "byclaw-datacloud", FIXED_DB_NAME)


def _ensure_db_dir() -> None:
    os.makedirs(os.path.dirname(_db_path()), exist_ok=True)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=_DDL_LOCK_TIMEOUT)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _execute_ddl(ddl: str, label: str) -> None:
    _ensure_db_dir()
    deadline = time.monotonic() + _DDL_LOCK_TIMEOUT
    last_error: Exception | None = None
    while True:
        conn = _connect()
        try:
            conn.execute(ddl)
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            last_error = exc
            if "locked" in str(exc).lower() and time.monotonic() < deadline:
                logger.warning("%s 被锁，重试中...", label)
                time.sleep(_DDL_RETRY_INTERVAL)
            else:
                raise RuntimeError(f"{label}失败: {exc}") from exc
        except sqlite3.Error as exc:
            raise RuntimeError(f"{label}失败: {exc}") from exc
        finally:
            conn.close()
    raise RuntimeError(f"{label}失败: {last_error}")


# ── 公开 API ──────────────────────────────────────────────────────────────────


def create_table(entity_code: str, fields: list[dict[str, Any]], _user_code: str = "") -> None:
    """在本地 SQLite 中创建动态表（IF NOT EXISTS）。

    Args:
        entity_code: 表名（即本体对象编码）。
        fields: 字段列表，每项含 property_code 和 data_type。
        _user_code: 已废弃，保留兼容。
    """
    col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
    for f in fields:
        col_name = f.get("property_code", "")
        if not col_name or col_name.lower() == "id":
            continue
        sqlite_type = _TYPE_MAP.get(f.get("data_type", "STRING"), "TEXT")
        col_defs.append(f"{col_name} {sqlite_type}")

    ddl = f"CREATE TABLE IF NOT EXISTS {entity_code} ({', '.join(col_defs)})"
    logger.info("create_table: entity=%s", entity_code)
    _execute_ddl(ddl, "建表")


def drop_table(entity_code: str, _user_code: str = "") -> None:
    """删除本地 SQLite 中的动态表（IF EXISTS）。

    Args:
        entity_code: 表名（即本体对象编码）。
        _user_code: 已废弃，保留兼容。
    """
    ddl = f"DROP TABLE IF EXISTS {entity_code}"
    logger.info("drop_table: entity=%s", entity_code)
    _execute_ddl(ddl, "删表")


def get_existing_columns(entity_code: str) -> list[str]:
    """返回表的现有列名列表（不含 id），表不存在时返回空列表。

    Args:
        entity_code: 表名（即本体对象编码）。
    """
    _ensure_db_dir()
    conn = _connect()
    try:
        cursor = conn.execute(f"PRAGMA table_info({entity_code})")
        rows = cursor.fetchall()
        return [row[1] for row in rows if row[1].lower() != "id"]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def add_columns(entity_code: str, fields: list[dict[str, Any]]) -> None:
    """为已有表增加新列（ALTER TABLE ADD COLUMN）。

    幂等：已存在的列跳过。

    Args:
        entity_code: 表名（即本体对象编码）。
        fields: 字段列表，每项含 property_code 和 data_type。
    """
    existing = set(get_existing_columns(entity_code))
    for f in fields:
        col_name = f.get("property_code", "")
        if not col_name or col_name.lower() == "id" or col_name in existing:
            continue
        sqlite_type = _TYPE_MAP.get(f.get("data_type", "STRING"), "TEXT")
        ddl = f"ALTER TABLE {entity_code} ADD COLUMN {col_name} {sqlite_type}"
        logger.info("add_column: entity=%s col=%s type=%s", entity_code, col_name, sqlite_type)
        _execute_ddl(ddl, f"新增列 {col_name}")
        existing.add(col_name)


def drop_columns(entity_code: str, column_names: list[str]) -> None:
    """从已有表删除指定列（ALTER TABLE DROP COLUMN，需 SQLite >= 3.35）。

    不存在的列跳过。

    Args:
        entity_code: 表名（即本体对象编码）。
        column_names: 要删除的列名列表。
    """
    existing = set(get_existing_columns(entity_code))
    for col_name in column_names:
        if col_name.lower() == "id" or col_name not in existing:
            continue
        ddl = f"ALTER TABLE {entity_code} DROP COLUMN {col_name}"
        logger.info("drop_column: entity=%s col=%s", entity_code, col_name)
        _execute_ddl(ddl, f"删除列 {col_name}")
