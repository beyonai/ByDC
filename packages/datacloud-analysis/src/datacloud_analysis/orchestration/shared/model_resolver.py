"""Reasoning-model normalization helpers shared across orchestration nodes."""

from __future__ import annotations

import os
from typing import TypedDict

_DEFAULT_REASONING_MODEL = "Qwen/Qwen3-235B-A22B"
_DEFAULT_PROVIDER = "openai"
_KNOWN_PROVIDERS: frozenset[str] = frozenset(
    {
        "openai",
        "azure_openai",
        "anthropic",
        "google_genai",
        "bedrock",
        "ollama",
    }
)


class ReasoningModelSpec(TypedDict):
    """Normalized model settings for ``init_chat_model``."""

    raw_model: str
    model: str
    model_provider: str
    provider_prefixed: bool


def resolve_reasoning_model_spec(raw_model: str | None = None) -> ReasoningModelSpec:
    """Resolve model/provider for LangChain init_chat_model.

    Rules:
    1. Read from ``DATACLOUD_LLM_MODEL`` when ``raw_model`` is None.
    2. Accept provider-prefixed value like ``openai:Qwen/Qwen3-235B-A22B``.
    3. Strip known provider prefix and return provider separately.
    4. Keep unknown prefixes as-is (treat whole value as model).

    注意：推荐使用 ``DATACLOUD_LLM_MODEL_PROVIDER`` 环境变量显式指定协议
    （``openai`` 或 ``anthropic``），不要在 ``DATACLOUD_LLM_MODEL`` 中使用
    ``provider:model`` 前缀写法，两者同时存在时以 ``DATACLOUD_LLM_MODEL_PROVIDER``
    为准。
    """
    raw = (raw_model if raw_model is not None else os.getenv("DATACLOUD_LLM_MODEL", "")).strip()
    if not raw:
        raw = _DEFAULT_REASONING_MODEL

    provider = _DEFAULT_PROVIDER
    model = raw
    provider_prefixed = False
    if ":" in raw:
        prefix, suffix = raw.split(":", 1)
        prefix = prefix.strip()
        suffix = suffix.strip()
        normalized_prefix = prefix.lower()
        if normalized_prefix in _KNOWN_PROVIDERS and suffix:
            provider = normalized_prefix
            model = suffix
            provider_prefixed = True

    return {
        "raw_model": raw,
        "model": model,
        "model_provider": provider,
        "provider_prefixed": provider_prefixed,
    }


def resolve_reasoning_api_key() -> str | None:
    """Resolve API key fallback chain for reasoning model requests."""
    return os.getenv("DATACLOUD_LLM_API_KEY")


def resolve_reasoning_base_url() -> str | None:
    """Resolve base URL fallback chain for reasoning model requests."""
    return os.getenv("DATACLOUD_LLM_API_BASE")


def resolve_reasoning_provider() -> str:
    """Resolve the LLM provider from ``DATACLOUD_LLM_MODEL_PROVIDER``.

    返回值为 ``openai``（默认）或 ``anthropic``。
    请使用此变量指定协议，不要在 ``DATACLOUD_LLM_MODEL`` 中使用前缀写法。
    """
    return os.getenv("DATACLOUD_LLM_MODEL_PROVIDER", "openai").strip().lower()
