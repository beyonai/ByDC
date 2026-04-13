"""test_llm_retry.py — TDD 红阶段：llm_retry 模块尚未实现，全部用例应失败。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ─── _is_retryable ────────────────────────────────────────────────────────────

def test_is_retryable_http_429() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _is_retryable

    exc = Exception("rate limited")
    exc.status_code = 429  # type: ignore[attr-defined]
    assert _is_retryable(exc) is True


def test_is_retryable_http_500() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _is_retryable

    exc = Exception("server error")
    exc.status_code = 500  # type: ignore[attr-defined]
    assert _is_retryable(exc) is True


def test_is_retryable_http_503_via_status_attr() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _is_retryable

    exc = Exception("service unavailable")
    exc.status = 503  # type: ignore[attr-defined]  # 某些 SDK 用 .status 而不是 .status_code
    assert _is_retryable(exc) is True


def test_is_retryable_timeout_error() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _is_retryable

    assert _is_retryable(TimeoutError("timed out")) is True


def test_is_retryable_connection_error() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _is_retryable

    assert _is_retryable(ConnectionError("connection refused")) is True


def test_not_retryable_http_400() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _is_retryable

    exc = Exception("bad request")
    exc.status_code = 400  # type: ignore[attr-defined]
    assert _is_retryable(exc) is False


def test_not_retryable_http_401() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _is_retryable

    exc = Exception("unauthorized")
    exc.status_code = 401  # type: ignore[attr-defined]
    assert _is_retryable(exc) is False


def test_not_retryable_http_403() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _is_retryable

    exc = Exception("forbidden")
    exc.status_code = 403  # type: ignore[attr-defined]
    assert _is_retryable(exc) is False


# ─── _parse_retry_after ───────────────────────────────────────────────────────

def test_parse_retry_after_numeric_header() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _parse_retry_after

    class _FakeResp:
        headers = {"Retry-After": "30"}

    exc = Exception()
    exc.response = _FakeResp()  # type: ignore[attr-defined]
    assert _parse_retry_after(exc) == 30.0


def test_parse_retry_after_lowercase_key() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _parse_retry_after

    class _FakeResp:
        headers = {"retry-after": "15"}

    exc = Exception()
    exc.response = _FakeResp()  # type: ignore[attr-defined]
    assert _parse_retry_after(exc) == 15.0


def test_parse_retry_after_no_header_returns_zero() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _parse_retry_after

    assert _parse_retry_after(Exception("no header")) == 0.0


def test_parse_retry_after_non_numeric_returns_zero() -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _parse_retry_after

    class _FakeResp:
        headers = {"Retry-After": "Fri, 31 Dec 2099 23:59:59 GMT"}

    exc = Exception()
    exc.response = _FakeResp()  # type: ignore[attr-defined]
    assert _parse_retry_after(exc) == 0.0


# ─── stream_llm_call_with_retry ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_succeeds_on_first_try() -> None:
    """正常调用直接返回结果，不触发任何重试或 sleep。"""
    from datacloud_analysis.orchestration.execution.llm_retry import stream_llm_call_with_retry

    async def _ok() -> str:
        return "result"

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await stream_llm_call_with_retry(_ok)

    assert result == "result"
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """第一次 500 失败，第二次成功。总调用次数应为 2。"""
    from datacloud_analysis.orchestration.execution.llm_retry import stream_llm_call_with_retry

    call_count = 0

    async def _flaky() -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            exc = Exception("internal server error")
            exc.status_code = 500  # type: ignore[attr-defined]
            raise exc
        return "recovered"

    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "3")
    monkeypatch.setenv("DATACLOUD_LLM_RETRY_MIN_WAIT", "0")

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await stream_llm_call_with_retry(_flaky)

    assert result == "recovered"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted_raises_original_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """重试 max_retries 次后仍失败，抛出原始异常。调用次数 = max_retries + 1。"""
    from datacloud_analysis.orchestration.execution.llm_retry import stream_llm_call_with_retry

    call_count = 0

    async def _always_fail() -> str:
        nonlocal call_count
        call_count += 1
        exc = Exception("server error")
        exc.status_code = 500  # type: ignore[attr-defined]
        raise exc

    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("DATACLOUD_LLM_RETRY_MIN_WAIT", "0")

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(Exception, match="server error"):
            await stream_llm_call_with_retry(_always_fail)

    assert call_count == 3  # 首次 1 次 + 重试 2 次


@pytest.mark.asyncio
async def test_non_retryable_error_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """401 不可重试，直接抛出，不调用 sleep，调用次数仅 1。"""
    from datacloud_analysis.orchestration.execution.llm_retry import stream_llm_call_with_retry

    call_count = 0

    async def _auth_fail() -> str:
        nonlocal call_count
        call_count += 1
        exc = Exception("unauthorized")
        exc.status_code = 401  # type: ignore[attr-defined]
        raise exc

    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "3")

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(Exception, match="unauthorized"):
            await stream_llm_call_with_retry(_auth_fail)

    assert call_count == 1
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_429_adds_extra_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 时等待时间 = 基础退避 + rate_limit_wait（10 秒）。"""
    from datacloud_analysis.orchestration.execution.llm_retry import stream_llm_call_with_retry

    call_count = 0

    async def _rate_limited() -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            exc = Exception("too many requests")
            exc.status_code = 429  # type: ignore[attr-defined]
            raise exc
        return "ok"

    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "3")
    monkeypatch.setenv("DATACLOUD_LLM_RETRY_MIN_WAIT", "1.0")
    monkeypatch.setenv("DATACLOUD_LLM_RETRY_MAX_WAIT", "60.0")
    monkeypatch.setenv("DATACLOUD_LLM_RETRY_RATE_LIMIT_WAIT", "10.0")

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("asyncio.sleep", side_effect=_fake_sleep):
        await stream_llm_call_with_retry(_rate_limited)

    assert len(sleep_calls) == 1
    # attempt=0: base = 1.0 * 2^0 = 1.0, rate_limit = 10.0 → 总计 11.0
    assert sleep_calls[0] == pytest.approx(11.0)


@pytest.mark.asyncio
async def test_exponential_backoff_increases_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """每次重试等待时间按指数增长：1.0, 2.0, 4.0 秒。"""
    from datacloud_analysis.orchestration.execution.llm_retry import stream_llm_call_with_retry

    call_count = 0

    async def _always_fail_500() -> str:
        nonlocal call_count
        call_count += 1
        exc = Exception("server error")
        exc.status_code = 500  # type: ignore[attr-defined]
        raise exc

    monkeypatch.setenv("DATACLOUD_LLM_MAX_RETRIES", "3")
    monkeypatch.setenv("DATACLOUD_LLM_RETRY_MIN_WAIT", "1.0")
    monkeypatch.setenv("DATACLOUD_LLM_RETRY_MAX_WAIT", "60.0")

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("asyncio.sleep", side_effect=_fake_sleep):
        with pytest.raises(Exception):
            await stream_llm_call_with_retry(_always_fail_500)

    assert sleep_calls == pytest.approx([1.0, 2.0, 4.0])


# ─── _build_fallback_llm ──────────────────────────────────────────────────────

def test_build_fallback_llm_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _build_fallback_llm

    monkeypatch.delenv("DATACLOUD_LLM_FALLBACK_ENABLED", raising=False)
    assert _build_fallback_llm() is None


def test_build_fallback_llm_explicit_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _build_fallback_llm

    monkeypatch.setenv("DATACLOUD_LLM_FALLBACK_ENABLED", "false")
    assert _build_fallback_llm() is None


def test_build_fallback_llm_incomplete_config_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """启用但缺少 MODEL/BASE_URL/API_KEY，不抛异常，返回 None。"""
    from datacloud_analysis.orchestration.execution.llm_retry import _build_fallback_llm

    monkeypatch.setenv("DATACLOUD_LLM_FALLBACK_ENABLED", "true")
    monkeypatch.delenv("DATACLOUD_LLM_FALLBACK_MODEL", raising=False)
    monkeypatch.delenv("DATACLOUD_LLM_FALLBACK_BASE_URL", raising=False)
    monkeypatch.delenv("DATACLOUD_LLM_FALLBACK_API_KEY", raising=False)
    assert _build_fallback_llm() is None


def test_build_fallback_llm_returns_llm_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置完整时调用 init_chat_model 并返回其结果。"""
    from datacloud_analysis.orchestration.execution.llm_retry import _build_fallback_llm

    monkeypatch.setenv("DATACLOUD_LLM_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("DATACLOUD_LLM_FALLBACK_MODEL", "gpt-3.5-turbo")
    monkeypatch.setenv("DATACLOUD_LLM_FALLBACK_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("DATACLOUD_LLM_FALLBACK_API_KEY", "sk-test-key")

    fake_llm = object()

    with patch(
        "datacloud_analysis.orchestration.execution.llm_retry.init_chat_model",
        return_value=fake_llm,
    ) as mock_init:
        result = _build_fallback_llm()

    assert result is fake_llm
    mock_init.assert_called_once_with(
        model="gpt-3.5-turbo",
        model_provider="openai",
        api_key="sk-test-key",
        base_url="https://api.openai.com/v1",
        temperature=0.0,
    )
