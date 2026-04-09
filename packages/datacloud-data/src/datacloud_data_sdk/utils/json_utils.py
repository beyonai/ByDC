"""JSON 序列化辅助工具。"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


def json_default(value: Any) -> Any:
    """将常见非 JSON 原生类型转换为可序列化值。"""
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return str(value)


def dump_json(value: Any) -> str:
    """输出对 MCP/HTTP 友好的 JSON 文本。"""
    return json.dumps(value, ensure_ascii=False, default=json_default)
