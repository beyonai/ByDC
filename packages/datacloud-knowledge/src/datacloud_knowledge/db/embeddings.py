"""Backfill vector embeddings for term names."""

from __future__ import annotations

import logging

import psycopg
from psycopg import sql

from datacloud_knowledge.db.url import (
    build_postgres_connection_uri,
    resolve_knowledge_schema_for_connection,
)
from datacloud_knowledge.query.embedding import get_embedding_service

logger = logging.getLogger(__name__)


def backfill_name_embeddings(
    *,
    schema: str | None = None,
    db_url: str | None = None,
    batch_size: int = 50,
    force: bool = False,
    limit: int | None = None,
) -> dict[str, int | str]:
    """Generate embeddings for ``term_name.name_embedding``."""

    resolved_schema = resolve_knowledge_schema_for_connection(schema=schema, db_url=db_url)
    embedding_service = get_embedding_service()
    predicate: sql.Composable = sql.SQL("name_text IS NOT NULL")
    if not force:
        predicate += sql.SQL(" AND name_embedding IS NULL")

    with psycopg.connect(
        build_postgres_connection_uri(schema=resolved_schema, db_url=db_url)
    ) as conn:
        updated = 0
        try:
            while True:
                remaining = None if limit is None else max(limit - updated, 0)
                if remaining == 0:
                    break
                current_batch_size = batch_size if remaining is None else min(batch_size, remaining)
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            """
                            SELECT name_id, name_text
                            FROM {}.term_name
                            WHERE {}
                            ORDER BY name_id
                            LIMIT %s
                            """
                        ).format(sql.Identifier(resolved_schema), predicate),
                        (current_batch_size,),
                    )
                    rows = cur.fetchall()
                if not rows:
                    break

                name_ids = [row[0] for row in rows]
                texts = [row[1] for row in rows]
                vectors = embedding_service.get_text_embedding_batch(texts)
                update_params = [
                    (f"[{','.join(map(str, vector))}]", name_id)
                    for name_id, vector in zip(name_ids, vectors, strict=True)
                ]
                with conn.cursor() as cur:
                    cur.executemany(
                        sql.SQL(
                            """
                            UPDATE {}.term_name
                            SET name_embedding = %s::vector
                            WHERE name_id = %s
                            """
                        ).format(sql.Identifier(resolved_schema)),
                        update_params,
                    )
                conn.commit()
                updated += len(rows)
                logger.info("Updated %s term-name embeddings", updated)
        except Exception:
            conn.rollback()
            raise
    return {"schema": resolved_schema, "updated": updated}
