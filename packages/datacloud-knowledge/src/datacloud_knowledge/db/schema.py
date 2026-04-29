"""Schema lifecycle utilities for the knowledge database."""

from __future__ import annotations

import logging

import psycopg
from psycopg import sql

from datacloud_knowledge.db.resources import sql_texts
from datacloud_knowledge.db.url import (
    build_postgres_connection_uri,
    resolve_knowledge_schema_for_connection,
)

logger = logging.getLogger(__name__)

CORE_TABLES = (
    "domain",
    "term_library",
    "term_type",
    "term",
    "term_relation",
    "term_name",
    "term_vocabulary",
    "term_knowledge",
)


def _connect(
    *,
    schema: str,
    db_url: str | None = None,
    autocommit: bool = False,
) -> psycopg.Connection[tuple]:
    return psycopg.connect(
        build_postgres_connection_uri(schema=schema, db_url=db_url),
        autocommit=autocommit,
    )


def _set_search_path(cur: psycopg.Cursor[tuple], schema: str) -> None:
    cur.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))


def create_schema(*, schema: str | None = None, db_url: str | None = None) -> str:
    """Create the target schema if it does not exist and return its resolved name."""

    resolved_schema = resolve_knowledge_schema_for_connection(schema=schema, db_url=db_url)
    with (
        _connect(schema=resolved_schema, db_url=db_url, autocommit=True) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(resolved_schema))
        )
    return resolved_schema


def _apply_sql_group(
    kind: str,
    *,
    schema: str,
    db_url: str | None = None,
    skip_destructive: bool = True,
) -> int:
    files = sql_texts(kind)
    if skip_destructive:
        files = [(name, text) for name, text in files if not name.startswith("00_")]
    if not files:
        logger.info("No %s SQL files found", kind)
        return 0

    with _connect(schema=schema, db_url=db_url) as conn:
        try:
            with conn.cursor() as cur:
                _set_search_path(cur, schema)
                for name, text in files:
                    logger.info("Executing %s/%s", kind, name)
                    cur.execute(text.encode())
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return len(files)


def _apply_destructive_ddl(*, schema: str, db_url: str | None = None) -> int:
    files = sql_texts("ddl")
    if not files:
        raise ValueError("No DDL SQL files found")

    schema_file, *rest_files = files
    with _connect(schema=schema, db_url=db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        _set_search_path(cur, schema)
        logger.warning("Executing destructive DDL %s", schema_file[0])
        cur.execute(schema_file[1].encode())

    if rest_files:
        with _connect(schema=schema, db_url=db_url) as conn:
            try:
                with conn.cursor() as cur:
                    _set_search_path(cur, schema)
                    for name, text in rest_files:
                        logger.info("Executing ddl/%s", name)
                        cur.execute(text.encode())
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    return len(files)


def ensure_schema(
    *,
    schema: str | None = None,
    db_url: str | None = None,
    reset: bool = False,
    seed: bool = True,
    create_vector_extension: bool = False,
) -> dict[str, int | str]:
    """Ensure the knowledge schema exists and has the expected tables.

    ``reset=True`` executes the destructive ``00_`` DDL file. The default path
    skips destructive SQL and only applies idempotent DDL, migrations, and seed.
    """

    resolved_schema = create_schema(schema=schema, db_url=db_url)
    if create_vector_extension:
        with (
            _connect(schema=resolved_schema, db_url=db_url, autocommit=True) as conn,
            conn.cursor() as cur,
        ):
            cur.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS vector"))

    ddl_count = (
        _apply_destructive_ddl(schema=resolved_schema, db_url=db_url)
        if reset
        else _apply_sql_group("ddl", schema=resolved_schema, db_url=db_url, skip_destructive=True)
    )
    migration_count = _apply_sql_group(
        "migrations", schema=resolved_schema, db_url=db_url, skip_destructive=False
    )
    seed_count = (
        _apply_sql_group("seed", schema=resolved_schema, db_url=db_url, skip_destructive=False)
        if seed
        else 0
    )
    return {
        "schema": resolved_schema,
        "ddl_files": ddl_count,
        "migration_files": migration_count,
        "seed_files": seed_count,
    }


def verify_schema(
    *,
    schema: str | None = None,
    db_url: str | None = None,
) -> dict[str, int | str | list[str]]:
    """Verify that all core knowledge tables exist in the target schema."""

    resolved_schema = resolve_knowledge_schema_for_connection(schema=schema, db_url=db_url)
    with _connect(schema=resolved_schema, db_url=db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name = ANY(%s)
                """,
            (resolved_schema, list(CORE_TABLES)),
        )
        existing = {row[0] for row in cur.fetchall()}
    missing = [table for table in CORE_TABLES if table not in existing]
    return {
        "schema": resolved_schema,
        "existing_count": len(existing),
        "expected_count": len(CORE_TABLES),
        "missing": missing,
    }
