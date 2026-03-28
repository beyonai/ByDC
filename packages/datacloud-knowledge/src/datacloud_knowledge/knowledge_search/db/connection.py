from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from collections.abc import Generator


_engine: Engine | None = None
_session_local: sessionmaker[Session] | None = None


def _build_database_url() -> str:
    host = os.getenv("DB_HOST") or os.getenv("DC_DB_HOST")
    if host:
        port = os.getenv("DB_PORT") or os.getenv("DC_DB_PORT", "5432")
        user = os.getenv("DB_USER") or os.getenv("DC_DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD") or os.getenv("DC_DB_PASSWORD", "")
        database = os.getenv("DB_NAME") or os.getenv("DC_DB_NAME", "postgres")

        safe_password = quote_plus(password) if password else ""
        auth = f"{user}:{safe_password}" if safe_password else user
        return f"postgresql+psycopg://{auth}@{host}:{port}/{database}"

    url = os.getenv("DATABASE_URL", "postgresql+psycopg://localhost:5432/postgres")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _patch_pgdialect_opengauss() -> None:
    """OpenGauss 模拟 PostgreSQL 15 版本"""
    PGDialect._get_server_version_info = lambda _self, _conn: (15, 0)  # type: ignore[method-assign]


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        db_type = os.getenv("KNOWLEDGE_DB_TYPE") or os.getenv("DC_KNOWLEDGE_DB_TYPE") or ""
        if db_type.lower() == "opengauss":
            _patch_pgdialect_opengauss()

        database_url = _build_database_url()
        _engine = create_engine(
            database_url,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            pool_pre_ping=True,
        )
    return _engine


def _get_session_local() -> sessionmaker[Session]:
    global _session_local
    if _session_local is None:
        _session_local = sessionmaker(
            bind=_get_engine(),
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_local


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = _get_session_local()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
