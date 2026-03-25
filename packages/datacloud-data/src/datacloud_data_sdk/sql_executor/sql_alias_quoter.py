"""SQL 别名自动加引号，使 PostgreSQL/OpenGauss/MySQL 等保留 camelCase。"""
from __future__ import annotations

_DOUBLE_QUOTE_DBS = {"POSTGRESQL", "OPENGAUSS", "SQLITE"}
_BACKTICK_DBS = {"MYSQL", "CLICKHOUSE"}


def quote_aliases(sql: str, db_type: str) -> str:
    """仅对最外层 SELECT 列表中的 AS 别名加引号。ORDER BY 等子句中的 AS 不处理。"""
    if db_type.upper() in _DOUBLE_QUOTE_DBS:
        quote_char = '"'
    elif db_type.upper() in _BACKTICK_DBS:
        quote_char = "`"
    else:
        return sql

    try:
        return _quote_select_aliases(sql, quote_char)
    except Exception:
        return sql


def _quote_select_aliases(sql: str, quote_char: str) -> str:
    import sqlparse
    from sqlparse import sql as sql_ast
    from sqlparse import tokens as T

    parsed = sqlparse.parse(sql)
    if not parsed:
        return sql

    stmt = parsed[0]
    if not hasattr(stmt, "tokens") or not stmt.tokens:
        return sql

    parts: list[str] = []
    in_select = False
    select_done = False

    for token in stmt.tokens:
        tok_val = getattr(token, "value", "")
        is_select = token.ttype == T.DML and tok_val.upper() == "SELECT"
        is_from = (
            token.ttype is not None
            and "Keyword" in str(token.ttype)
            and tok_val.upper() == "FROM"
        )

        if is_select:
            in_select = True
            parts.append(token.value)
            continue
        if in_select and is_from:
            in_select = False
            select_done = True
            parts.append(token.value)
            continue

        if in_select and not select_done:
            _emit_select_token(token, quote_char, parts)
        else:
            parts.append(token.value)

    return "".join(parts)


def _emit_select_token(token: object, quote_char: str, parts: list[str]) -> None:
    """输出 SELECT 列表中的 token，对未加引号的别名加引号。"""
    from sqlparse import sql as sql_ast

    if isinstance(token, sql_ast.IdentifierList):
        for t in token.tokens:
            if isinstance(t, (sql_ast.Identifier, sql_ast.Function)):
                _emit_select_token(t, quote_char, parts)
            else:
                parts.append(getattr(t, "value", str(t)))
        return

    if hasattr(token, "tokens") and token.tokens:
        if hasattr(token, "get_alias") and token.get_alias():
            alias = token.get_alias()
            if alias and not _is_quoted(alias, token):
                _emit_with_quoted_alias(token, alias, quote_char, parts)
                return
        for t in token.tokens:
            _emit_select_token(t, quote_char, parts)
    else:
        parts.append(getattr(token, "value", str(token)))


def _is_quoted(alias: str, token: object) -> bool:
    """检查别名在原始 token 中是否已加引号。"""
    val = getattr(token, "value", "") or str(token)
    for q in ('"', "'", "`"):
        if f"AS {q}{alias}{q}" in val or f"AS {q}{alias}" in val:
            return True
    return False


def _emit_with_quoted_alias(
    token: object, alias: str, quote_char: str, parts: list[str]
) -> None:
    """遍历 token 直接子节点，对 AS 后的标识符加引号。"""
    tokens = getattr(token, "tokens", [])
    if not tokens:
        parts.append(getattr(token, "value", str(token)))
        return
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if getattr(t, "value", "").upper() == "AS" and getattr(t, "is_keyword", False):
            parts.append(t.value)
            i += 1
            while i < len(tokens) and getattr(tokens[i], "is_whitespace", False):
                parts.append(tokens[i].value)
                i += 1
            if i < len(tokens):
                parts.append(quote_char + alias + quote_char)
                i += 1
            continue
        if hasattr(t, "tokens") and t.tokens:
            _emit_token_recursive(t, parts)
        else:
            parts.append(getattr(t, "value", str(t)))
        i += 1


def _emit_token_recursive(token: object, parts: list[str]) -> None:
    """递归输出 token，不加引号。"""
    if hasattr(token, "tokens") and token.tokens:
        for t in token.tokens:
            _emit_token_recursive(t, parts)
    else:
        parts.append(getattr(token, "value", str(token)))
