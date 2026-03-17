"""Verify whale_datacloud schema and core tables."""

from __future__ import annotations

import os

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


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"missing required env var: {name}")
    return value


def main() -> None:
    """Verify schema existence and expected table set."""
    host = _required_env("DB_HOST")
    port = int(_required_env("DB_PORT"))
    user = _required_env("DB_USER")
    password = _required_env("DB_PASSWORD")
    dbname = _required_env("DB_NAME")
    schema = os.getenv("DB_SCHEMA", "whale_datacloud")

    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
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
