"""从 SQL SELECT 子句解析列名（含 AS 别名）。"""
from __future__ import annotations

import re


def extract_select_columns(sql: str) -> list[str]:
    """从 SELECT 语句解析列名。优先 AS 别名，无 AS 时取列名。解析失败返回 []。"""
    if not sql or not sql.strip():
        return []
    try:
        return _extract_with_sqlparse(sql)
    except ImportError:
        return _extract_with_regex(sql)
    except Exception:
        return []


def _extract_with_sqlparse(sql: str) -> list[str]:
    import sqlparse
    from sqlparse.sql import Identifier, IdentifierList, Token

    parsed = sqlparse.parse(sql)
    if not parsed:
        return []
    stmt = parsed[0]
    columns: list[str] = []
    in_select = False
    select_tokens: list[Token] = []

    for token in stmt.tokens:
        if getattr(token.ttype, "name", "") == "DML" and token.value.upper() == "SELECT":
            in_select = True
            continue
        if in_select:
            if token.ttype and "Keyword" in str(token.ttype) and token.value.upper() == "FROM":
                break
            if not (token.is_whitespace or (token.ttype and "Punctuation" in str(token.ttype))):
                select_tokens.append(token)

    for token in select_tokens:
        if isinstance(token, IdentifierList):
            for ident in token.get_identifiers():
                name = _get_ident_name(ident)
                if name:
                    columns.append(name)
        elif isinstance(token, Identifier):
            name = _get_ident_name(token)
            if name:
                columns.append(name)
        elif hasattr(token, "tokens"):
            for t in token.tokens:
                if isinstance(t, Identifier):
                    name = _get_ident_name(t)
                    if name:
                        columns.append(name)
                elif isinstance(t, IdentifierList):
                    for ident in t.get_identifiers():
                        name = _get_ident_name(ident)
                        if name:
                            columns.append(name)
    return columns


def _get_ident_name(ident: object) -> str | None:
    try:
        name = ident.get_name()  # type: ignore[union-attr]
        return name.strip('"\'') if name else None
    except Exception:
        return None


def _extract_with_regex(sql: str) -> list[str]:
    """正则回退：匹配 SELECT ... FROM。"""
    m = re.search(r"\bSELECT\s+(.+?)\s+FROM\s", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    select_part = m.group(1)
    columns: list[str] = []
    for part in re.split(r"\s*,\s*", select_part):
        part = part.strip()
        as_match = re.search(r"\bAS\s+([^\s,]+)\s*$", part, re.IGNORECASE)
        if as_match:
            columns.append(as_match.group(1).strip('"\''))
        else:
            last = part.split()[-1].split(".")[-1].strip('"\'')
            if last and last.upper() not in ("AS", "DISTINCT", "ALL"):
                columns.append(last)
    return columns
