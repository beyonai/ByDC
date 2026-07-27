"""Execute a single SQL statement against an existing SQLite database."""

from __future__ import annotations

import base64
import sqlite3
from pathlib import Path
from typing import Any, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"]
SqliteExecutionResult: TypeAlias = dict[str, JsonValue]


class SqliteExecutionError(ValueError):
    """Raised when a SQLite path or SQL statement cannot be executed."""


def _json_value(value: Any) -> JsonValue:
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise SqliteExecutionError(
        f"SQLite returned an unsupported value type: {type(value).__name__}"
    )


def execute_sqlite_statement(
    sql: str,
    sqlite_path: Path,
) -> SqliteExecutionResult:
    """Execute one SQL statement and return JSON-compatible cursor data."""
    if not sql.strip():
        raise SqliteExecutionError("SQL must not be empty")
    if not sqlite_path.is_file():
        raise SqliteExecutionError(f"SQLite file does not exist: {sqlite_path}")

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(sqlite_path)
        cursor = connection.execute(sql)
        description: JsonValue = (
            [[_json_value(value) for value in column] for column in cursor.description]
            if cursor.description is not None
            else None
        )
        rows: JsonValue = (
            [[_json_value(value) for value in row] for row in cursor.fetchall()]
            if cursor.description is not None
            else []
        )
        result: SqliteExecutionResult = {
            "description": description,
            "rows": rows,
            "rowcount": cursor.rowcount,
            "lastrowid": cursor.lastrowid,
        }
        cursor.close()
        connection.commit()
        return result
    except sqlite3.Error as error:
        if connection is not None:
            connection.rollback()
        raise SqliteExecutionError(str(error)) from error
    finally:
        if connection is not None:
            connection.close()
