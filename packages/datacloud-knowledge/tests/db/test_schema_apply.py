"""Integration tests for whale_datacloud schema DDL."""

from __future__ import annotations

from pathlib import Path

import psycopg2
import pytest

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


def _split_sql_statements(sql_content: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    in_single_quote = False
    i = 0
    while i < len(sql_content):
        ch = sql_content[i]
        if ch == "'":
            if in_single_quote and i + 1 < len(sql_content) and sql_content[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_single_quote = not in_single_quote
            buf.append(ch)
            i += 1
            continue
        if ch == ";" and not in_single_quote:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _execute_ddl_directory(conn: psycopg2.extensions.connection, ddl_dir: Path) -> None:
    for sql_path in sorted(ddl_dir.glob("*.sql")):
        sql_content = sql_path.read_text(encoding="utf-8")
        for statement in _split_sql_statements(sql_content):
            with conn.cursor() as cur:
                cur.execute(statement)


@pytest.mark.db_integration
def test_database_connectivity(db_config: dict[str, str | int]) -> None:
    """Test that target database can be connected."""
    conn = psycopg2.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        dbname=db_config["database"],
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        conn.close()


@pytest.mark.db_integration
def test_apply_ddl_and_verify_tables(
    db_config: dict[str, str | int], ddl_dir: Path
) -> None:
    """Apply DDL under whale_datacloud and verify expected tables."""
    conn = psycopg2.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        dbname=db_config["database"],
    )
    try:
        conn.autocommit = False
        _execute_ddl_directory(conn, ddl_dir)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (db_config["schema"],),
            )
            existing = {row[0] for row in cur.fetchall()}
        missing = sorted(EXPECTED_TABLES - existing)
        assert not missing, f"missing tables in {db_config['schema']}: {', '.join(missing)}"
    finally:
        conn.close()
