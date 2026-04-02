"""Execution node — ReAct loop with tool dispatch and hook support."""
from __future__ import annotations
import inspect
import logging
import os
from typing import Any
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from datacloud_analysis.i18n.prompts import get_execution_prompt, get_system_prompt
from datacloud_analysis.orchestration.execution.react_loop import run_react_loop
from datacloud_analysis.orchestration.execution.tool_wrapper import inject_reason_field
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tools.ask_user import ask_user
from datacloud_analysis.tools.file_io import read_file, write_file
from datacloud_analysis.tools.code_exec import write_code, execute_code
from datacloud_analysis.workspace.runtime import resolve_shared_workspace_dir

logger = logging.getLogger(__name__)

_BUILTIN_TOOLS: list[BaseTool] = [
    ask_user,
    read_file,
    write_file,
    write_code,
    execute_code,
]

def _build_tools_list(default_tools: dict[str, Any] | None) -> list[BaseTool]:
    """Merge builtin tools with dynamically injected tools, inject reason field."""
    tools: list[BaseTool] = []

    # Builtin tools: ask_user skips reason injection (already has it)
    for t in _BUILTIN_TOOLS:
        if t.name == "ask_user":
            tools.append(t)
        else:
            tools.append(inject_reason_field(t))

    # Dynamic tools from agent config
    if default_tools:
        for name, callable_or_tool in default_tools.items():
            if isinstance(callable_or_tool, BaseTool):
                tools.append(inject_reason_field(callable_or_tool))
            elif callable(callable_or_tool):
                import asyncio  # noqa: PLC0415
                from langchain_core.tools import StructuredTool  # noqa: PLC0415
                is_async = asyncio.iscoroutinefunction(callable_or_tool)

                # 检查函数签名：如果是 **kwargs 或无明确参数，生成固定 schema
                sig = inspect.signature(callable_or_tool)
                params = list(sig.parameters.values())
                has_only_var_keyword = all(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in params
                ) if params else True

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
                tools.append(inject_reason_field(t))

    return tools

async def execution_node(
    state: AgentState,
    config: RunnableConfig,
    default_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute ReAct loop with tool dispatch and hook support."""
    locale = os.getenv("DATACLOUD_AGENT_LOCALE", "zh_CN")
    system_prompt = get_system_prompt(locale) + "\n\n" + get_execution_prompt(locale)

    tools_list = _build_tools_list(default_tools)
    max_rounds = int(os.getenv("DATACLOUD_REACT_MAX_ROUNDS", "10"))

    # 设置 workspace 环境变量供工具使用
    workspace_dir = state.get("workspace_dir")
    if workspace_dir:
        workspace_root = resolve_shared_workspace_dir(workspace_dir)
        if workspace_root is not None:
            os.environ["DATACLOUD_ACTIVE_WORKSPACE"] = str(workspace_root)

    logger.info(
        "[execution_node] tools=%s max_rounds=%d",
        [t.name for t in tools_list],
        max_rounds,
    )

    result = await run_react_loop(
        state=state,
        tools_list=tools_list,
        system_prompt=system_prompt,
        max_rounds=max_rounds,
        gateway_context=(config.get("configurable") or {}).get("gateway_context"),
    )

    return result
