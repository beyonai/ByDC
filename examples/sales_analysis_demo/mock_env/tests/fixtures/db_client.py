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
    normalized_lines: list[str] = []
    for line in sql_content.splitlines():
        if "--" in line:
            line = line.split("--", 1)[0]
        normalized_lines.append(line)
    normalized_sql = "\n".join(normalized_lines)

    statements: list[str] = []
    buf: list[str] = []
    in_single_quote = False
    i = 0
    while i < len(normalized_sql):
        ch = normalized_sql[i]
        if ch == "'":
            # Handle escaped quote in SQL string literal: ''
            if in_single_quote and i + 1 < len(normalized_sql) and normalized_sql[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_single_quote = not in_single_quote
            buf.append(ch)
            i += 1
            continue

        if ch == ";" and not in_single_quote:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
