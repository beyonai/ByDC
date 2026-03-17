"""Apply whale_datacloud DDL files in sorted order."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import psycopg2

logger = logging.getLogger(__name__)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"missing required env var: {name}")
    return value


def _read_sql_files(ddl_dir: Path) -> list[str]:
    sql_files = sorted(ddl_dir.glob("*.sql"))
    if not sql_files:
        raise ValueError(f"no ddl files found in {ddl_dir}")
    return [p.read_text(encoding="utf-8") for p in sql_files]


def main() -> None:
    """Apply all DDL files under db/ddl/whale_datacloud."""
    root = Path(__file__).resolve().parents[2]
    ddl_dir = root / "db" / "ddl" / "whale_datacloud"

    host = _required_env("DB_HOST")
    port = int(_required_env("DB_PORT"))
    user = _required_env("DB_USER")
    password = _required_env("DB_PASSWORD")
    dbname = _required_env("DB_NAME")

    ddl_sql_list = _read_sql_files(ddl_dir)
    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            for ddl_sql in ddl_sql_list:
                cur.execute(ddl_sql)
        conn.commit()
        logger.info("applied whale_datacloud ddl successfully")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
