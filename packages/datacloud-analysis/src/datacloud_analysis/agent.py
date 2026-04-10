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


def _drop_tools_named(tools: list[Any], *names: str) -> list[Any]:
    """Remove tools whose ``name`` is listed in ``names``.

    LangGraph ``ToolNode`` registers tools in order; a later tool with the same
    name overwrites an earlier one. ``create_agent`` passes
    ``middleware_tools + regular_tools``, so any ``emit_result`` in ontology or
    MCP tools would replace ``DatacloudOutputMiddleware``'s version (which
    accepts ``data`` as JSON string).

    Args:
        tools: Tools for ``create_deep_agent`` (typically ``BaseTool`` instances).
        names: Tool names to strip from this list.

    Returns:
        A new list without matching tools.
    """

    banned = frozenset(names)
    kept: list[Any] = []
    removed = 0
    for item in tools:
        if getattr(item, "name", None) in banned:
            removed += 1
            continue
        kept.append(item)
    if removed:
        logger.info(
            "create_agent: dropped %d tool(s) named {%s} so middleware-provided tools win",
            removed,
            ", ".join(sorted(banned)),
        )
    return kept


# ============================================================
# 内置系统提示词（固定部分，用户不可覆盖）
# ============================================================

_BUILTIN_SYSTEM_PROMPT_ZH = """
## 输出规则

使用 `emit_result` 工具输出最终结果：
- 完成分析或任务后，调用 `emit_result` 工具向用户展示最终结果
- 纯文本回复不能替代 `emit_result`，最终答案必须通过工具输出

## 任务追踪

使用 `todo` 工具管理多步骤任务：
- 当任务需要多个步骤时，先用 `todo` 分解任务，逐步执行并更新状态
- 简单的单步查询无需创建 todo 记录

## 文件读写规则

- 所有文件操作须限定在工作空间目录内
- 使用框架提供的文件工具进行读写，不要访问工作空间目录以外的路径

## 数据完整性

- 严禁编造数据，所有数据必须来自工具调用的真实返回结果
- 若查询无结果，如实告知用户，不要凭空补充数据
"""

_BUILTIN_SYSTEM_PROMPT_EN = """
## Output Rules

Use `emit_result` tool to output final results:
- After completing analysis or tasks, call `emit_result` to present the final result to the user
- Plain text replies cannot replace `emit_result`; final answers must be delivered through the tool

## Task Tracking

Use `todo` tool for multi-step task management:
- When tasks require multiple steps, use `todo` to break down tasks, execute step by step, and update status
- Simple single-step queries do not require a todo record

## File I/O Rules

- All file operations must be confined to the workspace directory
- Use the framework's file tools for reading/writing; do not access paths outside the workspace

## Data Integrity

- Never fabricate data; all data must come from real tool call results
- If a query returns no results, inform the user truthfully without adding made-up data
"""


def _build_system_prompt(
    agent_name: str,
    agent_desc: str,
    core_persona: str,
    locale: str,
) -> str:
    """Build the full system prompt: user-configurable identity + built-in logic.

    Args:
        agent_name: Agent display name (from resourceName)
        agent_desc: Agent description (from resourceDesc)
        core_persona: Core persona / behavior guidelines (from corePersonaDefinition)
        locale: Locale string, e.g. "zh_CN"

    Returns:
        Complete system prompt string
    """
    if locale == "zh_CN":
        parts: list[str] = []
        if agent_name:
            parts.append(f"你是 **{agent_name}**。")
        else:
            parts.append("你是 DataCloud Agent，一个专业的数据分析助手。")
        if agent_desc:
            parts.append(f"\n## 角色描述\n\n{agent_desc}")
        if core_persona:
            parts.append(f"\n## 人格定义\n\n{core_persona}")
        parts.append(_BUILTIN_SYSTEM_PROMPT_ZH)
        return "".join(parts)
    else:
        parts_en: list[str] = []
        if agent_name:
            parts_en.append(f"You are **{agent_name}**.")
        else:
            parts_en.append("You are DataCloud Agent, a professional data analysis assistant.")
        if agent_desc:
            parts_en.append(f"\n## Role Description\n\n{agent_desc}")
        if core_persona:
            parts_en.append(f"\n## Persona Definition\n\n{core_persona}")
        parts_en.append(_BUILTIN_SYSTEM_PROMPT_EN)
        return "".join(parts_en)


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
    # 🔍 打印 Worker 端传递的所有参数
    logger.info("=" * 80)
    logger.info("create_agent: WORKER INPUT PARAMETERS")
    logger.info("=" * 80)
    logger.info("create_agent: model=%s", model)
    logger.info("create_agent: api_key=%s", "***" if api_key else None)
    logger.info("create_agent: base_url=%s", base_url)
    logger.info("create_agent: temperature=%s", temperature)
    logger.info("create_agent: locale=%s", locale)
    logger.info(
        "create_agent: system_prompt=%s", f"<{len(system_prompt)} chars>" if system_prompt else None
    )

    # 打印 prompts_overwrite 详情
    if prompts_overwrite:
        logger.info("create_agent: prompts_overwrite keys=%s", list(prompts_overwrite.keys()))
        for key, value in prompts_overwrite.items():
            if isinstance(value, str):
                logger.info("create_agent:   - %s: <%d chars>", key, len(value))
            else:
                logger.info("create_agent:   - %s: %s", key, type(value).__name__)
    else:
        logger.info("create_agent: prompts_overwrite=None")

    # 打印 tools 详情
    if tools:
        logger.info("create_agent: tools keys=%s", list(tools.keys()))
        for tool_key, tool_value in tools.items():
            if isinstance(tool_value, dict):
                logger.info("create_agent:   - %s: %s", tool_key, tool_value)
            else:
                logger.info("create_agent:   - %s: %s", tool_key, type(tool_value).__name__)
    else:
        logger.info("create_agent: tools=None")

    # 打印 mounted_objects 详情
    logger.info("create_agent: mounted_objects=%s", mounted_objects)
    logger.info("=" * 80)

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

    # 优先级: prompts_overwrite > system_prompt 参数 > 空字符串
    # agent_name: 数字员工名称（resourceName）
    # agent_desc: 角色描述（resourceDesc / system_prompt 参数）
    # core_persona: 人格定义（corePersonaDefinition / task_prompt）
    agent_name = ""
    agent_desc = system_prompt or ""
    core_persona = ""

    if prompts_overwrite:
        if "agent_name" in prompts_overwrite:
            agent_name = prompts_overwrite["agent_name"] or ""
            logger.info("create_agent: using agent_name from prompts_overwrite")
        if "system_prompt" in prompts_overwrite:
            agent_desc = prompts_overwrite["system_prompt"] or ""
            logger.info("create_agent: using agent_desc (system_prompt) from prompts_overwrite")
        if "task_prompt" in prompts_overwrite:
            core_persona = prompts_overwrite["task_prompt"] or ""
            logger.info("create_agent: using core_persona (task_prompt) from prompts_overwrite")

    return _create_deep_agent(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        locale=resolved_locale,
        agent_name=agent_name,
        agent_desc=agent_desc,
        core_persona=core_persona,
        tools=tools,
        mounted_objects=mounted_objects,
    )


def _create_deep_agent(
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.7,
    locale: str = "zh_CN",
    agent_name: str = "",
    agent_desc: str = "",
    core_persona: str = "",
    tools: dict[str, Any] | None = None,
    mounted_objects: list[str] | None = None,
) -> Any:
    """Create agent using Deep Agents SDK.

    Args:
        model: LLM model name
        api_key: API key
        base_url: Base URL
        temperature: Temperature
        locale: Locale
        agent_name: Agent display name (from resourceName)
        agent_desc: Agent description (from resourceDesc)
        core_persona: Core persona / behavior guidelines (from corePersonaDefinition)
        tools: Additional tools (阶段2后为 other_tools，不包含 OBJECT/VIEW)
        mounted_objects: 挂载的对象/视图列表（🆕 阶段2新增）

    Returns:
        Compiled agent

    Raises:
        ImportError: If deepagents is not installed
    """
    import pathlib  # noqa: PLC0415

    from deepagents import create_deep_agent  # noqa: PLC0415
    from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT  # noqa: PLC0415

    from datacloud_analysis.backend import create_datacloud_backend  # noqa: PLC0415
    from datacloud_analysis.config.env import Settings  # noqa: PLC0415
    from datacloud_analysis.context import DatacloudContext  # noqa: PLC0415
    from datacloud_analysis.middlewares import (  # noqa: PLC0415
        DatacloudOutputMiddleware,
        KnowledgeInjectionMiddleware,
        ToolCallLoggingMiddleware,
        WorkspaceInitMiddleware,
    )
    from datacloud_analysis.subagents import CODE_EXECUTOR_SUBAGENT  # noqa: PLC0415
    from datacloud_analysis.tools.ontology_loader import create_ontology_loader  # noqa: PLC0415

    logger.info("create_agent: Using Deep Agents SDK (locale=%s)", locale)

    # 🆕 根据环境变量选择本体加载模式
    try:
        settings = Settings()
        ontology_config = settings.ontology
        load_mode = ontology_config.load_mode if ontology_config else "unified_interface"
        mcp_endpoint = ontology_config.mcp_endpoint if ontology_config else ""
        scene_path = ontology_config.scene_path if ontology_config else ""
        auto_register = ontology_config.auto_register if ontology_config else True
    except Exception as e:
        logger.warning("create_agent: failed to load ontology settings: %s, using defaults", e)
        load_mode = "unified_interface"
        mcp_endpoint = ""
        scene_path = ""
        auto_register = True

    logger.info("create_agent: ontology load_mode=%s", load_mode)

    # 使用本体加载器加载工具
    ontology_loader = create_ontology_loader(
        load_mode=load_mode,
        mcp_endpoint=mcp_endpoint,
        scene_path=scene_path,
        auto_register=auto_register,
    )
    all_tools = ontology_loader.load_tools(mounted_objects=mounted_objects)

    if tools:
        # 阶段2后，tools 仅包含 other_tools (AGENT/FUNCTION等类型)
        # OBJECT/VIEW 类型通过 mounted_objects 传递给本体加载器
        all_tools.extend(tools.values())

    all_tools = _drop_tools_named(all_tools, "emit_result")

    # Build system prompt: user-configurable identity + built-in logic
    final_system_prompt = _build_system_prompt(
        agent_name=agent_name,
        agent_desc=agent_desc,
        core_persona=core_persona,
        locale=locale,
    )
    logger.info(
        "create_agent: built system_prompt <%d chars> (agent_name=%r)",
        len(final_system_prompt),
        agent_name,
    )

    # Workspace dir for backend
    workspace_dir = os.getcwd()

    # DatacloudBackend — limits file operations to workspace_dir
    backend = create_datacloud_backend(workspace_dir)

    # Built-in skills directory (SKILL.md 格式，随包发布)
    # 优先级：1. 工作目录内的skills/builtin  2. 包内的skills/builtin
    skill_sources = []
    workspace_path = pathlib.Path(workspace_dir).resolve()

    # 优先尝试工作目录内的技能
    workspace_skills_dir = workspace_path / "skills" / "builtin"
    if workspace_skills_dir.exists() and workspace_skills_dir.is_dir():
        skill_sources = [str(workspace_skills_dir)]
        logger.info("create_agent: using skills from workspace: %s", workspace_skills_dir)
    else:
        # 回退到包内技能（仅当在工作目录内时）
        builtin_skills_dir = pathlib.Path(__file__).parent / "skills" / "builtin"
        try:
            builtin_path = builtin_skills_dir.resolve()
            # 尝试计算相对路径，如果成功说明在工作目录内
            builtin_path.relative_to(workspace_path)
            skill_sources = [str(builtin_skills_dir)]
            logger.info("create_agent: using builtin skills from package: %s", builtin_skills_dir)
        except (ValueError, OSError):
            # 技能目录不在工作目录内，跳过
            logger.info("create_agent: no skills directory found (checked workspace and package)")

    # Middleware stack (自定义中间件追加在 SDK 内置栈之后)
    logger.info("create_agent: initializing middlewares with mounted_objects=%s", mounted_objects)
    middlewares = [
        KnowledgeInjectionMiddleware(mounted_objects=mounted_objects),  # 🆕 传递挂载对象
        ToolCallLoggingMiddleware(),  # 🆕 阶段4：工具调用推送
        DatacloudOutputMiddleware(),
        WorkspaceInitMiddleware(
            workspace_dir=workspace_dir,
            agent_name=agent_name or "DataCloud Agent",
        ),
    ]
    logger.info("create_agent: middlewares initialized count=%d", len(middlewares))

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
        subagents=[
            {
                **GENERAL_PURPOSE_SUBAGENT,
                "middleware": [DatacloudOutputMiddleware()],
            },
            {
                **CODE_EXECUTOR_SUBAGENT,
                "middleware": [DatacloudOutputMiddleware()],
            },
        ],
        checkpointer=checkpointer,
    )

    return compiled
