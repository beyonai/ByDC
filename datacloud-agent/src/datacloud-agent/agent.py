"""DataCloud deep agent for use with Deep Agents UI.

LLM config is read from environment variables (set in the app's .env file).
Hard-coded values below are only used as last-resort fallbacks so that
the module can be imported without any env vars (e.g. in unit tests).

Required env vars (loaded by langgraph dev via langgraph.json "env": ".env"):
    OPENAI_API_KEY    — API key for the LLM proxy
    OPENAI_BASE_URL   — Base URL for the LLM proxy
    DATACLOUD_LLM_REASONING_MODEL  — (optional) model name override
"""

import logging
import os
from typing import Any
from uuid import UUID

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


class _LLMLogger(BaseCallbackHandler):
    """Logs LLM call lifecycle at INFO level so issues are visible in console."""

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs: Any) -> None:
        run_id: UUID = kwargs.get("run_id")
        short_id = str(run_id)[:8] if run_id else "?"
        model = serialized.get("kwargs", {}).get("model_name") or serialized.get("name", "?")
        logger.info("[LLM] ▶ start   run=%s  model=%s  prompts=%d", short_id, model, len(prompts))

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        run_id: UUID = kwargs.get("run_id")
        short_id = str(run_id)[:8] if run_id else "?"
        logger.info("[LLM] ✓ finish  run=%s", short_id)

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        run_id: UUID = kwargs.get("run_id")
        short_id = str(run_id)[:8] if run_id else "?"
        logger.error("[LLM] ✗ error   run=%s  %s: %s", short_id, type(error).__name__, error)

# Fallback values — override via env vars in .env
_FALLBACK_MODEL = "openai:Qwen/Qwen3-235B-A22B"
_FALLBACK_API_KEY = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
_FALLBACK_BASE_URL = "https://lab.iwhalecloud.com/gpt-proxy/v1"


def create_agent(
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.7,
    system_prompt: str | None = None,
) -> Any:
    """Create a deep agent for DataCloud, usable with langgraph dev and deep-agents-ui.

    Parameters are resolved in this order:
    1. Explicit argument (if provided)
    2. Environment variable
    3. Hard-coded fallback

    Args:
        model:        Model identifier, e.g. ``openai:Qwen/Qwen3-235B-A22B``.
        api_key:      API key; falls back to ``OPENAI_API_KEY`` env var.
        base_url:     Base URL; falls back to ``OPENAI_BASE_URL`` env var.
        temperature:  Sampling temperature.
        system_prompt: Optional system prompt.

    Returns:
        A LangGraph-compilable deep agent.
    """
    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY") or _FALLBACK_API_KEY
    resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL") or _FALLBACK_BASE_URL
    resolved_model = (
        model
        or os.getenv("DATACLOUD_LLM_REASONING_MODEL")
        or _FALLBACK_MODEL
    )
    # Ensure the model identifier has the openai: provider prefix.
    if not resolved_model.startswith("openai:"):
        resolved_model = f"openai:{resolved_model}"

    logger.info(
        "create_agent: model=%s base_url=%s", resolved_model, resolved_base_url
    )

    llm = init_chat_model(
        model=resolved_model,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        temperature=temperature,
        callbacks=[_LLMLogger()],
    )

    if system_prompt is None:
        system_prompt = (
            "You are a helpful DataCloud assistant. "
            "You help users with data analysis and business insights. "
            "Be concise and accurate."
        )

    return create_deep_agent(
        model=llm,
        system_prompt=system_prompt,
    )
