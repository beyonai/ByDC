"""DataCloud deep agent — Deep Agents Architecture v2.

This module provides the agent factory using Deep Agents SDK.
When deepagents is available, it uses create_deep_agent() with middleware stack.
Otherwise, it falls back to the legacy StateGraph implementation.

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
    """Create a deep agent for DataCloud.

    This function attempts to use Deep Agents SDK if available,
    otherwise falls back to the legacy StateGraph implementation.

    Args:
        model: LLM model name
        api_key: API key for LLM provider
        base_url: Base URL for LLM provider
        temperature: LLM temperature
        locale: Locale for agent (default: zh_CN)
        system_prompt: Custom system prompt
        prompts_overwrite: Prompt overrides
        tools: Additional tools to register

    Returns:
        Compiled agent graph
    """
    # Resolve locale
    resolved_locale = locale or os.getenv("DATACLOUD_AGENT_LOCALE", "zh_CN")
    supported = get_supported_locales()
    if resolved_locale not in supported:
        logger.warning(
            "create_agent: locale=%r is not supported (supported: %s). Falling back to zh_CN.",
            resolved_locale,
            supported,
        )
        resolved_locale = "zh_CN"

    # Try to use Deep Agents SDK
    try:
        return _create_deep_agent(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            locale=resolved_locale,
            system_prompt=system_prompt,
            prompts_overwrite=prompts_overwrite,
            tools=tools,
        )
    except ImportError:
        logger.warning(
            "Deep Agents SDK not available, falling back to legacy StateGraph implementation"
        )
        return _create_legacy_agent(
            locale=resolved_locale,
            prompts_overwrite=prompts_overwrite,
            tools=tools,
        )


def _create_deep_agent(
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.7,
    locale: str = "zh_CN",
    system_prompt: str | None = None,
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
) -> Any:
    """Create agent using Deep Agents SDK.

    Args:
        model: LLM model name
        api_key: API key
        base_url: Base URL
        temperature: Temperature
        locale: Locale
        system_prompt: System prompt
        prompts_overwrite: Prompt overrides
        tools: Additional tools

    Returns:
        Compiled agent

    Raises:
        ImportError: If deepagents is not installed
    """
    from deepagents import create_deep_agent  # noqa: PLC0415

    from datacloud_analysis.middlewares import (  # noqa: PLC0415
        DatacloudOutputMiddleware,
        KnowledgeInjectionMiddleware,
        WorkspaceInitMiddleware,
    )
    from datacloud_analysis.tools.registry import register_all_tools  # noqa: PLC0415

    logger.info("create_agent: Using Deep Agents SDK (locale=%s)", locale)

    # Register all tools
    all_tools = register_all_tools()
    if tools:
        # Merge additional tools
        all_tools.extend(tools.values())

    # Build system prompt
    final_system_prompt = system_prompt or _build_default_system_prompt(locale)

    # Create middleware stack
    middlewares = [
        KnowledgeInjectionMiddleware(),
        DatacloudOutputMiddleware(),
        WorkspaceInitMiddleware(
            workspace_dir=os.getcwd(),
            agent_name="DataCloud Agent",
        ),
    ]

    # Resolve checkpointer
    checkpointer: Any = None
    try:
        from datacloud_analysis.session.checkpointer import get_checkpointer  # noqa: PLC0415

        checkpointer = get_checkpointer()
        logger.info("create_agent: using PG checkpointer")
    except RuntimeError:
        logger.warning(
            "create_agent: checkpointer not initialized — running without checkpointing. "
            "Call `await bootstrap.setup()` before create_agent() to enable interrupt/resume."
        )

    # Create compiled agent with Deep Agents SDK
    compiled = create_deep_agent(
        model=model or "claude-sonnet-4-6",
        tools=all_tools,
        system_prompt=final_system_prompt,
        middleware=middlewares,
        checkpointer=checkpointer,
    )

    return compiled


def _create_legacy_agent(
    *,
    locale: str = "zh_CN",
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
) -> Any:
    """Create agent using legacy StateGraph implementation.

    Args:
        locale: Locale
        prompts_overwrite: Prompt overrides
        tools: Additional tools

    Returns:
        Compiled agent
    """
    from datacloud_analysis.orchestration.graph_builder import build_analysis_graph  # noqa: PLC0415

    logger.info("create_agent: Using legacy StateGraph (locale=%s)", locale)
    logger.info(
        "create_agent: injecting tools into graph closure count=%d keys=%s",
        len(tools or {}),
        sorted((tools or {}).keys()),
    )

    graph = build_analysis_graph(
        prompts_overwrite=prompts_overwrite,
        tools=tools,
    )

    # Inject checkpointer if available
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


def _build_default_system_prompt(locale: str) -> str:
    """Build default system prompt.

    Args:
        locale: Locale

    Returns:
        System prompt
    """
    if locale == "zh_CN":
        return """你是 DataCloud Agent，一个专业的数据分析助手。

你的职责：
1. 理解用户的数据分析需求
2. 使用 query_objects 工具查询本体对象数据
3. 使用 execute_action 工具执行业务动作
4. 提供清晰、准确的分析结果

重要规则：
- 所有数据查询必须通过 query_objects 工具
- 所有写操作必须通过 execute_action 工具
- 不要编造数据，只使用工具返回的真实数据
- 使用 emit_result 工具输出最终结果
"""
    else:
        return """You are DataCloud Agent, a professional data analysis assistant.

Your responsibilities:
1. Understand user's data analysis requirements
2. Use query_objects tool to query ontology object data
3. Use execute_action tool to execute business actions
4. Provide clear and accurate analysis results

Important rules:
- All data queries must go through query_objects tool
- All write operations must go through execute_action tool
- Don't fabricate data, only use real data returned by tools
- Use emit_result tool to output final results
"""
