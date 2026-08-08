"""测试 build_llm 参数化：thinking / temperature 按调用方覆盖。

覆盖场景：
- thinking=False → extra_body.thinking.type == "disabled"
- thinking=True → extra_body.thinking.type == "enabled"
- temperature 显式传入覆盖环境变量（DATACLOUD_LLM_TEMPERATURE）
- 不传参数行为完全不变（向后兼容：document_enrich 等调用不受影响）
- 显式参数优先于环境 MODEL_KWARGS 中同键
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """固定 DATACLOUD_LLM 环境（temperature=1，与生产 .env 一致）。"""
    monkeypatch.setenv("DATACLOUD_LLM_API_BASE", "https://llm.example.test/v1")
    monkeypatch.setenv("DATACLOUD_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DATACLOUD_LLM_MODEL", "test-model")
    monkeypatch.setenv("DATACLOUD_LLM_TEMPERATURE", "1")
    monkeypatch.delenv("DATACLOUD_LLM_MODEL_KWARGS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)


@pytest.fixture
def capture_kwargs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """捕获 init_chat_model 的 kwargs，返回假 LLM。"""
    captured: list[dict[str, Any]] = []

    def _fake_init(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return object()

    monkeypatch.setattr("langchain.chat_models.init_chat_model", _fake_init)
    return captured


def test_build_llm_thinking_false_disables_thinking(
    llm_env: None, capture_kwargs: list[dict[str, Any]]
) -> None:
    from datacloud_knowledge.intent.llm_utils import build_llm

    build_llm(thinking=False)
    kwargs = capture_kwargs[0]
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_build_llm_thinking_true_enables_thinking(
    llm_env: None, capture_kwargs: list[dict[str, Any]]
) -> None:
    from datacloud_knowledge.intent.llm_utils import build_llm

    build_llm(thinking=True)
    kwargs = capture_kwargs[0]
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


def test_build_llm_temperature_overrides_env(
    llm_env: None, capture_kwargs: list[dict[str, Any]]
) -> None:
    from datacloud_knowledge.intent.llm_utils import build_llm

    build_llm(temperature=0.0)
    kwargs = capture_kwargs[0]
    assert kwargs["temperature"] == 0.0


def test_build_llm_default_behavior_unchanged(
    llm_env: None, capture_kwargs: list[dict[str, Any]]
) -> None:
    """不传参数：temperature 取自环境变量，不附加 extra_body。"""
    from datacloud_knowledge.intent.llm_utils import build_llm

    build_llm()
    kwargs = capture_kwargs[0]
    assert kwargs["temperature"] == 1.0
    assert "extra_body" not in kwargs


def test_build_llm_explicit_overrides_model_kwargs_thinking(
    llm_env: None, monkeypatch: pytest.MonkeyPatch, capture_kwargs: list[dict[str, Any]]
) -> None:
    """显式 thinking 优先于环境 MODEL_KWARGS 中的同键。"""
    monkeypatch.setenv(
        "DATACLOUD_LLM_MODEL_KWARGS",
        '{"extra_body": {"thinking": {"type": "enabled"}}}',
    )
    from datacloud_knowledge.intent.llm_utils import build_llm

    build_llm(thinking=False)
    kwargs = capture_kwargs[0]
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_build_llm_thinking_merges_other_extra_body_keys(
    llm_env: None, monkeypatch: pytest.MonkeyPatch, capture_kwargs: list[dict[str, Any]]
) -> None:
    """显式 thinking 合并而非覆盖 MODEL_KWARGS 中 extra_body 的其他键。"""
    monkeypatch.setenv(
        "DATACLOUD_LLM_MODEL_KWARGS",
        '{"extra_body": {"metadata": {"tag": "x"}}}',
    )
    from datacloud_knowledge.intent.llm_utils import build_llm

    build_llm(thinking=False)
    kwargs = capture_kwargs[0]
    assert kwargs["extra_body"] == {
        "metadata": {"tag": "x"},
        "thinking": {"type": "disabled"},
    }
