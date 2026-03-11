"""tests/datacloud_data_sdk/test_sql_alias_quoter.py"""
import pytest
from datacloud_data_sdk.sql_executor.sql_alias_quoter import quote_aliases


def test_quote_aliases_postgresql_double_quote() -> None:
    sql = "SELECT emp_no AS empNo, period_type AS periodType FROM t"
    out = quote_aliases(sql, "POSTGRESQL")
    assert 'AS "empNo"' in out
    assert 'AS "periodType"' in out


def test_quote_aliases_mysql_backtick() -> None:
    sql = "SELECT emp_no AS empNo FROM t"
    out = quote_aliases(sql, "MYSQL")
    assert "AS `empNo`" in out


def test_quote_aliases_skip_already_quoted() -> None:
    sql = 'SELECT col AS "empNo" FROM t'
    out = quote_aliases(sql, "POSTGRESQL")
    assert out == sql


def test_quote_aliases_unknown_db_type_no_change() -> None:
    sql = "SELECT emp_no AS empNo FROM t"
    out = quote_aliases(sql, "UNKNOWN")
    assert out == sql
