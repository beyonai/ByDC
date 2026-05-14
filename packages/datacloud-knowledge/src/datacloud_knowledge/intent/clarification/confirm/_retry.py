"""确认重试与 LLM 输出清洗 — 指数退避重试 + tool call 参数 sanitize。"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_CONFIRM_MAX_RETRIES = 2
_CONFIRM_RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_CONFIRM_NON_RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({400, 401, 403})

# LLM 可能在列表字段中传 null（如 select: [null]），或以 JSON 字符串传递列表
_LIST_FIELDS_TO_SANITIZE = (
    "select",
    "filters",
    "order_by",
    "dimensions",
    "metrics",
    "having",
    "clarify_items",
    "confirmed_conditions",
)


def _sanitize_confirm_args(args: dict[str, Any]) -> None:
    """清洗 LLM tool call 参数：JSON 字符串解码 + 过滤列表中的 None 值。"""
    for field in _LIST_FIELDS_TO_SANITIZE:
        val = args.get(field)
        # LLM 有时以 JSON 字符串传递列表/对象
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    val = parsed
                    args[field] = val
            except (json.JSONDecodeError, ValueError):
                pass
        if isinstance(val, list):
            args[field] = [item for item in val if item is not None]


def _is_retryable_confirm_error(exc: Exception) -> bool:
    """Return whether a clarification confirm failure is likely transient."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status is not None:
        if int(status) in _CONFIRM_NON_RETRYABLE_HTTP_STATUS:
            return False
        return int(status) in _CONFIRM_RETRYABLE_HTTP_STATUS
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return isinstance(exc, ValueError) and "No generations found in stream" in str(exc)


def _invoke_confirm_with_retry(invoke: Callable[[], Any]) -> Any:
    """Invoke confirmation LLM call with minimal retry for transient failures."""
    last_exc: Exception | None = None

    for attempt in range(_CONFIRM_MAX_RETRIES + 1):
        try:
            return invoke()
        except Exception as exc:
            last_exc = exc
            if not _is_retryable_confirm_error(exc) or attempt >= _CONFIRM_MAX_RETRIES:
                raise

            wait_seconds = float(2**attempt)
            logger.warning(
                "[confirm] LLM 确认调用失败，第 %d/%d 次重试，等待 %.1f 秒: %s",
                attempt + 1,
                _CONFIRM_MAX_RETRIES,
                wait_seconds,
                exc,
            )
            time.sleep(wait_seconds)

    if last_exc is None:
        raise RuntimeError("confirm retry loop exited without result")
    raise last_exc
