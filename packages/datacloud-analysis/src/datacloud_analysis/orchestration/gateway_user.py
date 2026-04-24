"""Gateway context user identity helpers."""

from __future__ import annotations

from typing import Any


def get_gateway_user_id(gateway_context: Any) -> str | None:
    """从 gateway_context 获取用户 ID；缺失时不做任何降级。"""
    user_id = str(getattr(gateway_context, "user_id", "") or "").strip()
    if user_id:
        return user_id

    header = getattr(gateway_context, "header", None)
    user_id = str(getattr(header, "user_id", "") or getattr(header, "user_code", "") or "").strip()
    if user_id:
        return user_id

    current_command = getattr(gateway_context, "current_command", None)
    command_header = getattr(current_command, "header", None)
    user_id = str(
        getattr(command_header, "user_id", "") or getattr(command_header, "user_code", "") or ""
    ).strip()
    return user_id or None
