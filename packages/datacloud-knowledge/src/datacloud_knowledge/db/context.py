"""数据库上下文：集中管理 schema 和 search_path。"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .url import resolve_knowledge_schema

logger = logging.getLogger(__name__)


class DatabaseContext:
    """集中管理 schema 上下文。

    每个事务开始时通过 SET LOCAL search_path 设置 schema，
    事务结束自动恢复，连接池安全。
    """

    def __init__(self, schema: str | None = None) -> None:
        self.schema = schema or resolve_knowledge_schema()

    def apply_search_path(self, conn: Connection) -> None:
        """在当前事务内设置 search_path。"""
        conn.execute(text(f"SET LOCAL search_path TO {self.schema}"))
        logger.debug("search_path set to: %s", self.schema)
