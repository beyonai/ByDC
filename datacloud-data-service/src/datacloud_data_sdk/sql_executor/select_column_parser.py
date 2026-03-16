"""从 SQL SELECT 子句解析列名（含 AS 别名）。"""
from __future__ import annotations

import re


def extract_select_columns(sql: str) -> list[str]:
    """从 SELECT 语句解析最外层返回列名。优先 AS 别名，无 AS 时取列名。解析失败返回 []。"""
    if not sql or not sql.strip():
        return []
    try:
        result = _extract_with_sqlparse(sql)
        if result and _sqlparse_result_complete(sql, result):
            return result
    except ImportError:
        pass
    except Exception:
        pass
    return _extract_with_regex(sql)


def _extract_with_sqlparse(sql: str) -> list[str]:
    """用 sqlparse 解析，只取最外层 SELECT 的返回列（stmt 为顶层语句，SELECT/FROM 为顶层关键字）。"""
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
        if token.value.upper() == "SELECT":
            in_select = True
            continue
        if in_select:
            if token.value.upper() == "FROM":
                break
            if not (token.is_whitespace or (token.ttype and "Punctuation" in str(token.ttype))):
                select_tokens.append(token)

    for token in select_tokens:
        if isinstance(token, IdentifierList):
            for ident in token.get_identifiers():
                name = _get_ident_name(ident)
                if name and _should_append_column(columns, name):
                    columns.append(name)
        elif isinstance(token, Identifier):
            name = _get_ident_name(token)
            if name and _should_append_column(columns, name):
                columns.append(name)
        elif hasattr(token, "tokens"):
            for t in token.tokens:
                if isinstance(t, Identifier):
                    name = _get_ident_name(t)
                    if name and _should_append_column(columns, name):
                        columns.append(name)
                elif isinstance(t, IdentifierList):
                    for ident in t.get_identifiers():
                        name = _get_ident_name(ident)
                        if name and _should_append_column(columns, name):
                            columns.append(name)
    return columns


def _should_append_column(columns: list[str], name: str) -> bool:
    """sqlparse 对 type 等关键字会错误拆成多个 IdentifierList，导致重复。跳过连续重复。"""
    if not columns:
        return True
    if columns[-1] == name and name.upper() in ("TYPE",):  # 已知 sqlparse 会重复的关键字
        return False
    return True


def _get_ident_name(ident: object) -> str | None:
    try:
        name = ident.get_name()  # type: ignore[union-attr]
        if name:
            return name.strip('"\'')
    except Exception:
        pass
    # sqlparse 对部分关键字（如 type）可能解析为 Token 而非 Identifier，无 get_name
    if hasattr(ident, "value") and ident.value:  # type: ignore[union-attr]
        val = str(ident.value).strip('"\'')
        if val.upper() not in ("DISTINCT", "ALL"):
            return val
    return None


def _sqlparse_result_complete(sql: str, columns: list[str]) -> bool:
    """检测 sqlparse 是否完整且正确：列数须与 SELECT 部分一致，且无重复（sqlparse 对 type 等关键字可能截断或重复）。"""
    m = re.search(r"\bSELECT\s+(.+?)\s+FROM\s", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return True
    select_part = m.group(1)
    depth = 0
    comma_count = 0
    for c in select_part:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            comma_count += 1
    expected_cols = comma_count + 1
    if len(columns) != expected_cols:
        return False
    if len(columns) != len(set(columns)):
        return False  # 有重复
    return True


def _extract_with_regex(sql: str) -> list[str]:
    """正则解析：匹配 SELECT ... FROM，兼容含 SQL 关键字（如 type）的列名。"""
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
