"""DataCloud deep agent for use with Deep Agents UI.

LLM config is read from environment variables (set in the app's .env file).
Hard-coded values below are only used as last-resort fallbacks so that
the module can be imported without any env vars (e.g. in unit tests).

Required env vars (loaded by langgraph dev via langgraph.json "env": ".env"):
    OPENAI_API_KEY             — API key for the LLM proxy
    OPENAI_BASE_URL            — Base URL for the LLM proxy
    DATACLOUD_LLM_REASONING_MODEL  — (optional) model name override
    DATACLOUD_AGENT_LOCALE     — (optional) zh_CN | en_US, default zh_CN
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain.agents import create_agent as _lc_create_agent
from langchain.chat_models import init_chat_model
from datacloud_agent.tools.data import data_query  # noqa: E402
from datacloud_agent.i18n import get_system_prompt, get_supported_locales

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 兼容不同版本的 langchain：set_verbose 在 0.1+ 才存在
try:
    from langchain.globals import set_verbose as _set_verbose
    _set_verbose(os.getenv("LANGCHAIN_VERBOSE", "").lower() in ("1", "true"))
except ImportError:
    pass



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
    locale: str | None = None,
    system_prompt: str | None = None,
) -> Any:
    """Create a deep agent for DataCloud, usable with langgraph dev and deep-agents-ui.

    Parameters are resolved in this order:
    1. Explicit argument (if provided)
    2. Environment variable
    3. Hard-coded fallback

    Args:
        model:         Model identifier, e.g. ``openai:Qwen/Qwen3-235B-A22B``.
        api_key:       API key; falls back to ``OPENAI_API_KEY`` env var.
        base_url:      Base URL; falls back to ``OPENAI_BASE_URL`` env var.
        temperature:   Sampling temperature.
        locale:        Language locale code (``zh_CN`` | ``en_US``).
                       Falls back to ``DATACLOUD_AGENT_LOCALE`` env var, then ``zh_CN``.
                       Supported locales: see ``get_supported_locales()``.
        system_prompt: Fully custom system prompt; if provided, overrides the
                       locale-based prompt entirely.

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

    # Resolve locale and warn if unsupported.
    resolved_locale = locale or os.getenv("DATACLOUD_AGENT_LOCALE", "zh_CN")
    supported = get_supported_locales()
    if resolved_locale not in supported:
        logger.warning(
            "create_agent: locale=%r is not supported (supported: %s). "
            "Falling back to zh_CN.",
            resolved_locale,
            supported,
        )
        resolved_locale = "zh_CN"

    logger.info(
        "create_agent: model=%s base_url=%s locale=%s",
        resolved_model, resolved_base_url, resolved_locale,
    )

    llm = init_chat_model(
        model=resolved_model,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        temperature=temperature,
        timeout=60,
        max_retries=1,
    )

    if system_prompt is None:
        system_prompt = get_system_prompt(resolved_locale)

    # Use langchain.agents.create_agent directly — bypasses deepagents SubAgentMiddleware
    # which injects TASK_SYSTEM_PROMPT ("use subagent for all tasks") that overrides our
    # intent and causes the general-purpose subagent to not receive data_query correctly.
    compiled = _lc_create_agent(
        llm,
        tools=[data_query],
        system_prompt=system_prompt,
    )

    # ── debug: list graph nodes to confirm ToolNode is in graph ───────────
    try:
        nodes = list(compiled.get_graph().nodes.keys())
        logger.info("[dbg] compiled graph nodes: %s", nodes)
    except Exception as _e:
        logger.warning("[dbg] get_graph failed: %s", _e)
    # ──────────────────────────────────────────────────────────────────────

    return compiled
