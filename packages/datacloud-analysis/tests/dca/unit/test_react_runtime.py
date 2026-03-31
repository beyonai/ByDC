from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from datacloud_analysis.orchestration.execution import react_runtime
from datacloud_analysis.orchestration.execution.react_runtime import select_react_capability


@dataclass
class _FakeAIMessage:
    tool_calls: list[dict[str, Any]]


class _FakeBoundModel:
    def __init__(self, tool_calls: list[dict[str, Any]]) -> None:
        self._tool_calls = tool_calls

    async def ainvoke(self, _messages: list[Any]) -> _FakeAIMessage:
        return _FakeAIMessage(tool_calls=self._tool_calls)


class _FakeModel:
    def __init__(self, tool_calls: list[dict[str, Any]]) -> None:
        self._tool_calls = tool_calls

    def bind_tools(self, *_args: Any, **_kwargs: Any) -> _FakeBoundModel:
        return _FakeBoundModel(self._tool_calls)


@pytest.mark.asyncio
async def test_select_react_capability_uses_llm_function_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_init_chat_model(*_args: Any, **_kwargs: Any) -> _FakeModel:
        return _FakeModel(
            tool_calls=[
                {
                    "id": "call_123",
                    "name": "choose_capability",
                    "args": {"capability_id": "skill.normalize", "reason": "best fit"},
                }
            ]
        )

    monkeypatch.setattr(react_runtime, "init_chat_model", _fake_init_chat_model)

    out = await select_react_capability(
        state={},
        todo={"goal": "normalize dataset"},
        candidates=["tool.query", "skill.normalize"],
        round_index=1,
    )

    assert out["capability_id"] == "skill.normalize"
    assert out["source"] == "llm_function_call"
    assert out["tool_call_id"] == "call_123"


@pytest.mark.asyncio
async def test_select_react_capability_falls_back_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def _should_not_be_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("init_chat_model should not be called when function-call is disabled")

    monkeypatch.setattr(react_runtime, "init_chat_model", _should_not_be_called)

    out = await select_react_capability(
        state={"react_function_call_enabled": False},
        todo={"goal": "query"},
        candidates=["tool.query"],
        round_index=1,
    )

    assert out["capability_id"] == "tool.query"
    assert out["source"] == "fallback"
    assert out["reason"] == "function_call_disabled"
    assert out["tool_call_id"] is None


@pytest.mark.asyncio
async def test_select_react_capability_falls_back_when_tool_call_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_init_chat_model(*_args: Any, **_kwargs: Any) -> _FakeModel:
        return _FakeModel(
            tool_calls=[
                {
                    "id": "call_invalid",
                    "name": "choose_capability",
                    "args": {"capability_id": "not_in_candidates", "reason": "invalid"},
                }
            ]
        )

    monkeypatch.setattr(react_runtime, "init_chat_model", _fake_init_chat_model)

    out = await select_react_capability(
        state={},
        todo={"goal": "query"},
        candidates=["tool.query", "tool.search"],
        round_index=1,
    )

    assert out["capability_id"] == "tool.query"
    assert out["source"] == "fallback"
    assert out["reason"] == "no_valid_tool_call"


@pytest.mark.asyncio
async def test_select_react_capability_returns_empty_fallback_for_empty_candidates() -> None:
    out = await select_react_capability(
        state={},
        todo={"goal": "none"},
        candidates=[],
        round_index=1,
    )

    assert out["capability_id"] == ""
    assert out["source"] == "fallback"
    assert out["reason"] == "empty_candidates"


@pytest.mark.asyncio
async def test_select_react_capability_normalizes_provider_prefixed_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_init_chat_model(*args: Any, **kwargs: Any) -> _FakeModel:
        captured["model"] = args[0] if args else None
        captured["model_provider"] = kwargs.get("model_provider")
        return _FakeModel(
            tool_calls=[
                {
                    "id": "call_prefixed",
                    "name": "choose_capability",
                    "args": {"capability_id": "tool.query", "reason": "normalized"},
                }
            ]
        )

    monkeypatch.setenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    monkeypatch.setattr(react_runtime, "init_chat_model", _fake_init_chat_model)

    out = await select_react_capability(
        state={},
        todo={"goal": "query"},
        candidates=["tool.query", "tool.search"],
        round_index=1,
    )

    assert out["capability_id"] == "tool.query"
    assert captured["model"] == "Qwen/Qwen3-235B-A22B"
    assert captured["model_provider"] == "openai"


