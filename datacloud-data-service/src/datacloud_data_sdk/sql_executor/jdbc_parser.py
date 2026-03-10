"""JDBC URL 解析。"""
from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse


def parse_jdbc_url(jdbc_url: str, db_type: str) -> str:
    """将 JDBC URL 转为 Python 连接字符串（MySQL/PostgreSQL/OpenGauss/SQLite）。"""
    if db_type.upper() == "SQLITE":
        return jdbc_url.replace("jdbc:sqlite:", "")
    if db_type.upper() == "MYSQL":
        return jdbc_url.replace("jdbc:mysql:", "mysql+aiomysql:")
    if db_type.upper() == "DORIS":
        return jdbc_url.replace("jdbc:mysql:", "mysql+aiomysql:")
    if db_type.upper() == "POSTGRESQL":
        return jdbc_url.replace("jdbc:postgresql:", "postgresql+asyncpg:")
    if db_type.upper() == "OPENGAUSS":
        if jdbc_url.startswith("jdbc:opengauss:"):
            return jdbc_url.replace("jdbc:opengauss:", "opengauss+asyncpg:")
        return jdbc_url.replace("jdbc:postgresql:", "opengauss+asyncpg:")
    return jdbc_url


def extract_current_schema(jdbc_url: str) -> str | None:
    """从 JDBC URL 的 query 中解析 currentSchema，用于设置 search_path。"""
    url = jdbc_url
    if jdbc_url.startswith("jdbc:opengauss:"):
        url = jdbc_url.replace("jdbc:opengauss:", "opengauss://", 1)
    elif jdbc_url.startswith("jdbc:postgresql:"):
        url = jdbc_url.replace("jdbc:postgresql:", "postgresql://", 1)
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    values = qs.get("currentSchema") or qs.get("current_schema")
    if not values:
        return None
    return values[0]


def parse_clickhouse_jdbc_url(jdbc_url: str) -> dict[str, str | int]:
    """解析 ClickHouse JDBC URL，返回 aioch 连接参数字典。

    jdbc:clickhouse://host:port/database?user=xxx&password=yyy
    """
    url = jdbc_url.replace("jdbc:clickhouse:", "http:")
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8123
    database = (parsed.path or "/default").lstrip("/") or "default"
    user = parsed.username or ""
    password = parsed.password or ""
    if parsed.query:
        qs = parse_qs(parsed.query)
        if "user" in qs:
            user = unquote(qs["user"][0])
        if "password" in qs:
            password = unquote(qs["password"][0])
    return {
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
    }
