"""DataCloud deep agent — core graph factory.

Persistence (checkpointing) is handled externally:
- langgraph dev: injected by the platform via ``langgraph.json`` / ``checkpointer.py``
  which references ``datacloud_analysis.session.pg_opengauss.get_checkpointer``.
- Standalone SDK: call ``create_agent()`` then compile with your own checkpointer,
  or use ``datacloud_analysis.session.pg_opengauss.make_opengauss_saver`` directly.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from datacloud_analysis.i18n import get_supported_locales
from datacloud_analysis.orchestration.graph_builder import build_analysis_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_agent(
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.7,
    locale: str | None = None,
    system_prompt: str | None = None,
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
) -> Any:
    """Create a deep agent for DataCloud, usable with langgraph dev and deep-agents-ui."""
    
    # 语言和环境的日志预警可以保留，这里为了兼容现有 SDK 初始化
    resolved_locale = locale or os.getenv("DATACLOUD_AGENT_LOCALE", "zh_CN")
    supported = get_supported_locales()
    if resolved_locale not in supported:
        logger.warning(
            "create_agent: locale=%r is not supported (supported: %s). Falling back to zh_CN.",
            resolved_locale,
            supported,
        )
        resolved_locale = "zh_CN"

    logger.info("create_agent: locale=%s (Custom StateGraph)", resolved_locale)

    graph = build_analysis_graph(
        prompts_overwrite=prompts_overwrite,
        tools=tools,
    )

    # Inject checkpointer if bootstrap.setup() has already been called;
    # fall back to compiling without checkpointing in standalone / test mode.
    try:
        from datacloud_analysis.session.checkpointer import get_checkpointer  # noqa: PLC0415

        compiled = graph.compile(checkpointer=get_checkpointer())
        logger.info("create_agent: compiled with PG checkpointer")
    except RuntimeError:
        compiled = graph.compile()
        logger.warning(
            "create_agent: checkpointer not initialized — compiling without checkpointing. "
            "Call `await bootstrap.setup()` before create_agent() to enable interrupt/resume."
        )

    try:
        nodes = list(compiled.get_graph().nodes.keys())
        logger.info("[dbg] compiled graph nodes: %s", nodes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[dbg] get_graph failed: %s", exc)

    return compiled
