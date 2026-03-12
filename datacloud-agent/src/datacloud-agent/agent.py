"""DataCloud deep agent — core graph factory.

Persistence (checkpointing) is handled externally:
- langgraph dev: injected by the platform via ``langgraph.json`` / ``checkpointer.py``
  which references ``datacloud_agent.session.pg_opengauss.get_checkpointer``.
- Standalone SDK: call ``create_agent()`` then compile with your own checkpointer,
  or use ``datacloud_agent.session.pg_opengauss.make_opengauss_saver`` directly.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from datacloud_agent.i18n import get_supported_locales, get_system_prompt
from datacloud_agent.tools.data import data_query
from langchain.agents import create_agent as _lc_create_agent
from langchain.chat_models import init_chat_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from langchain.globals import set_verbose as _set_verbose

    _set_verbose(os.getenv("LANGCHAIN_VERBOSE", "").lower() in ("1", "true"))
except ImportError:
    pass


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
    """Create a deep agent for DataCloud, usable with langgraph dev and deep-agents-ui."""
    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY") or _FALLBACK_API_KEY
    resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL") or _FALLBACK_BASE_URL
    resolved_model = model or os.getenv("DATACLOUD_LLM_REASONING_MODEL") or _FALLBACK_MODEL
    if not resolved_model.startswith("openai:"):
        resolved_model = f"openai:{resolved_model}"

    resolved_locale = locale or os.getenv("DATACLOUD_AGENT_LOCALE", "zh_CN")
    supported = get_supported_locales()
    if resolved_locale not in supported:
        logger.warning(
            "create_agent: locale=%r is not supported (supported: %s). Falling back to zh_CN.",
            resolved_locale,
            supported,
        )
        resolved_locale = "zh_CN"

    logger.info(
        "create_agent: model=%s base_url=%s locale=%s",
        resolved_model,
        resolved_base_url,
        resolved_locale,
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

    compiled = _lc_create_agent(
        llm,
        tools=[data_query],
        system_prompt=system_prompt,
    )

    try:
        nodes = list(compiled.get_graph().nodes.keys())
        logger.info("[dbg] compiled graph nodes: %s", nodes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[dbg] get_graph failed: %s", exc)

    return compiled
