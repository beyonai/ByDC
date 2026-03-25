"""SQL 字面量术语解析：将 WHERE 中的标签/名称替换为标准 code。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from datacloud_data_sdk.plan.models import ObjectViewField, ObjectViewPayload

if TYPE_CHECKING:
    from datacloud_data_sdk.ontology.term_loader import TermLoader


def resolve_sql_literals(
    sql_template: str,
    payload: ObjectViewPayload | None,
    datasource_alias: str,
    term_loader: "TermLoader | None",
) -> str:
    """解析 SQL 中绑定术语字段的字面量，将标签/名称替换为 code。无 payload 或 loader 时原样返回。"""
    if not payload or not term_loader:
        return sql_template

    col_to_field, table_col_to_field = _build_field_mappings(payload, datasource_alias)
    if not col_to_field and not table_col_to_field:
        return sql_template

    try:
        import sqlparse  # noqa: F401
    except ImportError:
        return sql_template

    try:
        return _resolve_with_sqlparse(sql_template, col_to_field, table_col_to_field, term_loader)
    except Exception:
        return sql_template


def _build_field_mappings(
    payload: ObjectViewPayload,
    datasource_alias: str,
) -> tuple[dict[str, ObjectViewField], dict[tuple[str, str], ObjectViewField]]:
    """构建 col->field（无前缀）和 (table,col)->field（含表名）映射。"""
    source_ids = {s.source_id for s in payload.sources if s.datasource_alias == datasource_alias}
    if not source_ids:
        return {}, {}

    col_to_field: dict[str, ObjectViewField] = {}
    table_col_to_field: dict[tuple[str, str], ObjectViewField] = {}
    for obj in payload.objects:
        if obj.source_id not in source_ids or not obj.table:
            continue
        table = obj.table
        for f in obj.fields:
            col = f.source_column or f.name
            if not f.term_set or not col:
                continue
            key = (table, col)
            if key not in table_col_to_field:
                table_col_to_field[key] = f
            if col not in col_to_field:
                col_to_field[col] = f
    return col_to_field, table_col_to_field


def _resolve_with_sqlparse(
    sql: str,
    col_to_field: dict[str, ObjectViewField],
    table_col_to_field: dict[tuple[str, str], ObjectViewField],
    term_loader: "TermLoader",
) -> str:
    import sqlparse
    from sqlparse import sql as sql_ast

    parsed = sqlparse.parse(sql)
    if not parsed:
        return sql

    stmt = parsed[0]
    alias_to_table = _extract_alias_to_table(stmt)
    modified = False

    def _resolve_field(table_or_alias: str | None, col: str) -> ObjectViewField | None:
        if table_or_alias:
            table = alias_to_table.get(table_or_alias, table_or_alias)
            return table_col_to_field.get((table, col))
        return col_to_field.get(col)

    def _process_where(tlist: object) -> None:
        nonlocal modified
        if not hasattr(tlist, "tokens"):
            return
        tokens = getattr(tlist, "tokens", [])
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if isinstance(t, sql_ast.Comparison):
                if _replace_comparison(t, _resolve_field, term_loader):
                    modified = True
            elif isinstance(t, sql_ast.Identifier):
                j = _next_non_ws(tokens, i + 1)
                k = _next_non_ws(tokens, j + 1)
                if j < len(tokens) and k < len(tokens):
                    kw, paren = tokens[j], tokens[k]
                    if (
                        getattr(kw, "value", "").upper() == "IN"
                        and isinstance(paren, sql_ast.Parenthesis)
                    ):
                        if _replace_in_list(t, paren, _resolve_field, term_loader):
                            modified = True
            if hasattr(t, "tokens"):
                _process_where(t)
            i += 1

    for token in stmt.tokens:
        if isinstance(token, sql_ast.Where):
            _process_where(token)
            break

    return str(stmt) if modified else sql


def _extract_alias_to_table(stmt: object) -> dict[str, str]:
    """从 FROM/JOIN 子句提取 alias -> table_name。"""
    from sqlparse import sql as sql_ast

    result: dict[str, str] = {}
    tokens = getattr(stmt, "tokens", [])
    in_from = False
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if getattr(t, "value", "").upper() == "FROM":
            in_from = True
            i += 1
            continue
        if in_from:
            if getattr(t, "value", "").upper() in ("WHERE", "GROUP", "ORDER", "LIMIT", "HAVING", "UNION"):
                break
            if getattr(t, "value", "").upper() == "JOIN":
                i += 1
                continue
            for table, alias in _parse_table_aliases(t):
                if table and alias:
                    result[alias] = table
                elif table:
                    result[table] = table
        i += 1
    return result


def _parse_table_aliases(token: object) -> list[tuple[str, str | None]]:
    """从 Identifier/IdentifierList 解析 (table_name, alias) 列表。"""
    from sqlparse import sql as sql_ast

    out: list[tuple[str, str | None]] = []
    if isinstance(token, sql_ast.IdentifierList):
        for ident in token.get_identifiers():
            out.extend(_parse_table_aliases(ident))
        return out
    if isinstance(token, sql_ast.Identifier):
        try:
            real = token.get_real_name()
            alias = token.get_alias()
            name = real or (token.get_name() or "").strip('"\'')
            if name:
                out.append((name, alias))
        except Exception:
            pass
    return out


def _next_non_ws(tokens: list, start: int) -> int:
    """返回下一个非空白 token 的索引，若无则返回 len(tokens)。"""
    from sqlparse.tokens import Whitespace

    while start < len(tokens):
        if getattr(tokens[start], "ttype", None) != Whitespace:
            return start
        start += 1
    return start


def _get_qualified_column(ident: object) -> tuple[str | None, str]:
    """从 Identifier 提取 (table_or_alias, column)。无前缀时返回 (None, col)。"""
    try:
        name = ident.get_name()  # type: ignore[union-attr]
        if not name:
            return None, ""
        s = name.strip('"\'')
        if "." in s:
            parts = s.split(".")
            return parts[0], parts[-1]
        return None, s
    except Exception:
        return None, ""


def _get_string_value(token: object) -> str | None:
    """从 Single/Literal 提取字符串值（去引号）。"""
    val = getattr(token, "value", None) or str(token)
    if not val or len(val) < 2:
        return None
    if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
        return val[1:-1]
    return val


def _replace_comparison(
    comparison: object,
    resolve_field: object,
    term_loader: "TermLoader",
) -> bool:
    """替换 Comparison 中的字面量。"""
    tokens = getattr(comparison, "tokens", [])
    if len(tokens) < 5:
        return False
    left = tokens[0]
    right = tokens[-1]
    table_or_alias, col = _get_qualified_column(left)
    if not col:
        return False
    field = resolve_field(table_or_alias, col) if callable(resolve_field) else None
    if not field:
        return False
    raw = _get_string_value(right)
    if raw is None:
        return False
    try:
        resolved = term_loader.resolve_value(
            field.term_set,
            raw,
            term_field=field.term_field,
            dataset_id=field.dataset_id,
            term_type_code=field.term_set.split(".")[0] if field.term_set and "." in field.term_set else None,
        )
        quote = "'" if str(right).startswith("'") else '"'
        right.value = f"{quote}{resolved}{quote}"  # type: ignore[union-attr]
        return True
    except ValueError:
        return False


def _replace_in_list(
    ident: object,
    paren: object,
    resolve_field: object,
    term_loader: "TermLoader",
) -> bool:
    """替换 IN ('v1','v2') 中的字面量。"""
    table_or_alias, col = _get_qualified_column(ident)
    if not col:
        return False
    field = resolve_field(table_or_alias, col) if callable(resolve_field) else None
    if not field:
        return False
    changed = False
    for t in _iter_string_literals(paren):
        raw = _get_string_value(t)
        if raw is None:
            continue
        try:
            resolved = term_loader.resolve_value(
                field.term_set,
                raw,
                term_field=field.term_field,
                dataset_id=field.dataset_id,
                term_type_code=field.term_set.split(".")[0] if field.term_set and "." in field.term_set else None,
            )
            quote = "'" if str(t).startswith("'") else '"'
            t.value = f"{quote}{resolved}{quote}"  # type: ignore[union-attr]
            changed = True
        except ValueError:
            pass
    return changed


def _iter_string_literals(node: object) -> list:
    """递归收集 Parenthesis/IdentifierList 中的 Single 字面量 token。"""
    from sqlparse.tokens import Literal

    out: list = []
    tokens = getattr(node, "tokens", [])
    for t in tokens:
        if getattr(t, "ttype", None) == Literal.String.Single:
            out.append(t)
        elif hasattr(t, "tokens"):
            out.extend(_iter_string_literals(t))
    return out
