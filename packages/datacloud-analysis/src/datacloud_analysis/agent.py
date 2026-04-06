"""DataCloud deep agent — Deep Agents Architecture v2.

This module provides the agent factory using Deep Agents SDK.
Uses create_deep_agent() with middleware stack.

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
    mounted_objects: list[str] | None = None,  # 🆕 阶段2新增参数
) -> Any:
    """Create a deep agent for DataCloud using Deep Agents SDK.

    Args:
        model: LLM model name
        api_key: API key for LLM provider
        base_url: Base URL for LLM provider
        temperature: LLM temperature
        locale: Locale for agent (default: zh_CN)
        system_prompt: Custom system prompt
        prompts_overwrite: Prompt overrides from worker (优先级最高)
            - system_prompt: 覆盖默认 system prompt
            - task_prompt: 附加任务指导（将追加到 system_prompt）
        tools: Additional tools to register (阶段2后为 other_tools，不包含 OBJECT/VIEW)
        mounted_objects: 挂载的对象/视图列表（🆕 阶段2新增）

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

    # 优先级: prompts_overwrite['system_prompt'] > system_prompt > default
    final_system_prompt = system_prompt
    task_prompt = None

    if prompts_overwrite:
        if "system_prompt" in prompts_overwrite:
            final_system_prompt = prompts_overwrite["system_prompt"]
            logger.info("create_agent: using system_prompt from prompts_overwrite")
        if "task_prompt" in prompts_overwrite:
            task_prompt = prompts_overwrite["task_prompt"]
            logger.info("create_agent: using task_prompt from prompts_overwrite")

    return _create_deep_agent(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        locale=resolved_locale,
        system_prompt=final_system_prompt,  # 传递解析后的 system_prompt
        task_prompt=task_prompt,  # 新增参数
        tools=tools,
        mounted_objects=mounted_objects,  # 🆕 阶段2传递挂载对象
    )


def _create_deep_agent(
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.7,
    locale: str = "zh_CN",
    system_prompt: str | None = None,
    task_prompt: str | None = None,  # 新增
    tools: dict[str, Any] | None = None,
    mounted_objects: list[str] | None = None,  # 🆕 阶段2新增参数
) -> Any:
    """Create agent using Deep Agents SDK.

    Args:
        model: LLM model name
        api_key: API key
        base_url: Base URL
        temperature: Temperature
        locale: Locale
        system_prompt: System prompt (优先使用此参数)
        task_prompt: Additional task guidance (追加到 system_prompt)
        tools: Additional tools (阶段2后为 other_tools，不包含 OBJECT/VIEW)
        mounted_objects: 挂载的对象/视图列表（🆕 阶段2新增）

    Returns:
        Compiled agent

    Raises:
        ImportError: If deepagents is not installed
    """
    import pathlib  # noqa: PLC0415

    from deepagents import create_deep_agent  # noqa: PLC0415

    from datacloud_analysis.backend import create_datacloud_backend  # noqa: PLC0415
    from datacloud_analysis.context import DatacloudContext  # noqa: PLC0415
    from datacloud_analysis.middlewares import (  # noqa: PLC0415
        DatacloudOutputMiddleware,
        KnowledgeInjectionMiddleware,
        ToolCallLoggingMiddleware,
        WorkspaceInitMiddleware,
    )
    from datacloud_analysis.subagents import CODE_EXECUTOR_SUBAGENT  # noqa: PLC0415
    from datacloud_analysis.tools.registry import register_all_tools  # noqa: PLC0415

    logger.info("create_agent: Using Deep Agents SDK (locale=%s)", locale)

    # Register OQL tools (emit_result injected by DatacloudOutputMiddleware)
    all_tools = register_all_tools()
    if tools:
        # 阶段2后，tools 仅包含 other_tools (AGENT/FUNCTION等类型)
        # OBJECT/VIEW 类型通过 mounted_objects 传递给 KnowledgeInjectionMiddleware
        all_tools.extend(tools.values())

    # Build system prompt: default + custom + task_prompt
    final_system_prompt = system_prompt or _build_default_system_prompt(locale)

    if task_prompt:
        final_system_prompt = f"{final_system_prompt}\n\n# 任务处理指导\n{task_prompt}"
        logger.info("create_agent: appended task_prompt to system_prompt")

    # Workspace dir for backend
    workspace_dir = os.getcwd()

    # DatacloudBackend — limits file operations to workspace_dir
    backend = create_datacloud_backend(workspace_dir)

    # Built-in skills directory (SKILL.md 格式，随包发布)
    builtin_skills_dir = str(pathlib.Path(__file__).parent / "skills" / "builtin")
    skill_sources = [builtin_skills_dir]

    # Middleware stack (自定义中间件追加在 SDK 内置栈之后)
    middlewares = [
        KnowledgeInjectionMiddleware(mounted_objects=mounted_objects),  # 🆕 传递挂载对象
        ToolCallLoggingMiddleware(),  # 🆕 阶段4：工具调用推送
        DatacloudOutputMiddleware(),
        WorkspaceInitMiddleware(
            workspace_dir=workspace_dir,
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

    # 当 base_url 非空时（自定义 endpoint，如 Qwen/私有模型），预先构造 ChatOpenAI 实例，
    # 绕过 LangChain init_chat_model 的 provider 推断（不认识非标准模型名会报 ValueError）。
    # 使用标准模型名（claude-*、gpt-* 等）时沿用字符串，由 deepagents SDK 自行推断。
    resolved_model: Any
    if base_url:
        from langchain_openai import ChatOpenAI  # noqa: PLC0415

        resolved_model = ChatOpenAI(
            model=model or "gpt-4o",
            base_url=base_url,
            api_key=api_key or "sk-placeholder",
            temperature=temperature,
        )
        logger.info(
            "create_agent: using ChatOpenAI with custom base_url=%s model=%s",
            base_url,
            model,
        )
    else:
        resolved_model = model or "claude-sonnet-4-6"

    # Create compiled agent with Deep Agents SDK
    compiled = create_deep_agent(
        model=resolved_model,
        tools=all_tools,
        system_prompt=final_system_prompt,  # 使用构建后的完整 prompt
        middleware=middlewares,
        context_schema=DatacloudContext,
        backend=backend,
        skills=skill_sources,
        subagents=[CODE_EXECUTOR_SUBAGENT],
        checkpointer=checkpointer,
    )

    return compiled


def _build_default_system_prompt(locale: str) -> str:
    """Build default system prompt."""
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
