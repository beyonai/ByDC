from __future__ import annotations

import pytest
from datacloud_knowledge.intent.clarification import confirm


@pytest.mark.intent
def test_invoke_confirm_with_retry_retries_transient_stream_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}
    sleep_calls: list[float] = []

    def _fake_invoke() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise ValueError("No generations found in stream")
        return "ok"

    def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(confirm.time, "sleep", _fake_sleep)

    result = confirm._invoke_confirm_with_retry(_fake_invoke)

    assert result == "ok"
    assert calls["count"] == 2
    assert sleep_calls == [1.0]


@pytest.mark.intent
def test_invoke_confirm_with_retry_does_not_retry_non_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}
    sleep_calls: list[float] = []

    def _fake_invoke() -> object:
        calls["count"] += 1
        exc = RuntimeError("bad request")
        exc.status_code = 400  # type: ignore[attr-defined]
        raise exc

    def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(confirm.time, "sleep", _fake_sleep)

    with pytest.raises(RuntimeError, match="bad request"):
        confirm._invoke_confirm_with_retry(_fake_invoke)

    assert calls["count"] == 1
    assert sleep_calls == []
