"""Verify whale_datacloud schema and core tables."""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

EXPECTED_TABLES = {
    "domain",
    "term",
    "term_knowledge",
    "term_library",
    "term_name",
    "term_vocabulary",
    "term_type",
    "term_relation",
}

_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _ROOT / "src"

if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

def main() -> None:
    """Verify schema existence and expected table set."""
    from datacloud_knowledge.db_url import build_postgres_connection_uri, resolve_knowledge_schema

    schema = resolve_knowledge_schema()

    conn = psycopg2.connect(dsn=build_postgres_connection_uri())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (schema,),
            )
            actual_tables = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    missing = sorted(EXPECTED_TABLES - actual_tables)
    if missing:
        raise AssertionError(f"missing tables in {schema}: {', '.join(missing)}")


if __name__ == "__main__":
    main()
