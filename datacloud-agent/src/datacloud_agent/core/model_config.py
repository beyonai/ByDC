"""Model configuration module.

Provides functions for creating and configuring LLM models.
"""

import os
from typing import Any

from langchain_openai import ChatOpenAI


def get_default_model_config() -> dict[str, Any]:
    """Get the default model configuration.

    Returns:
        dict: Default configuration with model, api_key, and base_url.
    """
    return {
        "model": "openai:qwen3.5-plus",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL"),
    }


def create_model(config: dict[str, Any] | None = None) -> ChatOpenAI:
    """Create a model instance using the provided configuration.

    Args:
        config: Optional configuration dictionary. If None, uses environment
                variables as defaults.

    Returns:
        ChatOpenAI: Initialized model instance.

    Raises:
        ValueError: If API key is missing from config or environment variables.
    """
    if config is None:
        config = {}

    model_name = config.get("model", "openai:qwen3.5-plus")
    api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
    base_url = config.get("base_url") or os.getenv("OPENAI_BASE_URL")

    if not api_key:
        raise ValueError("API key is required. Set OPENAI_API_KEY environment variable.")

    model = ChatOpenAI(
        model=model_name,
        api_key=api_key,  # type: ignore[arg-type]
        base_url=base_url,
        temperature=0,
    )

    return model
