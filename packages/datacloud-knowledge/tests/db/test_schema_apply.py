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


def _execute_sql_file(conn: psycopg2.extensions.connection, sql_path: Path) -> None:
    """Execute all statements in a single SQL file."""
    sql_content = sql_path.read_text(encoding="utf-8")
    for statement in _split_sql_statements(sql_content):
        with conn.cursor() as cur:
            cur.execute(statement)


def _connect(db_config: dict[str, str | int]) -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        dbname=db_config["database"],
    )


@pytest.mark.db_integration
def test_database_connectivity(db_config: dict[str, str | int]) -> None:
    """Test that target database can be connected."""
    conn = _connect(db_config)
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
    """Drop existing schema objects then create all tables, verify expected set.

    Two-phase approach:
    - Phase 1 (autocommit=True):  execute 00_create_schema.sql to drop old tables
      and ensure the schema exists; committed immediately so cleanup is guaranteed.
    - Phase 2 (transaction):      execute remaining DDL files (01_..99_) to create
      tables; rolled back atomically if any statement fails.
    """
    sql_files = sorted(ddl_dir.glob("*.sql"))
    init_files = [p for p in sql_files if p.name.startswith("00_")]
    ddl_files = [p for p in sql_files if not p.name.startswith("00_")]

    # Phase 1: cleanup — autocommit so DROP is committed regardless of later failures
    conn = _connect(db_config)
    try:
        conn.autocommit = True
        for sql_path in init_files:
            _execute_sql_file(conn, sql_path)
    finally:
        conn.close()

    # Phase 2: create — single transaction; rolls back to empty schema on failure
    conn = _connect(db_config)
    try:
        conn.autocommit = False
        for sql_path in ddl_files:
            _execute_sql_file(conn, sql_path)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Verify
    conn = _connect(db_config)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                (db_config["schema"],),
            )
            existing = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    missing = sorted(EXPECTED_TABLES - existing)
    assert not missing, f"missing tables in {db_config['schema']}: {', '.join(missing)}"
