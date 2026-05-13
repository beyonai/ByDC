"""批量导入适配器 — 封装 psycopg 连接和批量写入操作。

导入器（ingestion/owl_import/importer/executor.py）通过此类访问数据库，
不再直接导入 psycopg。psycopg 完全由 adapter 内部管理。
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg import Connection, sql

from datacloud_knowledge.adapters.opengauss._db.context import DatabaseContext
from datacloud_knowledge.adapters.opengauss._db.url import build_postgres_connection_uri

from ..ingestion.owl_import.importer._helpers import (
    _execute_values,
    _import_batch_size,
    _iter_jsonl_obj_batches,
    _normalize_term_code,
    _str_id_if_set,
    _term_id_from_obj_or_code_direct,
)

logger = logging.getLogger(__name__)


class BulkImportAdapter:
    """批量导入适配器 — 封装连接管理和实体批量写入。

    导入流程：
    1. 构造实例 → 建立 psycopg 连接
    2. ``begin_import()`` → 设置 search_path，删除 scoped 数据
    3. ``batch_process_*()`` → 逐实体批量写入
    4. ``commit()`` / ``rollback()`` → 事务控制
    5. ``close()`` → 释放连接

    Example::

        adapter = BulkImportAdapter(schema="whale_datacloud", db_url="...")
        try:
            adapter.begin_import(
                scopes=[{"scope": "view", "code": "sales"}],
                root_term_ids=["lib1#view#sales"],
            )
            adapter.batch_process_term_type(term_types, stats)
            adapter.batch_process_term(terms, stats)
            adapter.commit()
        except Exception:
            adapter.rollback()
            raise
        finally:
            adapter.close()
    """

    def __init__(
        self,
        *,
        schema: str | None = None,
        db_url: str | None = None,
        conninfo: str | None = None,
    ) -> None:
        db_ctx = DatabaseContext(schema=schema)
        self._schema = db_ctx.schema
        self._conn = self._connect(
            conninfo=conninfo
            or build_postgres_connection_uri(schema=self._schema, db_url=db_url),
        )
        self._conn.autocommit = False

    @staticmethod
    def _connect(conninfo: str) -> Connection:
        import os

        ct_raw = os.getenv("DATACLOUD_DB_CONNECT_TIMEOUT", "30").strip()
        connect_timeout = int(ct_raw) if ct_raw.isdigit() else 30
        app_name = "datacloud_knowledge_import"

        _kw: dict[str, Any] = {
            "conninfo": conninfo,
            "connect_timeout": connect_timeout,
        }
        try:
            return psycopg.connect(**_kw, application_name=app_name)
        except TypeError:
            return psycopg.connect(**_kw)

    # ── 事务控制 ──────────────────────────────────────────────────────────

    def begin_import(
        self,
        *,
        scopes: list[dict[str, str]],
        root_term_ids: list[str],
    ) -> None:
        """设置 search_path，删除 scoped 数据（在事务内执行）。"""
        with self._conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET LOCAL search_path TO {}").format(
                    sql.Identifier(self._schema)
                )
            )
            self._delete_scoped_term_names(cur, scopes)
            self._delete_scope_terms(cur, root_term_ids)

    def commit(self) -> None:
        self._conn.commit()
        logger.info("import committed")

    def rollback(self) -> None:
        self._conn.rollback()
        logger.warning("import rolled back")

    def close(self) -> None:
        self._conn.close()

    def cursor(self) -> Any:
        """获取 psycopg cursor（上下文管理器），供批量写入使用。"""
        return self._conn.cursor()

    # ── Scoped 删除 ──────────────────────────────────────────────────────

    @staticmethod
    def _delete_scope_terms(cur: Any, root_term_ids: list[str]) -> None:
        if not root_term_ids:
            return
        for table in ("term_knowledge", "term_relation", "term_name", "term"):
            target_col = "term_id"
            if table == "term_relation":
                cur.execute(
                    f"""
                    WITH RECURSIVE scope_terms AS (
                        SELECT term_id FROM term WHERE term_id = ANY(%s)
                        UNION
                        SELECT t.term_id FROM term t
                        JOIN scope_terms s ON t.parent_term_id = s.term_id
                    )
                    DELETE FROM {table}
                    WHERE source_term_id IN (SELECT term_id FROM scope_terms)
                       OR target_term_id IN (SELECT term_id FROM scope_terms)
                    """,
                    (root_term_ids,),
                )
            else:
                cur.execute(
                    f"""
                    WITH RECURSIVE scope_terms AS (
                        SELECT term_id FROM term WHERE term_id = ANY(%s)
                        UNION
                        SELECT t.term_id FROM term t
                        JOIN scope_terms s ON t.parent_term_id = s.term_id
                    )
                    DELETE FROM {table}
                    WHERE {target_col} IN (SELECT term_id FROM scope_terms)
                    """,
                    (root_term_ids,),
                )

    @staticmethod
    def _delete_scoped_term_names(cur: Any, scopes: list[dict[str, str]]) -> None:
        import json

        for scope in scopes:
            cur.execute(
                "DELETE FROM term_name WHERE search_scope @> %s::jsonb",
                (json.dumps(scope, ensure_ascii=False),),
            )

    # ── 实体批量写入（委托底层 writer 函数）─────────────────────────────

    def batch_process_domain(
        self, items: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.ingestion.owl_import.importer.writer._domain import (
            _batch_process_domain,
        )

        with self._conn.cursor() as cur:
            _batch_process_domain(cur, items, stats)

    def batch_process_library(
        self, items: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.ingestion.owl_import.importer.writer._library import (
            _batch_process_library,
        )

        with self._conn.cursor() as cur:
            _batch_process_library(cur, items, stats)

    def batch_process_term_type(
        self, items: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.ingestion.owl_import.importer.writer._term_type import (
            _batch_process_term_type,
        )

        with self._conn.cursor() as cur:
            _batch_process_term_type(cur, items, stats)

    def batch_process_term(
        self, items: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.ingestion.owl_import.importer.writer._term import (
            _batch_process_term,
        )

        with self._conn.cursor() as cur:
            _batch_process_term(cur, items, stats)

    def batch_process_relation(
        self, items: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.ingestion.owl_import.importer.writer._relation import (
            _batch_process_relation,
        )

        with self._conn.cursor() as cur:
            _batch_process_relation(cur, items, stats)

    def batch_process_knowledge(
        self, items: list[dict[str, Any]], stats: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.ingestion.owl_import.importer.writer._knowledge import (
            _batch_process_knowledge,
        )

        with self._conn.cursor() as cur:
            _batch_process_knowledge(cur, items, stats)
