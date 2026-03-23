from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.orm import Session, sessionmaker


def _build_database_url() -> str:
    host = os.getenv("DB_HOST")
    if host:
        port = os.getenv("DB_PORT", "5432")
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        database = os.getenv("DB_NAME", "postgres")

        safe_password = quote_plus(password) if password else ""
        auth = f"{user}:{safe_password}" if safe_password else user
        return f"postgresql+psycopg2://{auth}@{host}:{port}/{database}"

    url = os.getenv("DATABASE_URL", "postgresql+psycopg2://localhost:5432/postgres")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


DATABASE_URL = _build_database_url()

if os.getenv("KNOWLEDGE_DB_TYPE", "").lower() == "opengauss":
    PGDialect._get_server_version_info = lambda self, conn: (15, 0)

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

