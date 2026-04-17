"""Execution node — ReAct loop with tool dispatch and hook support."""

from __future__ import annotations

import inspect
import logging
import os
from datetime import datetime
from typing import Any, List

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from datacloud_analysis.i18n.prompts import get_execution_prompt, get_system_prompt
from datacloud_analysis.orchestration.execution.react_loop import run_react_loop
from datacloud_analysis.orchestration.execution.tool_wrapper import (
    inject_reason_field,
    is_delegate_wait_resume_command,
)
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tools.ask_user import ask_user
from datacloud_analysis.tools.file_io import read_file

logger = logging.getLogger(__name__)

# ── 数据工具识别 ─────────────────────────────────────────────────────────────
_DATA_TOOL_PREFIXES = ("query_", "compute_", "data_query_")

# ── 禁止挂载的工具名（黑名单）────────────────────────────────────────────────
_BLOCKED_TOOL_NAMES: frozenset[str] = frozenset({"write_code", "execute_code"})


def _is_data_tool_name(name: str) -> bool:
    """判断工具名是否属于数据类工具（query_/compute_/data_query_ 前缀）。"""
    return any(name.startswith(p) for p in _DATA_TOOL_PREFIXES)


def inject_ambiguity_fields(t: BaseTool) -> BaseTool:
    """往数据类工具 Schema 注入三个元字段，由 LLM 在调用时填写，执行前自动剥除。

    注入字段：
    - intent_reason: str        — LLM 对本次查询意图的完整理解描述
    - extraction_confidence: float — LLM 对参数提取正确性的自信度 [0.0, 1.0]
    - ambiguous_params: List[str]  — LLM 认为有歧义/不确定的参数名列表

    底层 coroutine 不会收到这三个字段（调用前自动剥除）。
    """
    try:
        from pydantic import Field, create_model  # noqa: PLC0415

        original_schema = t.args_schema
        if original_schema is None:
            return t

        NewSchema = create_model(
            f"{original_schema.__name__}WithAmbiguity",
            __base__=original_schema,
            intent_reason=(
                str,
                Field(
                    default="",
                    description=(
                        "你对用户本次查询意图的完整理解描述。"
                        "请用一句话说明用户真正想查什么、时间范围、分组维度等关键要素。"
                    ),
                ),
            ),
            extraction_confidence=(
                float,
                Field(
                    default=1.0,
                    ge=0.0,
                    le=1.0,
                    description=(
                        "你对本次参数提取正确性的自信度，范围 [0.0, 1.0]。"
                        "若字段名、时间范围、过滤条件等存在不确定性，请填写较低值（如 0.6~0.8）。"
                    ),
                ),
            ),
            ambiguous_params=(
                List[str],
                Field(
                    default_factory=list,
                    description=(
                        "你认为存在歧义或不确定的参数名列表（如 [\"time_range\", \"target_object\"]）。"
                        "若所有参数均已明确，填写空列表 []。"
                    ),
                ),
            ),
        )
        t.args_schema = NewSchema

        # 包装 coroutine：调用前剥除三个元字段
        if hasattr(t, "coroutine") and t.coroutine is not None:
            _orig_coro = t.coroutine

            async def _coro_strip_ambiguity(**kw: Any) -> Any:
                kw.pop("intent_reason", None)
                kw.pop("extraction_confidence", None)
                kw.pop("ambiguous_params", None)
                return await _orig_coro(**kw)

            t.coroutine = _coro_strip_ambiguity

        # 包装 func（同步工具）
        if hasattr(t, "func") and t.func is not None:
            _orig_func = t.func

            def _func_strip_ambiguity(**kw: Any) -> Any:
                kw.pop("intent_reason", None)
                kw.pop("extraction_confidence", None)
                kw.pop("ambiguous_params", None)
                return _orig_func(**kw)

            t.func = _func_strip_ambiguity

    except Exception as exc:  # pragma: no cover
        logger.warning("[inject_ambiguity_fields] failed for tool=%s: %s", getattr(t, "name", "?"), exc)

    return t

# Set to 1/true/yes to omit ask_user from the execution agent (e.g. local debugging).
_DISABLE_ASK_USER_TOOL = os.environ.get("DATACLOUD_DISABLE_ASK_USER_TOOL", "1").lower() in (
    "1",
    "true",
    "yes",
)

_EXECUTION_REASONING_TITLE = "任务执行"

_BUILTIN_TOOLS: list[BaseTool] = [
    ask_user,
    read_file,
]


def _resolve_runtime_context_param(source: Any) -> str | None:
    """Return the supported runtime context parameter name for a tool callable."""
    try:
        sig = inspect.signature(source)
    except (TypeError, ValueError):
        return None

    for candidate in ("_context", "gateway_context"):
        if candidate in sig.parameters:
            return candidate
    return None


def _build_tools_list(default_tools: dict[str, Any] | None) -> list[BaseTool]:
    """Merge builtin tools with dynamically injected tools, inject reason field."""
    tools: list[BaseTool] = []

    # Builtin tools: ask_user skips reason injection (already has it)
    for t in _BUILTIN_TOOLS:
        if t.name == "ask_user" and _DISABLE_ASK_USER_TOOL:
            logger.info("ask_user omitted from execution tools (DATACLOUD_DISABLE_ASK_USER_TOOL)")
            continue
        if t.name == "ask_user":
            tools.append(t)
        else:
            # 在 inject_reason_field 之前检测签名，因为 inject_reason_field 会替换 coroutine
            # 导致原始 _context 参数签名消失
            runtime_context_param = _resolve_runtime_context_param(
                getattr(t, "coroutine", None)
            ) or _resolve_runtime_context_param(getattr(t, "func", None))
            tool = inject_reason_field(t)
            if runtime_context_param:
                tool._datacloud_runtime_context_param = runtime_context_param
            tools.append(tool)

    # Dynamic tools from agent config
    if default_tools:
        for name, callable_or_tool in default_tools.items():
            if name in _BLOCKED_TOOL_NAMES:
                logger.info("tool %r skipped (blocked by _BLOCKED_TOOL_NAMES)", name)
                continue
            if isinstance(callable_or_tool, BaseTool):
                runtime_context_param = _resolve_runtime_context_param(
                    getattr(callable_or_tool, "coroutine", None)
                ) or _resolve_runtime_context_param(getattr(callable_or_tool, "func", None))
                tool = inject_reason_field(callable_or_tool)
                # 数据类工具：注入歧义元字段（在 inject_reason_field 之后）
                if _is_data_tool_name(name):
                    tool = inject_ambiguity_fields(tool)
                if runtime_context_param:
                    tool._datacloud_runtime_context_param = runtime_context_param
                tools.append(tool)
            elif callable(callable_or_tool):
                import asyncio  # noqa: PLC0415

                from langchain_core.tools import StructuredTool  # noqa: PLC0415

                is_async = asyncio.iscoroutinefunction(callable_or_tool)
                runtime_context_param = _resolve_runtime_context_param(callable_or_tool)

                # 检查函数签名：如果是 **kwargs 或无明确参数，生成固定 schema
                sig = inspect.signature(callable_or_tool)
                params = list(sig.parameters.values())
                has_only_var_keyword = (
                    all(p.kind == inspect.Parameter.VAR_KEYWORD for p in params) if params else True
                )

                if has_only_var_keyword:
                    # **kwargs 工具：生成明确的 query: str schema，避免 LLM 产生嵌套参数
                    from pydantic import BaseModel, Field  # noqa: PLC0415

                    class _QuerySchema(BaseModel):
                        query: str = Field(description="完整的自然语言查询问题")

                    t = StructuredTool.from_function(
                        func=callable_or_tool if not is_async else None,
                        name=name,
                        description=getattr(callable_or_tool, "__doc__", name) or name,
                        coroutine=callable_or_tool if is_async else None,
                        args_schema=_QuerySchema,
                    )
                else:
                    t = StructuredTool.from_function(
                        func=callable_or_tool if not is_async else None,
                        name=name,
                        description=getattr(callable_or_tool, "__doc__", name) or name,
                        coroutine=callable_or_tool if is_async else None,
                    )
                tool = inject_reason_field(t)
                # 数据类工具：注入歧义元字段（在 inject_reason_field 之后）
                if _is_data_tool_name(name):
                    tool = inject_ambiguity_fields(tool)
                if runtime_context_param:
                    tool._datacloud_runtime_context_param = runtime_context_param
                if getattr(callable_or_tool, "_is_agent_delegate", False):
                    tool._is_agent_delegate = True
                tools.append(tool)

    return tools


async def execution_node(
    state: AgentState,
    config: RunnableConfig,
    default_tools: dict[str, Any] | None = None,
    prompts_overwrite: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute ReAct loop with tool dispatch and hook support."""
    locale = os.getenv("DATACLOUD_AGENT_LOCALE", "zh_CN")

    # 基础 prompt：系统角色 + 执行规则
    base_system = get_system_prompt(locale)
    base_execution = get_execution_prompt(locale)

    # 消费 prompts_overwrite：
    # - system_prompt 替换基础系统角色描述
    # - task_prompt   附加在执行规则之后（业务角色/流程说明等）
    overwrite = prompts_overwrite or {}
    custom_system = str(overwrite.get("system_prompt") or "").strip()
    custom_task = str(overwrite.get("task_prompt") or "").strip()

    system_parts = [custom_system if custom_system else base_system, base_execution]
    if custom_task:
        system_parts.append(custom_task)
    # stable_system_prompt：稳定部分，用于 Prompt Caching 的缓存前缀
    stable_system_prompt = "\n\n".join(p for p in system_parts if p)
    system_prompt = stable_system_prompt

    # 层 A：知识增强注入（knowledge_snippets 由 intend_node 写入，格式已经是可读文本）
    knowledge_snippets = state.get("knowledge_snippets") or []
    dynamic_parts: list[str] = []
    if knowledge_snippets:
        knowledge_section = "\n\n## 数据查询知识增强\n" + "\n".join(
            s if isinstance(s, str) else str(s) for s in knowledge_snippets
        )
        dynamic_parts.append(knowledge_section)

    # 层 B：运行时会话信息（用户 + 当前时间）——放最末尾，不破坏前缀缓存
    # 从 gateway_context.current_command.header.metadata 取用户信息，无需 worker.py 传参
    _gateway_context_for_meta = (config.get("configurable") or {}).get("gateway_context")
    try:
        _header_meta: dict = _gateway_context_for_meta.current_command.header.metadata or {}
    except AttributeError:
        _header_meta = {}
    _user_code = str(_header_meta.get("user_code") or "").strip()
    _user_name = str(_header_meta.get("user_name") or "").strip()
    _now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    _runtime_lines = ["\n\n## 当前会话信息", f"- 当前时间：{_now_str}"]
    if _user_name and _user_code:
        _runtime_lines.append(f"- 当前用户：{_user_name}（工号：{_user_code}）")
    elif _user_name:
        _runtime_lines.append(f"- 当前用户：{_user_name}")
    elif _user_code:
        _runtime_lines.append(f"- 当前用户工号：{_user_code}")
    dynamic_parts.append("\n".join(_runtime_lines))

    # 拼接完整 system_prompt（用于不支持 cache_control 的回退路径）
    dynamic_prompt = "".join(dynamic_parts)
    system_prompt = stable_system_prompt + dynamic_prompt

    tools_list = _build_tools_list(default_tools)
    max_rounds = int(os.getenv("DATACLOUD_REACT_MAX_ROUNDS", "10"))

    logger.info(
        "[execution_node] tools=%s max_rounds=%d",
        [t.name for t in tools_list],
        max_rounds,
    )

    gateway_context = (config.get("configurable") or {}).get("gateway_context")
    if gateway_context is not None:
        is_delegate_resume_replay = is_delegate_wait_resume_command(
            getattr(gateway_context, "current_command", None)
        )
        gateway_context._datacloud_skip_delegate_resume_replay_output = is_delegate_resume_replay
        if not is_delegate_resume_replay:
            result = await run_react_loop(
                state=state,
                tools_list=tools_list,
                system_prompt=system_prompt,
                stable_system_prompt=stable_system_prompt,
                dynamic_prompt=dynamic_prompt,
                max_rounds=max_rounds,
                gateway_context=gateway_context,
            )
        else:
            result = await run_react_loop(
                state=state,
                tools_list=tools_list,
                system_prompt=system_prompt,
                stable_system_prompt=stable_system_prompt,
                dynamic_prompt=dynamic_prompt,
                max_rounds=max_rounds,
                gateway_context=gateway_context,
            )
    else:
        result = await run_react_loop(
            state=state,
            tools_list=tools_list,
            system_prompt=system_prompt,
            stable_system_prompt=stable_system_prompt,
            dynamic_prompt=dynamic_prompt,
            max_rounds=max_rounds,
            gateway_context=gateway_context,
        )

    return result
