"""table_manager 单元测试 — 先红后绿。

测试 create_table / drop_table 的 SQLite 实现。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from datacloud_data_sdk.ddl.table_manager import create_table, drop_table


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def _set_db_env(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAL_SQLITE_PATH", str(db_path))


def _get_columns(db_path: Path, table_name: str) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor.fetchall()]
    finally:
        conn.close()


def _table_exists(db_path: Path, table_name: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


# ── create_table ───────────────────────────────────────────────────────────────


def test_create_table_creates_table(db_path: Path) -> None:
    fields: list[dict[str, Any]] = [
        {"property_code": "title", "data_type": "STRING"},
        {"property_code": "count", "data_type": "INTEGER"},
    ]
    create_table("by_test", fields, "user_001")
    assert _table_exists(db_path, "by_test")


def test_create_table_includes_id_column(db_path: Path) -> None:
    fields: list[dict[str, Any]] = [{"property_code": "title", "data_type": "STRING"}]
    create_table("by_test", fields, "user_001")
    columns = _get_columns(db_path, "by_test")
    assert "id" in columns


def test_create_table_includes_all_field_columns(db_path: Path) -> None:
    fields: list[dict[str, Any]] = [
        {"property_code": "title", "data_type": "STRING"},
        {"property_code": "handler_name", "data_type": "STRING"},
    ]
    create_table("by_test", fields, "user_001")
    columns = _get_columns(db_path, "by_test")
    assert "title" in columns
    assert "handler_name" in columns


def test_create_table_maps_data_types(db_path: Path) -> None:
    """STRING → TEXT, INTEGER → INTEGER, FLOAT → REAL, BOOLEAN → INTEGER, DATE → TEXT。"""
    fields: list[dict[str, Any]] = [
        {"property_code": "name", "data_type": "STRING"},
        {"property_code": "age", "data_type": "INTEGER"},
        {"property_code": "score", "data_type": "FLOAT"},
        {"property_code": "active", "data_type": "BOOLEAN"},
        {"property_code": "birth", "data_type": "DATE"},
    ]
    create_table("by_test", fields, "user_001")
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("PRAGMA table_info(by_test)")
        col_types = {row[1]: row[2].upper() for row in cursor.fetchall()}
    finally:
        conn.close()
    assert col_types["name"] == "TEXT"
    assert col_types["age"] == "INTEGER"
    assert col_types["score"] == "REAL"
    assert col_types["active"] == "INTEGER"
    assert col_types["birth"] == "TEXT"


def test_create_table_idempotent(db_path: Path) -> None:
    """重复调用不抛异常（IF NOT EXISTS 语义）。"""
    fields: list[dict[str, Any]] = [{"property_code": "title", "data_type": "STRING"}]
    create_table("by_test", fields, "user_001")
    create_table("by_test", fields, "user_001")  # 不应抛出


def test_create_table_empty_fields_creates_id_only(db_path: Path) -> None:
    """fields 为空时只创建 id 列。"""
    create_table("by_empty", [], "user_001")
    columns = _get_columns(db_path, "by_empty")
    assert columns == ["id"]


# ── drop_table ─────────────────────────────────────────────────────────────────


def test_drop_table_removes_table(db_path: Path) -> None:
    fields: list[dict[str, Any]] = [{"property_code": "title", "data_type": "STRING"}]
    create_table("by_test", fields, "user_001")
    drop_table("by_test")
    assert not _table_exists(db_path, "by_test")


def test_drop_table_nonexistent_does_not_raise(db_path: Path) -> None:
    """drop 不存在的表不抛异常（IF EXISTS 语义）。"""
    drop_table("nonexistent_table")  # 不应抛出


def test_drop_table_only_drops_target(db_path: Path) -> None:
    """drop 只删除目标表，不影响其他表。"""
    fields: list[dict[str, Any]] = [{"property_code": "title", "data_type": "STRING"}]
    create_table("by_test_a", fields, "user_001")
    create_table("by_test_b", fields, "user_001")
    drop_table("by_test_a")
    assert not _table_exists(db_path, "by_test_a")
    assert _table_exists(db_path, "by_test_b")
