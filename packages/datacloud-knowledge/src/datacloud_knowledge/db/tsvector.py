"""Backfill text-search vectors for term names."""

from __future__ import annotations

import psycopg
from psycopg import sql

from datacloud_knowledge.db.url import (
    build_postgres_connection_uri,
    resolve_knowledge_schema_for_connection,
)


def backfill_tsvector(*, schema: str | None = None, force: bool = False) -> dict[str, int | str]:
    """Fill ``term_name.name_keywords`` using PostgreSQL ``to_tsvector``."""

    return backfill_tsvector_with_url(schema=schema, force=force)


def backfill_tsvector_with_url(
    *,
    schema: str | None = None,
    db_url: str | None = None,
    force: bool = False,
) -> dict[str, int | str]:
    """Fill ``term_name.name_keywords`` with optional explicit DB URL."""

    resolved_schema = resolve_knowledge_schema_for_connection(schema=schema, db_url=db_url)
    query = sql.SQL(
        """
        UPDATE {}.term_name
        SET name_keywords = to_tsvector(
            'simple',
            array_to_string(string_to_array(COALESCE(name_text, ''), NULL), ' ')
        )
        WHERE name_text IS NOT NULL
        """
    ).format(sql.Identifier(resolved_schema))
    if not force:
        query += sql.SQL(" AND name_keywords IS NULL")

    with (
        psycopg.connect(
            build_postgres_connection_uri(schema=resolved_schema, db_url=db_url), autocommit=True
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(query)
        updated = cur.rowcount
    return {"schema": resolved_schema, "updated": updated}
