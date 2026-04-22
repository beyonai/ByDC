"""test_llm_retry.py — 覆盖 LLM 重试与备用模型关闭行为。"""

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

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        3,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MIN_WAIT",
        0.0,
    )

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

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        2,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MIN_WAIT",
        0.0,
    )

    with (
        patch("asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(Exception, match="server error"),
    ):
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

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        3,
    )

    with (
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        pytest.raises(Exception, match="unauthorized"),
    ):
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

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        3,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MIN_WAIT",
        1.0,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_WAIT",
        60.0,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_RATE_LIMIT_WAIT",
        10.0,
    )

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("asyncio.sleep", side_effect=_fake_sleep):
        await stream_llm_call_with_retry(_rate_limited)

    assert len(sleep_calls) == 1
    # attempt=0: base = 1.0 * 2^0 = 1.0, rate_limit = 10.0 → 总计 11.0
    assert sleep_calls[0] == pytest.approx(11.0)


@pytest.mark.asyncio
async def test_rate_limit_429_prefers_retry_after_over_default_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """429 with Retry-After should add Retry-After seconds instead of default extra wait."""
    from datacloud_analysis.orchestration.execution.llm_retry import stream_llm_call_with_retry

    call_count = 0

    class _Resp:
        headers = {"Retry-After": "3"}

    async def _rate_limited_with_header() -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            exc = Exception("too many requests")
            exc.status_code = 429  # type: ignore[attr-defined]
            exc.response = _Resp()  # type: ignore[attr-defined]
            raise exc
        return "ok"

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        3,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MIN_WAIT",
        1.0,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_WAIT",
        60.0,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_RATE_LIMIT_WAIT",
        10.0,
    )

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("asyncio.sleep", side_effect=_fake_sleep):
        await stream_llm_call_with_retry(_rate_limited_with_header)

    assert len(sleep_calls) == 1
    # attempt=0: base 1.0 + Retry-After 3.0 = 4.0 (should not add default 10.0)
    assert sleep_calls[0] == pytest.approx(4.0)


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

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        3,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MIN_WAIT",
        1.0,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_WAIT",
        60.0,
    )

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with (
        patch("asyncio.sleep", side_effect=_fake_sleep),
        pytest.raises(
            Exception,
            match="server error",
        ),
    ):
        await stream_llm_call_with_retry(_always_fail_500)

    assert sleep_calls == pytest.approx([1.0, 2.0, 4.0])


@pytest.mark.asyncio
async def test_max_wait_caps_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backoff should be capped by _DEFAULT_MAX_WAIT."""
    from datacloud_analysis.orchestration.execution.llm_retry import stream_llm_call_with_retry

    async def _always_fail_500() -> str:
        exc = Exception("server error")
        exc.status_code = 500  # type: ignore[attr-defined]
        raise exc

    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_RETRIES",
        3,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MIN_WAIT",
        5.0,
    )
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.execution.llm_retry._DEFAULT_MAX_WAIT",
        6.0,
    )

    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with (
        patch("asyncio.sleep", side_effect=_fake_sleep),
        pytest.raises(Exception, match="server error"),
    ):
        await stream_llm_call_with_retry(_always_fail_500)

    # attempt waits: min(5,6)=5, min(10,6)=6, min(20,6)=6
    assert sleep_calls == pytest.approx([5.0, 6.0, 6.0])


# ─── _build_fallback_llm ──────────────────────────────────────────────────────


def test_build_fallback_llm_always_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from datacloud_analysis.orchestration.execution.llm_retry import _build_fallback_llm

    _ = monkeypatch
    assert _build_fallback_llm() is None
