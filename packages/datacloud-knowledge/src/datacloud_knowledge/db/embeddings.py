"""术语名称嵌入向量回填。

将 term_name 表中的名称文本批量转换为向量嵌入（embedding），
写入 name_embedding 列，供 pgvector 语义搜索使用。
"""

from __future__ import annotations

import logging

import psycopg
from psycopg import sql

from datacloud_knowledge.db.url import (
    build_postgres_connection_uri,
    resolve_knowledge_schema_for_connection,
)

logger = logging.getLogger(__name__)


def backfill_name_embeddings(
    *,
    schema: str | None = None,
    db_url: str | None = None,
    batch_size: int = 50,
    force: bool = False,
    limit: int | None = None,
) -> dict[str, int | str]:
    """为 term_name.name_embedding 生成嵌入向量。

    逐批读取 term_name 表中 name_text 非空的记录，调用嵌入服务生成向量，
    写回 name_embedding 列。支持断点续传（force=False 时跳过已有向量的记录）。

    Args:
        schema: 目标 schema 名称。
        db_url: 数据库连接 URL。
        batch_size: 每批处理的记录数。
        force: 是否强制重新生成所有向量（忽略已有的 name_embedding）。
        limit: 最大处理记录数（用于测试）。

    Returns:
        {"schema": str, "updated": int} 处理结果。
    """
    from datacloud_knowledge.embedding import get_embedding_service

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
                logger.info("已更新 %s 条 term_name 嵌入向量", updated)
        except Exception:
            conn.rollback()
            raise
    return {"schema": resolved_schema, "updated": updated}
