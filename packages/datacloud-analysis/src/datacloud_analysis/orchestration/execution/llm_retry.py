"""llm_retry.py — LLM 调用重试（指数退避）与备用模型构建。

环境变量：
    DATACLOUD_LLM_MAX_RETRIES           最大重试次数（默认 3，不含首次）
    DATACLOUD_LLM_RETRY_MIN_WAIT        首次重试前等待秒数（默认 1.0）
    DATACLOUD_LLM_RETRY_MAX_WAIT        等待秒数上限（默认 30.0）
    DATACLOUD_LLM_RETRY_RATE_LIMIT_WAIT 429 时额外附加等待秒数（默认 10.0）
    DATACLOUD_LLM_FALLBACK_ENABLED      是否启用备用模型（true/false，默认 false）
    DATACLOUD_LLM_FALLBACK_MODEL        备用模型名称
    DATACLOUD_LLM_FALLBACK_BASE_URL     备用模型 API 地址
    DATACLOUD_LLM_FALLBACK_API_KEY      备用模型 API Key
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Callable

from langchain.chat_models import init_chat_model

logger = logging.getLogger(__name__)

# 模块级默认值（运行时实际读取 environ，支持测试通过 monkeypatch 动态修改）
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
    headers: dict = getattr(response, "headers", {}) if response else {}
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

    - 可重试错误（5xx / 网络层）：等待后重试，最多 DATACLOUD_LLM_MAX_RETRIES 次
    - 不可重试错误（4xx 客户端错误）：直接抛出
    - 429 限流：在基础退避基础上额外加 DATACLOUD_LLM_RETRY_RATE_LIMIT_WAIT 秒
    """
    max_retries = int(os.environ.get("DATACLOUD_LLM_MAX_RETRIES", str(_DEFAULT_MAX_RETRIES)))
    min_wait = float(os.environ.get("DATACLOUD_LLM_RETRY_MIN_WAIT", str(_DEFAULT_MIN_WAIT)))
    max_wait = float(os.environ.get("DATACLOUD_LLM_RETRY_MAX_WAIT", str(_DEFAULT_MAX_WAIT)))
    rate_limit_wait = float(os.environ.get("DATACLOUD_LLM_RETRY_RATE_LIMIT_WAIT", str(_DEFAULT_RATE_LIMIT_WAIT)))

    last_exc: BaseException | None = None

    for attempt in range(max_retries + 1):
        try:
            return await llm_call(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            is_rate_limit = (
                getattr(exc, "status_code", None) == 429
                or getattr(exc, "status", None) == 429
            )
            if not _is_retryable(exc) or attempt >= max_retries:
                logger.error(
                    "[LLM] 不可重试错误或达到最大重试次数 attempt=%d/%d: %s",
                    attempt,
                    max_retries,
                    exc,
                )
                raise

            wait = min(min_wait * (2 ** attempt), max_wait)
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
    raise last_exc  # type: ignore[misc]


def _build_fallback_llm() -> Any | None:
    """根据环境变量构建备用 LLM 实例，未启用或配置不完整时返回 None。

    每次请求调用此函数，不缓存——备用模型的意图是"本次请求"的兜底，
    下次请求仍先尝试主模型。
    """
    if os.environ.get("DATACLOUD_LLM_FALLBACK_ENABLED", "false").lower() != "true":
        return None

    model = os.environ.get("DATACLOUD_LLM_FALLBACK_MODEL", "")
    base_url = os.environ.get("DATACLOUD_LLM_FALLBACK_BASE_URL", "")
    api_key = os.environ.get("DATACLOUD_LLM_FALLBACK_API_KEY", "")

    if not (model and base_url and api_key):
        logger.warning(
            "[LLM] DATACLOUD_LLM_FALLBACK_ENABLED=true 但配置不完整"
            "（需要 MODEL / BASE_URL / API_KEY），备用模型未启用"
        )
        return None

    try:
        return init_chat_model(
            model=model,
            model_provider="openai",
            api_key=api_key,
            base_url=base_url,
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning("[LLM] 备用模型初始化失败: %s", exc)
        return None
