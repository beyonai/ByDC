"""Apply whale_datacloud DDL files then seed initial data.

执行顺序：
  1. DDL（db/ddl/whale_datacloud/*.sql）：先 drop schema，再建表
  2. Seed（db/seed/whale_datacloud/*.sql）：写入系统预置数据，幂等
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import psycopg2

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DDL_DIR  = _ROOT / "db" / "ddl"  / "whale_datacloud"
_SEED_DIR = _ROOT / "db" / "seed" / "whale_datacloud"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"missing required env var: {name}")
    return value


def _connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=_required_env("DB_HOST"),
        port=int(_required_env("DB_PORT")),
        user=_required_env("DB_USER"),
        password=_required_env("DB_PASSWORD"),
        dbname=_required_env("DB_NAME"),
    )


def _sql_files(directory: Path) -> list[Path]:
    """Return sorted .sql files in directory; empty list if dir does not exist."""
    if not directory.exists():
        return []
    files = sorted(directory.glob("*.sql"))
    return files


def apply_ddl() -> None:
    """Drop existing tables and re-create schema from DDL files."""
    files = _sql_files(_DDL_DIR)
    if not files:
        raise ValueError(f"no DDL files found in {_DDL_DIR}")

    # 00_create_schema.sql 含 DROP TABLE，须在 autocommit 模式下执行
    schema_file, *rest_files = files
    conn = _connect()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            logger.info("executing %s (autocommit)", schema_file.name)
            cur.execute(schema_file.read_text(encoding="utf-8"))
    finally:
        conn.close()

    # 剩余建表文件在事务内执行，失败整体回滚
    conn = _connect()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            for f in rest_files:
                logger.info("executing %s", f.name)
                cur.execute(f.read_text(encoding="utf-8"))
        conn.commit()
        logger.info("DDL applied successfully (%d files)", len(rest_files))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_seed() -> None:
    """Insert system preset data (idempotent via ON CONFLICT DO NOTHING)."""
    files = _sql_files(_SEED_DIR)
    if not files:
        logger.info("no seed files found in %s, skipping", _SEED_DIR)
        return

    conn = _connect()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            for f in files:
                logger.info("seeding %s", f.name)
                cur.execute(f.read_text(encoding="utf-8"))
        conn.commit()
        logger.info("seed applied successfully (%d files)", len(files))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    """Apply DDL then seed data for whale_datacloud schema.

    Usage:
        python apply_whale_datacloud.py            # 完整初始化（DDL + Seed）
        python apply_whale_datacloud.py --seed-only  # 仅执行 Seed（幂等，不 drop 表）
    """
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if "--seed-only" in sys.argv:
        apply_seed()
    else:
        apply_ddl()
        apply_seed()


if __name__ == "__main__":
    main()
