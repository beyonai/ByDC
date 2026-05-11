"""时间字段分组表达式构造器。

统一处理三类时间字段：
- STRING + data_format：按字符串格式切片，不强制转成数据库日期类型。
- DATE/DATETIME：直接沿用数据库原生时间函数。
- period 语义字段：保持账期字符串分组逻辑。

这样可以同时兼容这次的 `yyyyMMdd` 日字段，以及后续的 DATE / DATETIME 字段。
"""

from __future__ import annotations

from typing import Any


def _db_type(value: str) -> str:
    return value.upper()


def _field_type(field: Any | None) -> str:
    if field is None:
        return ""
    return str(getattr(field, "field_type", "") or "").upper()


def _data_format(field: Any | None) -> str:
    if field is None:
        return ""
    return str(getattr(field, "data_format", "") or "").strip()


def _analytic_kind(field: Any | None) -> str:
    if field is None:
        return ""
    return str(getattr(field, "analytic_kind", "") or "").strip()


def _substr_expr(col_expr: str, start: int, length: int, db_type: str) -> str:
    if db_type == "CLICKHOUSE":
        return f"substring({col_expr}, {start}, {length})"
    return f"substr({col_expr}, {start}, {length})"


def _concat_expr(parts: list[str], db_type: str) -> str:
    if db_type == "MYSQL":
        return f"CONCAT({', '.join(parts)})"
    if db_type == "CLICKHOUSE":
        return f"concat({', '.join(parts)})"
    return " || ".join(parts)


def _string_time_expr(col_expr: str, group_op: str, data_format: str, db_type: str) -> str:
    """按字符串格式生成时间分组表达式。"""
    if data_format == "yyyyMMdd":
        year = _substr_expr(col_expr, 1, 4, db_type)
        month = _substr_expr(col_expr, 5, 2, db_type)
        day = _substr_expr(col_expr, 7, 2, db_type)
    else:
        year = _substr_expr(col_expr, 1, 4, db_type)
        month = _substr_expr(col_expr, 6, 2, db_type)
        day = _substr_expr(col_expr, 9, 2, db_type)

    if group_op == "day":
        return _concat_expr([year, "'-'", month, "'-'", day], db_type)
    if group_op == "month":
        return _concat_expr([year, "'-'", month], db_type)
    if group_op == "year":
        return year
    if group_op == "quarter":
        quarter = f"CAST((CAST({month} AS INTEGER) + 2) / 3 AS TEXT)"
        return _concat_expr([year, "'-Q'", quarter], db_type)
    return col_expr


def _native_time_expr(col_expr: str, group_op: str, db_type: str) -> str:
    """沿用数据库原生时间类型的分组表达式。"""
    if group_op == "day":
        if db_type == "MYSQL":
            return f"DATE({col_expr})"
        if db_type in {"POSTGRESQL", "OPENGAUSS"}:
            return f"DATE_TRUNC('day', {col_expr})::date"
        if db_type == "CLICKHOUSE":
            return f"toDate({col_expr})"
        return f"DATE({col_expr})"

    if group_op == "month":
        if db_type == "MYSQL":
            return f"DATE_FORMAT({col_expr}, '%Y-%m')"
        if db_type in {"POSTGRESQL", "OPENGAUSS"}:
            return f"TO_CHAR(DATE_TRUNC('month', {col_expr}), 'YYYY-MM')"
        if db_type == "CLICKHOUSE":
            return f"toStartOfMonth({col_expr})"
        return f"strftime('%Y-%m', {col_expr})"

    if group_op == "quarter":
        if db_type == "MYSQL":
            return f"CONCAT(YEAR({col_expr}), '-Q', QUARTER({col_expr}))"
        if db_type in {"POSTGRESQL", "OPENGAUSS"}:
            return (
                f"CONCAT(DATE_PART('year', {col_expr})::int, '-Q', "
                f"DATE_PART('quarter', {col_expr})::int)"
            )
        if db_type == "CLICKHOUSE":
            return f"toStartOfQuarter({col_expr})"
        return (
            f"CAST(strftime('%Y', {col_expr}) AS TEXT) || '-Q' || "
            f"CAST((CAST(strftime('%m', {col_expr}) AS INTEGER) + 2) / 3 AS TEXT)"
        )

    if group_op == "year":
        if db_type == "MYSQL":
            return f"YEAR({col_expr})"
        if db_type in {"POSTGRESQL", "OPENGAUSS"}:
            return f"DATE_PART('year', {col_expr})::int"
        if db_type == "CLICKHOUSE":
            return f"toYear({col_expr})"
        return f"strftime('%Y', {col_expr})"

    return col_expr


def build_time_group_expr(
    col_expr: str,
    group_op: str,
    db_type: str,
    field: Any | None = None,
) -> str:
    """根据字段元数据构造时间分组表达式。

    规则优先级：
    1. STRING + data_format：按字符串格式分组，不把值强行转成数据库日期。
    2. analytic_kind=period：按账期字符串分组。
    3. 其他情况：沿用原生 DATE/DATETIME 分组逻辑。
    """
    normalized_db = _db_type(db_type)
    field_type = _field_type(field)
    data_format = _data_format(field)
    analytic_kind = _analytic_kind(field)

    # 1) 字符串时间字段优先按 data_format 解析。
    #    这类字段常见于 yyyyMMdd / yyyy-MM / yyyy-MM-dd HH:mm:ss，
    #    不能直接套数据库原生时间函数，否则 PostgreSQL/MySQL 都会把字符串当错类型处理。
    if field_type == "STRING" and data_format:
        return _string_time_expr(col_expr, group_op, data_format, normalized_db)

    # 2) 账期字段保持字符串切片逻辑。period 语义通常已经是规范账期，
    #    直接截取比转日期更稳，也能避免丢失原始粒度。
    if analytic_kind == "period":
        if group_op == "month":
            return f"substr({col_expr}, 1, 7)"
        if group_op == "year":
            return f"substr({col_expr}, 1, 4)"
        if group_op == "quarter":
            return (
                f"substr({col_expr}, 1, 4) || '-Q' || "
                f"CAST((CAST(substr({col_expr}, 6, 2) AS INTEGER) + 2) / 3 AS TEXT)"
            )
        return col_expr

    return _native_time_expr(col_expr, group_op, normalized_db)
