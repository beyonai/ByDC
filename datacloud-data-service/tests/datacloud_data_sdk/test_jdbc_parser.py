"""JDBC URL 解析测试。"""

from datacloud_data_sdk.sql_executor.jdbc_parser import (
    parse_jdbc_url,
    parse_clickhouse_jdbc_url,
    extract_current_schema,
)


def test_parse_sqlite_url():
    assert parse_jdbc_url("jdbc:sqlite::memory:", "SQLITE") == ":memory:"
    assert parse_jdbc_url("jdbc:sqlite:/tmp/db.sqlite", "SQLITE") == "/tmp/db.sqlite"


def test_parse_mysql_url():
    url = parse_jdbc_url("jdbc:mysql://localhost:3306/crm", "MYSQL")
    assert url == "mysql+aiomysql://localhost:3306/crm"


def test_parse_doris_url():
    url = parse_jdbc_url("jdbc:mysql://doris:9030/db", "DORIS")
    assert url == "mysql+aiomysql://doris:9030/db"


def test_parse_postgresql_url():
    url = parse_jdbc_url("jdbc:postgresql://localhost:5432/analytics", "POSTGRESQL")
    assert url == "postgresql+asyncpg://localhost:5432/analytics"


def test_parse_opengauss_url():
    url = parse_jdbc_url("jdbc:opengauss://host:5432/db", "OPENGAUSS")
    assert url == "opengauss+asyncpg://host:5432/db"
    url2 = parse_jdbc_url("jdbc:postgresql://host:5432/db", "OPENGAUSS")
    assert url2 == "opengauss+asyncpg://host:5432/db"


def test_extract_current_schema():
    jdbc = "jdbc:opengauss://host:5432/db?currentSchema=crm_demo"
    assert extract_current_schema(jdbc) == "crm_demo"
    jdbc2 = "jdbc:postgresql://host:5432/db?currentSchema=crm_demo"
    assert extract_current_schema(jdbc2) == "crm_demo"
    jdbc3 = "jdbc:postgresql://host:5432/db"
    assert extract_current_schema(jdbc3) is None


def test_parse_clickhouse_jdbc_url():
    params = parse_clickhouse_jdbc_url("jdbc:clickhouse://ch-host:8123/analytics")
    assert params["host"] == "ch-host"
    assert params["port"] == 8123
    assert params["database"] == "analytics"
    assert params["user"] == ""
    assert params["password"] == ""


def test_parse_clickhouse_jdbc_url_with_auth():
    params = parse_clickhouse_jdbc_url("jdbc:clickhouse://ch:8123/db?user=readonly&password=secret")
    assert params["host"] == "ch"
    assert params["port"] == 8123
    assert params["database"] == "db"
    assert params["user"] == "readonly"
    assert params["password"] == "secret"
