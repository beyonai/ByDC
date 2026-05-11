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
        if field_type in _DATE_FIELD_TYPES or analytic_kind == "datetime":
            return date.fromisoformat(normalized_value[:10])
        if field_type in _DATETIME_FIELD_TYPES:
            return datetime.fromisoformat(normalized_value)
    except ValueError as exc:
        field_code = str(getattr(field, "field_code", "") or "")
        field_type_label = field_type or analytic_kind or "unknown"
        raise ValueError(
            f"Cannot coerce value {value!r} to {field_type_label} for field {field_code!r}"
        ) from exc

    return value
