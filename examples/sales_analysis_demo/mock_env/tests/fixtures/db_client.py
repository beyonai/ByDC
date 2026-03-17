"""Database helper utilities for integration tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def create_test_engine(database_dsn: str) -> Engine:
    return create_engine(database_dsn, future=True)


@contextmanager
def db_connection(engine: Engine) -> Iterator[object]:
    with engine.connect() as conn:
        yield conn


def execute_sql_script(engine: Engine, sql_content: str) -> None:
    statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
