from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.orm import Session, sessionmaker

from .url import build_sqlalchemy_database_config, infer_database_type_from_url

if TYPE_CHECKING:
    from collections.abc import Generator


_engines: dict[str, Engine] = {}
_session_locals: dict[str, sessionmaker[Session]] = {}
_SQL_ECHO = False


def _patch_pgdialect_opengauss() -> None:
    """OpenGauss 模拟 PostgreSQL 15 版本"""
    PGDialect._get_server_version_info = lambda _self, _conn: (15, 0)  # type: ignore[method-assign]


def _get_engine(schema: str | None = None) -> Engine:
    database_url, connect_args = build_sqlalchemy_database_config("psycopg", schema=schema)
    engine_key = f"{database_url}|{connect_args.get('options', '')}"
    if engine_key not in _engines:
        db_type = infer_database_type_from_url()
        if db_type.lower() == "opengauss":
            _patch_pgdialect_opengauss()

        _engines[engine_key] = create_engine(
            database_url,
            echo=_SQL_ECHO,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engines[engine_key]


def _get_session_local(schema: str | None = None) -> sessionmaker[Session]:
    database_url, connect_args = build_sqlalchemy_database_config("psycopg", schema=schema)
    session_key = f"{database_url}|{connect_args.get('options', '')}"
    if session_key not in _session_locals:
        _session_locals[session_key] = sessionmaker(
            bind=_get_engine(schema),
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_locals[session_key]


@contextmanager
def get_session(schema: str | None = None) -> Generator[Session, None, None]:
    session = _get_session_local(schema)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
