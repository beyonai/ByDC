"""PostgreSQL/OpenGauss 异步连接池。"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


_IGNORED_QUERY_KEYS = frozenset({"characterEncoding", "serverTimezone", "timeZone"})
_SCHEMA_QUERY_KEYS = ("currentSchema", "schema")
_SQL_ECHO = False

def _build_database_config() -> tuple[str, dict[str, Any]]:
    raw_url = os.getenv("DATACLOUD_DB_URL", "").strip() or "jdbc:postgresql://localhost:5432/postgres"
    if raw_url.startswith("jdbc:"):
        raw_url = raw_url[5:]

    parsed = urlparse(raw_url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)

    schema: str | None = None
    filtered_query: list[tuple[str, str]] = []
    for key, value in query_pairs:
        if key in _SCHEMA_QUERY_KEYS and value and schema is None:
            schema = value
            continue
        if key in _IGNORED_QUERY_KEYS:
            continue
        filtered_query.append((key, value))

    user = os.getenv("DATACLOUD_DB_USER", "").strip() or parsed.username or "postgres"
    password = os.getenv("DATACLOUD_DB_PASSWORD", "")
    if not password and parsed.password:
        password = parsed.password

    safe_user = quote(user, safe="")
    safe_password = quote(password, safe="")
    auth = safe_user if not password else f"{safe_user}:{safe_password}"
    netloc = f"{auth}@{parsed.hostname or 'localhost'}:{parsed.port or 5432}"
    database = parsed.path.lstrip("/") or "postgres"
    database_url = urlunparse(
        (
            "postgresql+asyncpg",
            netloc,
            f"/{quote(database, safe='')}",
            "",
            urlencode(filtered_query, doseq=True),
            "",
        )
    )

    connect_args: dict[str, Any] = {}
    if schema:
        connect_args["server_settings"] = {"search_path": schema}
    return database_url, connect_args


DATABASE_URL, DATABASE_CONNECT_ARGS = _build_database_config()

engine = create_async_engine(
    DATABASE_URL,
    echo=_SQL_ECHO,
    pool_pre_ping=True,
    connect_args=DATABASE_CONNECT_ARGS,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库 session，用于 FastAPI Depends，使用后自动关闭。"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
