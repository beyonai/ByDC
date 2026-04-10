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
    mounted_objects: list[str] | None = None,
    loader: Any | None = None,
) -> Any:
    """Create a deep agent for DataCloud, usable with langgraph dev and deep-agents-ui.

    Args:
        tools: 调用方预构建的工具字典，key 为工具名，value 为可调用对象或 BaseTool。
        mounted_objects: OBJECT / VIEW / ONTOLOGY 编码列表。若提供，则通过
            ``OntologyToolLoader`` 从本体定义自动生成 query_{code} /
            compute_{code} / action 工具，再与 ``tools`` 合并（``tools``
            中同名工具优先，即调用方可覆盖自动生成的工具）。
        loader: ``datacloud_data_sdk.OntologyLoader`` 实例。``mounted_objects``
            非空时必须提供；未提供则跳过本体工具生成并记录 debug 日志。
    """

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

    # --- 本体工具生成 ---
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader  # noqa: PLC0415

    ontology_tools = OntologyToolLoader(
        mounted_objects=mounted_objects,
        loader=loader,
    ).load()

    # 合并工具：本体工具为基础，caller 传入的 tools 优先覆盖同名工具
    merged_tools: dict[str, Any] | None = {**ontology_tools, **(tools or {})} or None

    logger.info("create_agent: locale=%s (Custom StateGraph)", resolved_locale)
    logger.info(
        "create_agent: tools summary — "
        "ontology=%d extra=%d merged=%d mounted_objects=%s prompts_overwrite_keys=%s",
        len(ontology_tools),
        len(tools or {}),
        len(merged_tools or {}),
        mounted_objects,
        sorted((prompts_overwrite or {}).keys()),
    )

    graph = build_analysis_graph(
        prompts_overwrite=prompts_overwrite,
        tools=merged_tools,
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
