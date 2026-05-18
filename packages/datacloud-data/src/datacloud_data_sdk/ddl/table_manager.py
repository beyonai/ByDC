"""个人 SQLite 动态表管理。

通过 PERSONAL_SQLITE_PATH 环境变量指定 SQLite 数据库文件路径。
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TYPE_MAP: dict[str, str] = {
    "STRING": "TEXT",
    "INTEGER": "INTEGER",
    "FLOAT": "REAL",
    "BOOLEAN": "INTEGER",
    "DATE": "TEXT",
}


def _get_db_path() -> Path:
    raw = os.environ.get("PERSONAL_SQLITE_PATH", "")
    if not raw:
        raise ValueError("PERSONAL_SQLITE_PATH 环境变量未配置")
    return Path(raw)


def create_table(entity_code: str, fields: list[dict[str, Any]], user_code: str) -> None:
    """在个人 SQLite 中创建动态表（IF NOT EXISTS）。

    Args:
        entity_code: 表名（即本体对象编码）。
        fields: 字段列表，每项含 property_code 和 data_type。
        user_code: 操作用户编码（记录日志用）。
    """
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
    for f in fields:
        col_name = f.get("property_code", "")
        if not col_name:
            continue
        sqlite_type = _TYPE_MAP.get(f.get("data_type", "STRING"), "TEXT")
        col_defs.append(f"{col_name} {sqlite_type}")

    ddl = f"CREATE TABLE IF NOT EXISTS {entity_code} ({', '.join(col_defs)})"
    logger.info("create_table: user=%s entity=%s ddl=%s", user_code, entity_code, ddl)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()


def drop_table(entity_code: str) -> None:
    """删除个人 SQLite 中的动态表（IF EXISTS）。

    Args:
        entity_code: 表名（即本体对象编码）。
    """
    db_path = _get_db_path()
    if not db_path.exists():
        return

    ddl = f"DROP TABLE IF EXISTS {entity_code}"
    logger.info("drop_table: entity=%s", entity_code)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()
