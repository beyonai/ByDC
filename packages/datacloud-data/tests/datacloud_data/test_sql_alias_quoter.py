"""tests/datacloud_data_sdk/test_sql_alias_quoter.py"""

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


def test_quote_aliases_skip_cast_in_order_by() -> None:
    """ORDER BY CAST(expr AS DECIMAL) 中的 AS DECIMAL 不应加引号。"""
    sql = """SELECT contact_no AS contactNo, contact_name AS contactName, contact_scale AS contactScale
FROM sales_person_kpi_summary
WHERE contact_scale IS NOT NULL
ORDER BY CAST(contact_scale AS DECIMAL) DESC
LIMIT 5"""
    out = quote_aliases(sql, "POSTGRESQL")
    assert 'AS "contactNo"' in out
    assert 'AS "contactName"' in out
    assert 'AS "contactScale"' in out
    assert "AS DECIMAL" in out  # 不变


def test_quote_aliases_cast_in_select_list() -> None:
    """SELECT 中 CAST(expr AS type) AS alias 仅对 alias 加引号。"""
    sql = "SELECT CAST(x AS DECIMAL) AS result FROM t"
    out = quote_aliases(sql, "POSTGRESQL")
    assert 'AS "result"' in out
    assert "AS DECIMAL" in out  # 不变


def test_quote_aliases_aggregate_function() -> None:
    """聚合函数别名加引号。"""
    sql = "SELECT COUNT(*) AS totalCount FROM t"
    out = quote_aliases(sql, "POSTGRESQL")
    assert 'AS "totalCount"' in out


def test_quote_aliases_parse_failure_returns_original() -> None:
    """解析失败时返回原 SQL。"""
    sql = "invalid sql {{{"
    out = quote_aliases(sql, "POSTGRESQL")
    assert out == sql
