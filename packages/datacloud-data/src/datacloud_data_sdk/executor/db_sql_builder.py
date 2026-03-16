"""SQL 构建：filters → WHERE，SELECT/aggregates/group_by → 完整 SQL。"""

from __future__ import annotations

from typing import Any

_DOUBLE_QUOTE_DBS = {"POSTGRESQL", "OPENGAUSS", "SQLITE"}
_BACKTICK_DBS = {"MYSQL", "CLICKHOUSE"}


def _quote(ident: str, db_type: str) -> str:
    """按 db_type 对标识符加引号。"""
    if db_type.upper() in _DOUBLE_QUOTE_DBS:
        return f'"{ident}"'
    if db_type.upper() in _BACKTICK_DBS:
        return f"`{ident}`"
    return ident


def build_select_sql(
    table: str,
    fields: list[tuple[str, str]],
    aggregates: list[dict[str, Any]] | None,
    group_by: list[str] | None,
    where_sql: str,
    db_type: str,
    field_to_col: dict[str, str],
    derived_expressions: list[tuple[str, str]] | None = None,
    derived_aggregations: list[dict[str, Any]] | None = None,
    linked_joins: list[dict[str, Any]] | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> tuple[str, list[str]]:
    """构建完整 SELECT SQL 与输出列 key 列表。"""
    q = lambda x: _quote(x, db_type)
    quoted_table = q(table)
    join_clauses: list[str] = []

    if not aggregates:
        # 无聚合：SELECT 全部 fields + derived expressions + derived aggregations + linked target columns
        # 有 linked_joins 时主表列需加表名前缀避免歧义
        main_prefix = f"{quoted_table}." if linked_joins else ""
        select_parts = [f"{main_prefix}{q(col)} AS {q(fc)}" for fc, col in fields]
        col_keys = [fc for fc, _ in fields]
        if derived_expressions:
            for alias, expression in derived_expressions:
                select_parts.append(f"({expression}) AS {q(alias)}")
                col_keys.append(alias)
        if derived_aggregations:
            for da in derived_aggregations:
                alias = da.get("alias", "")
                target_table = da.get("target_table", "")
                target_field = da.get("target_field", "")
                func = da.get("func", "count").upper()
                join_from = da.get("join_from", "")
                join_to = da.get("join_to", "")
                subquery = f"(SELECT {func}({q(target_field)}) FROM {q(target_table)} o WHERE o.{q(join_to)} = {quoted_table}.{q(join_from)}) AS {q(alias)}"
                select_parts.append(subquery)
                col_keys.append(alias)
        # linked_joins: 追加 target 列，前缀 linked_field_field_code
        if linked_joins:
            for idx, lj in enumerate(linked_joins):
                linked_field = lj.get("linked_field", "")
                target_table = lj.get("target_table", "")
                join_from = lj.get("join_from", "")
                join_to = lj.get("join_to", "")
                target_fields = lj.get("target_fields", [])
                talias = f"t{idx}" if idx > 0 else "t"
                for field_code, col in target_fields:
                    alias = f"{linked_field}_{field_code}"
                    select_parts.append(f"{q(talias)}.{q(col)} AS {q(alias)}")
                    col_keys.append(alias)
                join_clauses.append(
                    f"LEFT JOIN {q(target_table)} {q(talias)} ON {quoted_table}.{q(join_from)} = {q(talias)}.{q(join_to)}"
                )
    elif group_by:
        # 有聚合 + group_by：SELECT group_by 列 + 聚合
        group_cols = [field_to_col.get(gb, gb) for gb in group_by]
        select_parts = [f"{q(c)} AS {q(gb)}" for gb, c in zip(group_by, group_cols)]
        for agg in aggregates or []:
            f = agg.get("field", "")
            func = agg.get("func", "count").upper()
            alias = agg.get("as") or f"{func.lower()}_{f}"
            col = field_to_col.get(f, f)
            select_parts.append(f"{func}({q(col)}) AS {q(alias)}")
        col_keys = list(group_by) + [
            agg.get("as") or f"{agg.get('func', 'count').lower()}_{agg.get('field', '')}"
            for agg in (aggregates or [])
        ]
    else:
        # 仅聚合
        select_parts = []
        col_keys = []
        for agg in aggregates or []:
            f = agg.get("field", "")
            func = agg.get("func", "count").upper()
            alias = agg.get("as") or f"{func.lower()}_{f}"
            col = field_to_col.get(f, f)
            select_parts.append(f"{func}({q(col)}) AS {q(alias)}")
            col_keys.append(alias)

    select_clause = ", ".join(select_parts)
    sql = f"SELECT {select_clause} FROM {quoted_table}"
    if linked_joins:
        for jc in join_clauses:
            sql += " " + jc
    if where_sql:
        sql += f" WHERE {where_sql}"
    if group_by:
        group_cols = [field_to_col.get(gb, gb) for gb in group_by]
        sql += " GROUP BY " + ", ".join(q(c) for c in group_cols)

    if limit is not None:
        sql += f" LIMIT {limit}"
    if offset is not None:
        sql += f" OFFSET {offset}"

    return sql, col_keys


def build_where_clause(
    filters: dict[str, Any],
    field_to_col: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    """从 filters 构建 WHERE 子句与命名参数。空 filters 返回 ("", {})。"""
    if not filters:
        return "", {}

    conditions: list[str] = []
    params: dict[str, Any] = {}

    for field_code, spec in filters.items():
        if not isinstance(spec, dict):
            continue
        op = spec.get("op")
        value = spec.get("value")
        col = field_to_col.get(field_code, field_code)
        param_name = f"p_{field_code}"

        if op == "is_null":
            conditions.append(f'"{col}" IS NULL')
            continue
        if op == "is_not_null":
            conditions.append(f'"{col}" IS NOT NULL')
            continue

        if op in ("eq", "gt", "gte", "lt", "lte", "like"):
            if value is None:
                continue
            op_sql = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "like": "LIKE"}[op]
            conditions.append(f'"{col}" {op_sql} :{param_name}')
            params[param_name] = value
        elif op == "in":
            if not isinstance(value, (list, tuple)) or not value:
                continue
            placeholders = ", ".join(f":{param_name}_{i}" for i in range(len(value)))
            conditions.append(f'"{col}" IN ({placeholders})')
            for i, v in enumerate(value):
                params[f"{param_name}_{i}"] = v

    if not conditions:
        return "", {}

    return " AND ".join(conditions), params
