"""llm_retry.py — LLM 调用重试（指数退避）与备用模型占位。

当前运行时只暴露统一的 DATACLOUD_LLM_* 环境变量。
重试与备用模型策略使用代码内默认值，不再通过环境变量配置。
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

# 模块级默认值
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_MIN_WAIT = 1.0
_DEFAULT_MAX_WAIT = 30.0
_DEFAULT_RATE_LIMIT_WAIT = 10.0

# 可重试的 HTTP 状态码
_RETRYABLE_HTTP: frozenset[int] = frozenset({429, 500, 502, 503, 504})
# 明确不可重试的 HTTP 状态码
_NON_RETRYABLE_HTTP: frozenset[int] = frozenset({400, 401, 403})


def _is_retryable(exc: BaseException) -> bool:
    """判断异常是否值得重试。

    规则：
    - 有 status_code / status 属性 → 查表
    - 无 status 的网络层异常（TimeoutError / ConnectionError 等）→ 一律重试
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status is not None:
        if status in _NON_RETRYABLE_HTTP:
            return False
        return int(status) in _RETRYABLE_HTTP
    # 无 HTTP status：网络层异常，默认可重试
    return True


def _parse_retry_after(exc: BaseException) -> float:
    """从 429 响应头中解析 Retry-After 秒数，找不到或非数字返回 0.0。"""
    response = getattr(exc, "response", None)
    raw_headers = getattr(response, "headers", None) if response else None
    headers: Mapping[str, Any] = raw_headers if isinstance(raw_headers, Mapping) else {}
    ra = headers.get("Retry-After") or headers.get("retry-after", "")
    if ra and re.match(r"^\d+$", str(ra)):
        return float(ra)
    return 0.0


async def stream_llm_call_with_retry(
    llm_call: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """对 llm_call(*args, **kwargs) 进行指数退避重试包装。

    - 可重试错误（5xx / 网络层）：等待后重试，最多 3 次
    - 不可重试错误（4xx 客户端错误）：直接抛出
    - 429 限流：在基础退避基础上额外加 10 秒
    """
    max_retries = _DEFAULT_MAX_RETRIES
    min_wait = _DEFAULT_MIN_WAIT
    max_wait = _DEFAULT_MAX_WAIT
    rate_limit_wait = _DEFAULT_RATE_LIMIT_WAIT

    last_exc: BaseException | None = None

    for attempt in range(max_retries + 1):
        try:
            return await llm_call(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            is_rate_limit = (
                getattr(exc, "status_code", None) == 429 or getattr(exc, "status", None) == 429
            )
            if not _is_retryable(exc) or attempt >= max_retries:
                logger.error(
                    "[LLM] 不可重试错误或达到最大重试次数 attempt=%d/%d: %s",
                    attempt,
                    max_retries,
                    exc,
                )
                raise

            wait = min(min_wait * (2**attempt), max_wait)
            if is_rate_limit:
                wait += _parse_retry_after(exc) or rate_limit_wait

            logger.warning(
                "[LLM] 调用失败，第 %d/%d 次重试，等待 %.1f 秒: %s",
                attempt + 1,
                max_retries,
                wait,
                exc,
            )
            await asyncio.sleep(wait)

    # 理论上不会到达此处（循环内 raise 或 return），但类型检查需要
    if last_exc is None:
        raise RuntimeError("LLM retry loop exited without result")
    raise last_exc


def _build_fallback_llm() -> Any | None:
    """备用模型当前关闭，后续若恢复请改为代码配置而非环境变量。"""
    return None
