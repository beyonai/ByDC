"""Integration tests for whale_datacloud schema DDL."""

from __future__ import annotations

from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2")  # type: ignore

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
    """Split SQL on ';' outside string literals.

    Handles:
    - Single-quoted strings with '' escapes
    - PostgreSQL dollar-quoted strings ($$ ... $$, $tag$ ... $tag$), e.g. DO $$ ... $$ blocks
      where semicolons appear inside the PL/pgSQL body.
    """
    statements: list[str] = []
    buf: list[str] = []
    in_single_quote = False
    dollar_close: str | None = None  # when set, copy until this delimiter closes
    n = len(sql_content)
    i = 0
    while i < n:
        if dollar_close is not None:
            if sql_content.startswith(dollar_close, i):
                buf.append(dollar_close)
                i += len(dollar_close)
                dollar_close = None
                continue
            buf.append(sql_content[i])
            i += 1
            continue

        ch = sql_content[i]
        if in_single_quote:
            if ch == "'" and i + 1 < n and sql_content[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            if ch == "'":
                in_single_quote = False
            buf.append(ch)
            i += 1
            continue

        if ch == "'":
            in_single_quote = True
            buf.append(ch)
            i += 1
            continue

        if ch == "$":
            # Opening dollar quote: $ + optional tag (letters/digits/_) + $
            j = i + 1
            while j < n and sql_content[j] != "$":
                c = sql_content[j]
                if not (c.isalnum() or c == "_"):
                    break
                j += 1
            if j < n and sql_content[j] == "$":
                delim = sql_content[i : j + 1]
                buf.append(delim)
                i = j + 1
                dollar_close = delim
                continue
            buf.append(ch)
            i += 1
            continue

        if ch == ";":
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


def test_split_sql_statements_keeps_do_dollar_block_intact() -> None:
    """Semicolons inside DO $$ ... $$ must not split statements (see 97_add_code_columns.sql)."""
    sql = """DO $$
BEGIN
    IF TRUE THEN
        SELECT 1;
    END IF;
END $$;
SELECT 2;
"""
    parts = _split_sql_statements(sql)
    assert len(parts) == 2
    assert parts[0].strip().startswith("DO $$")
    assert parts[0].strip().endswith("END $$")
    assert "SELECT 1;" in parts[0]
    assert parts[1].strip() == "SELECT 2"


def test_split_sql_statements_dollar_tag() -> None:
    sql = "$a$foo;bar$a$;SELECT 1;"
    parts = _split_sql_statements(sql)
    assert len(parts) == 2
    assert parts[0] == "$a$foo;bar$a$"
    assert parts[1].strip() == "SELECT 1"
