"""PostgreSQL 连接器。"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus, urlparse, urlunparse

from datacloud_data_sdk.exceptions import SqlExecutionError
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector
from datacloud_data_sdk.sql_executor.jdbc_parser import (
    parse_jdbc_url,
    extract_current_schema,
)
from datacloud_data_sdk.sql_executor.models import DataSourceConfig

_pg_dialect_opengauss_patched = False


def _patch_pg_dialect_for_opengauss() -> None:
    """Patch PGDialect 以兼容 openGauss 的 version 字符串格式。"""
    global _pg_dialect_opengauss_patched
    if _pg_dialect_opengauss_patched:
        return
    from sqlalchemy.dialects.postgresql.base import PGDialect

    _orig = PGDialect._get_server_version_info

    def _patched(connection: Any) -> tuple[int, ...]:
        try:
            return _orig(connection)
        except Exception:
            return (9, 2)

    PGDialect._get_server_version_info = _patched
    _pg_dialect_opengauss_patched = True


def _build_sqlalchemy_url(config: DataSourceConfig) -> str:
    base = parse_jdbc_url(config.jdbc_url, config.db_type)
    parsed = urlparse(base)
    if config.user:
        safe_pass = quote_plus(config.password) if config.password else ""
        safe_user = quote_plus(config.user)
        netloc = f"{safe_user}:{safe_pass}@{parsed.netloc}"
    else:
        netloc = parsed.netloc
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


class PostgreSQLConnector(BaseSourceConnector):
    """PostgreSQL 异步连接器，基于 SQLAlchemy + asyncpg。"""

    def __init__(self, config: DataSourceConfig) -> None:
        super().__init__(config)
        self._engine = None
        self._init_engine()

    def _init_engine(self) -> None:
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
        except ImportError as e:
            raise ImportError("asyncpg not installed. Install with: pip install asyncpg") from e

        if getattr(self.config, "open_gauss_compat", False):
            _patch_pg_dialect_for_opengauss()

        url = _build_sqlalchemy_url(self.config)
        pool_min = getattr(self.config, "pool_min", 1) or 1
        pool_max = getattr(self.config, "pool_max", 5) or 5
        if pool_max < pool_min:
            pool_max = pool_min
        pool_timeout = getattr(self.config, "pool_timeout", 30.0) or 30.0

        schema = extract_current_schema(self.config.jdbc_url)
        connect_args: dict[str, Any] = {}
        if schema:
            connect_args["server_settings"] = {"search_path": schema}

        self._engine = create_async_engine(
            url,
            pool_size=pool_min,
            max_overflow=max(0, pool_max - pool_min),
            pool_timeout=pool_timeout,
            connect_args=connect_args,
        )

    @classmethod
    def supported_type(cls) -> str:
        return "POSTGRESQL"

    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession

        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(text(sql), params or {})
                rows = result.fetchall()
                columns = result.keys()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            raise SqlExecutionError(self.config.alias, sql, str(e)) from e

    async def test_connection(self) -> bool:
        try:
            result = await self.execute("SELECT 1")
            return len(result) == 1
        except Exception:
            return False

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
            self._engine = None
