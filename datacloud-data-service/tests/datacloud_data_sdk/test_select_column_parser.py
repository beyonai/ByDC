"""Tests for select_column_parser."""
from datacloud_data_sdk.sql_executor.select_column_parser import extract_select_columns


def test_extract_columns_with_as() -> None:
    sql = "SELECT id AS user_id, name AS user_name FROM users"
    assert extract_select_columns(sql) == ["user_id", "user_name"]


def test_extract_columns_without_as() -> None:
    sql = "SELECT id, name FROM users"
    assert extract_select_columns(sql) == ["id", "name"]


def test_extract_columns_mixed() -> None:
    sql = "SELECT a, b AS col_b, c FROM t"
    assert extract_select_columns(sql) == ["a", "col_b", "c"]


def test_extract_columns_empty_or_invalid() -> None:
    assert extract_select_columns("") == []
    assert extract_select_columns("UPDATE t SET x=1") == []
