"""SQL 参数类型归一化工具。"""

from __future__ import annotations

from datetime import date, datetime

_INTEGER_FIELD_TYPES = frozenset({"INTEGER", "INT", "BIGINT", "LONG", "SMALLINT"})
_DECIMAL_FIELD_TYPES = frozenset({"NUMBER", "NUMERIC", "DECIMAL"})
_FLOAT_FIELD_TYPES = frozenset({"DOUBLE", "FLOAT", "REAL"})
_BOOLEAN_FIELD_TYPES = frozenset({"BOOLEAN"})
_DATE_FIELD_TYPES = frozenset({"DATE"})
_DATETIME_FIELD_TYPES = frozenset({"DATETIME", "TIMESTAMP"})


def _field_type(value: object | None) -> str:
    """从字段元数据中提取规范化 field_type。"""
    if value is None:
        return ""
    return str(getattr(value, "field_type", "") or "").upper()


def _data_format(value: object | None) -> str:
    """从字段元数据中提取规范化 data_format。"""
    if value is None:
        return ""
    return str(getattr(value, "data_format", "") or "").strip()


def _parse_date_value(normalized_value: str, data_format: str) -> date:
    """按 OWL data_format 将字符串解析为日期。"""
    # 这里仅处理数据库本身就是 DATE / TIMESTAMP 的场景。
    # STRING 日期字段不在这里强转，避免把原始绑定值变成数据库不接受的日期对象。
    if data_format == "yyyyMMdd":
        return datetime.strptime(normalized_value, "%Y%m%d").date()
    if data_format in {"yyyy-MM-dd", "yyyy-MM-dd HH:mm:ss"}:
        return date.fromisoformat(normalized_value[:10])
    return date.fromisoformat(normalized_value[:10])


def _parse_datetime_value(normalized_value: str, data_format: str) -> datetime:
    """按 OWL data_format 将字符串解析为时间戳。"""
    # 同上，仅用于原生 DATETIME/TIMESTAMP 类型。
    if data_format == "yyyyMMddHHmmss":
        return datetime.strptime(normalized_value, "%Y%m%d%H%M%S")
    if data_format == "yyyy-MM-dd HH:mm:ss":
        return datetime.strptime(normalized_value, "%Y-%m-%d %H:%M:%S")
    return datetime.fromisoformat(normalized_value)


def coerce_sql_param(value: object, field: object | None = None) -> object:
    """将字符串参数按字段类型转换为数据库可安全绑定的值。"""
    if value is None or isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return value

    normalized_value = value.strip()
    if not normalized_value:
        return value

    field_type = _field_type(field)
    data_format = _data_format(field)
    analytic_kind = str(getattr(field, "analytic_kind", "") or "")

    try:
        if field_type in _INTEGER_FIELD_TYPES:
            return int(normalized_value)
        if field_type in _DECIMAL_FIELD_TYPES:
            return float(normalized_value)
        if field_type in _FLOAT_FIELD_TYPES:
            return float(normalized_value)
        if field_type in _BOOLEAN_FIELD_TYPES:
            lowered = normalized_value.lower()
            if lowered in {"1", "true", "t", "yes", "y"}:
                return True
            if lowered in {"0", "false", "f", "no", "n"}:
                return False
            raise ValueError
        if field_type in _DATE_FIELD_TYPES:
            return _parse_date_value(normalized_value, data_format)
        if field_type in _DATETIME_FIELD_TYPES:
            return _parse_datetime_value(normalized_value, data_format)
        # STRING 时间串保持原样绑定，由 SQL 生成阶段按 data_format 处理。
    except ValueError as exc:
        field_code = str(getattr(field, "field_code", "") or "")
        field_type_label = field_type or analytic_kind or "unknown"
        raise ValueError(
            f"Cannot coerce value {value!r} to {field_type_label} for field {field_code!r}"
        ) from exc

    return value
