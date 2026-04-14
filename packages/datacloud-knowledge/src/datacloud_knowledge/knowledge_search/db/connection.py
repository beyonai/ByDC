from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.orm import Session, sessionmaker

from datacloud_knowledge.db_url import build_sqlalchemy_database_config, infer_database_type_from_url

if TYPE_CHECKING:
    from collections.abc import Generator


_engine: Engine | None = None
_session_local: sessionmaker[Session] | None = None
_SQL_ECHO = False


def _patch_pgdialect_opengauss() -> None:
    """OpenGauss 模拟 PostgreSQL 15 版本"""
    PGDialect._get_server_version_info = lambda _self, _conn: (15, 0)  # type: ignore[method-assign]


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        db_type = infer_database_type_from_url()
        if db_type.lower() == "opengauss":
            _patch_pgdialect_opengauss()

        database_url, connect_args = build_sqlalchemy_database_config("psycopg")
        _engine = create_engine(
            database_url,
            echo=_SQL_ECHO,
            pool_pre_ping=True,
            connect_args=connect_args,
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
