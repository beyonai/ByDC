"""SQL 别名自动加引号，使 PostgreSQL/OpenGauss/MySQL 等保留 camelCase。"""
from __future__ import annotations

import re

_DOUBLE_QUOTE_DBS = {"POSTGRESQL", "OPENGAUSS", "SQLITE"}
_BACKTICK_DBS = {"MYSQL", "CLICKHOUSE"}


def quote_aliases(sql: str, db_type: str) -> str:
    """对 SQL 中未加引号的 AS 别名加引号，按 db_type 选择双引号或反引号。"""
    if db_type.upper() in _DOUBLE_QUOTE_DBS:
        quote_char = '"'
    elif db_type.upper() in _BACKTICK_DBS:
        quote_char = "`"
    else:
        return sql

    pattern = r"\bAS\s+([a-zA-Z_][a-zA-Z0-9_]*)"

    def repl(m: re.Match[str]) -> str:
        return f"AS {quote_char}{m.group(1)}{quote_char}"

    return re.sub(pattern, repl, sql)
