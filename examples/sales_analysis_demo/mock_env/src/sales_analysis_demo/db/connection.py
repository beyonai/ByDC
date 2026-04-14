"""PostgreSQL/OpenGauss 异步连接池。"""

import os
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# OpenGauss 版本兼容补丁在 main.py 中于应用启动时执行

_IGNORED_QUERY_KEYS = frozenset({"characterEncoding", "serverTimezone", "timeZone"})
_SCHEMA_QUERY_KEYS = ("currentSchema", "schema")
_SQL_ECHO = False

def _parse_database_config() -> tuple[str, dict[str, Any], str]:
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
    query = urlencode(filtered_query, doseq=True)

    async_url = urlunparse(
        (
            "postgresql+asyncpg",
            netloc,
            f"/{quote(database, safe='')}",
            "",
            query,
            "",
        )
    )
    psycopg_dsn = urlunparse(
        (
            "postgresql",
            netloc,
            f"/{quote(database, safe='')}",
            "",
            query,
            "",
        )
    )

    connect_args: dict[str, Any] = {}
    if schema:
        connect_args["server_settings"] = {"search_path": schema}
        psycopg_dsn = urlunparse(
            (
                "postgresql",
                netloc,
                f"/{quote(database, safe='')}",
                "",
                urlencode([*filtered_query, ("options", f"-csearch_path={schema}")], doseq=True),
                "",
            )
        )
    return async_url, connect_args, psycopg_dsn


def build_psycopg_connection_dsn() -> str:
    """Return a libpq-compatible DSN for psycopg2/psycopg callers."""

    _, _, psycopg_dsn = _parse_database_config()
    return psycopg_dsn


DATABASE_URL, DATABASE_CONNECT_ARGS, _PSYCOPG_DSN = _parse_database_config()

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
    """获取异步数据库 session，用于 FastAPI Depends，使用后自动关闭."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
