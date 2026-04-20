"""Assemble the DataCloud analysis StateGraph.

V0.3 architecture: intend → llm_call → (Send) per-tool-node → llm_call → ... → finish_react → respond
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any, cast

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from datacloud_analysis.i18n.prompts import get_execution_prompt, get_system_prompt
from datacloud_analysis.orchestration.clarification.analyze_clarify_node import (
    analyze_clarify_node,
)
from datacloud_analysis.orchestration.clarification.user_clarify_node import user_clarify_node
from datacloud_analysis.orchestration.execution.finish_react_node import finish_react_node
from datacloud_analysis.orchestration.execution.llm_call_node import make_llm_call_node
from datacloud_analysis.orchestration.execution.make_tool_node import make_tool_node
from datacloud_analysis.orchestration.execution.node import _build_tools_list
from datacloud_analysis.orchestration.execution.tool_dispatcher_node import (
    make_tool_dispatcher_node,
)
from datacloud_analysis.orchestration.intend.node import intend_node
from datacloud_analysis.orchestration.respond.node import respond_node
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


def _route_after_intend(state: AgentState) -> str:
    status = str(state.get("execution_status") or "llm_call")
    if status == "command_done":
        return "command_done"
    return "llm_call"


def _route_after_tool_node(state: AgentState) -> str:
    """Per-tool 节点执行后的路由：澄清 → analyze_clarify；否则回到 llm_call。"""
    status = str(state.get("execution_status") or "")
    if status == "clarify_needed":
        return "analyze_clarify"
    return "llm_call"


def _route_after_tool_dispatcher(state: AgentState) -> str:
    status = str(state.get("execution_status") or "")
    if status == "finish_react":
        return "finish_react"
    if status == "clarify_needed":
        return "analyze_clarify"
    return "llm_call"


def _route_after_analyze(state: AgentState) -> str:
    analyze_result = state.get("clarification_analyze_result") or {}
    paradigm_list = list(analyze_result.get("paradigm_list") or [])
    if paradigm_list:
        return "user_clarify"
    return "tool_dispatcher"


def _make_per_tool_wrapper(
    fn: Callable[..., Any],
    name: str,
    as_state_update: Callable[[Any, str], dict[str, Any]],
) -> Callable[[AgentState, RunnableConfig], Any]:
    """工厂：为每个工具节点创建包装闭包，捕获 fn / name 避免循环变量泄漏。"""

    async def _wrapper(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await fn(state, config)
        return as_state_update(result, name)

    return _wrapper


def _as_state_update(value: object, *, node_name: str) -> dict[str, Any]:
    """Normalize node output into a concrete state update mapping."""
    if isinstance(value, Mapping):
        return dict(cast(Mapping[str, Any], value))
    msg = f"{node_name} node must return a mapping, got {type(value).__name__}"
    raise TypeError(msg)


def build_analysis_graph(
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
    knowledge_enhancer: Callable[..., Any] | None = None,
    loader: Any = None,
    redirect_tools: dict[str, Any] | None = None,
) -> StateGraph[AgentState]:
    """Return an uncompiled StateGraph for the DataCloud V0.3 pipeline."""
    builder = StateGraph(AgentState)

    # ── 构建 system prompt（stable 部分，供 Prompt Caching）──────────────────────
    locale = os.getenv("DATACLOUD_AGENT_LOCALE", "zh_CN")
    overwrite = prompts_overwrite or {}
    custom_system = str(overwrite.get("system_prompt") or "").strip()
    custom_task = str(overwrite.get("task_prompt") or "").strip()
    base_system = get_system_prompt(locale)
    base_execution = get_execution_prompt(locale)
    system_parts = [custom_system if custom_system else base_system, base_execution]
    if custom_task:
        system_parts.append(custom_task)
    stable_system_prompt = "\n\n".join(p for p in system_parts if p)

    # ── 构建 tools_list ──────────────────────────────────────────────────────────
    tools_list = _build_tools_list(tools)

    # ── redirect_tools_map ───────────────────────────────────────────────────────
    from langchain_core.tools import BaseTool  # noqa: PLC0415

    redirect_tools_map: dict[str, BaseTool] | None = None
    if redirect_tools:
        redirect_tools_map = {
            name: t for name, t in redirect_tools.items() if isinstance(t, BaseTool)
        }

    # ── 构建 per-tool 节点名集合（用于路由）──────────────────────────────────────
    _tool_node_names: frozenset[str] = frozenset(t.name for t in tools_list)

    # ── 创建节点闭包 ─────────────────────────────────────────────────────────────
    llm_call_fn = make_llm_call_node(
        tools_list=tools_list,
        system_prompt=stable_system_prompt,
        stable_system_prompt=stable_system_prompt,
    )
    tool_dispatcher_fn = make_tool_dispatcher_node(
        tools_list=tools_list,
        loader=loader,
        redirect_tools_map=redirect_tools_map,
    )

    # ── llm_call 路由（V0.3 Send API：路由到 per-tool 节点）─────────────────────
    def _route_after_llm_call(state: AgentState) -> str | list[Send]:  # type: ignore[return]
        status = str(state.get("execution_status") or "")
        if status == "max_rounds_exceeded":
            return "finish_react"

        messages = list(state.get("messages") or [])
        last_ai: AIMessage | None = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_ai = msg
                break

        if last_ai is None:
            return "finish_react"

        calls = list(getattr(last_ai, "tool_calls", None) or [])
        if not calls:
            return "finish_react"

        non_finish = [tc for tc in calls if tc.get("name") != "finish_react"]
        if not non_finish:
            return "finish_react"

        # Per-tool Send 路由（各工具并行执行）
        # Send(node, arg) 中 arg 是目标节点的完整 input state，必须传当前 state 而非 {}
        if _tool_node_names:
            sends = [
                Send(tc["name"], state)
                for tc in non_finish
                if tc.get("name") in _tool_node_names
            ]
            if sends:
                return sends  # type: ignore[return-value]

        return "tool_dispatcher"

    # ── 注册节点 ─────────────────────────────────────────────────────────────────
    async def _intend(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await intend_node(state, config, knowledge_enhancer=knowledge_enhancer)
        return _as_state_update(result, node_name="intend")

    async def _llm_call(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await llm_call_fn(state, config)
        return _as_state_update(result, node_name="llm_call")

    async def _tool_dispatcher(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await tool_dispatcher_fn(state, config)
        return _as_state_update(result, node_name="tool_dispatcher")

    async def _finish_react(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await finish_react_node(state, config)
        return _as_state_update(result, node_name="finish_react")

    async def _analyze_clarify(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await analyze_clarify_node(state, config)
        return _as_state_update(result, node_name="analyze_clarify")

    async def _user_clarify(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await user_clarify_node(state, config)
        return _as_state_update(result, node_name="user_clarify")

    async def _respond(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await respond_node(state, config)
        return _as_state_update(result, node_name="respond")

    builder.add_node("intend", _intend)
    builder.add_node("llm_call", _llm_call)
    builder.add_node("tool_dispatcher", _tool_dispatcher)
    builder.add_node("finish_react", _finish_react)
    builder.add_node("analyze_clarify", _analyze_clarify)
    builder.add_node("user_clarify", _user_clarify)
    builder.add_node("respond", _respond)

    # ── 注册 per-tool 节点（每个工具一个独立 LangGraph 节点）────────────────────
    for _tool_fn in tools_list:
        _per_tool_node_fn = make_tool_node(
            _tool_fn.name,
            _tool_fn,
            loader=loader,
            redirect_tools_map=redirect_tools_map,
        )
        builder.add_node(
            _tool_fn.name,
            _make_per_tool_wrapper(
                _per_tool_node_fn,
                _tool_fn.name,
                lambda r, n: _as_state_update(r, node_name=n),
            ),
        )
        builder.add_conditional_edges(
            _tool_fn.name,
            _route_after_tool_node,
            {"llm_call": "llm_call", "analyze_clarify": "analyze_clarify"},
        )

    # ── 边 ───────────────────────────────────────────────────────────────────────
    builder.add_edge(START, "intend")
    builder.add_conditional_edges(
        "intend",
        _route_after_intend,
        {"command_done": END, "llm_call": "llm_call"},
    )
    builder.add_conditional_edges(
        "llm_call",
        _route_after_llm_call,
        {"finish_react": "finish_react", "tool_dispatcher": "tool_dispatcher"},
    )
    builder.add_conditional_edges(
        "tool_dispatcher",
        _route_after_tool_dispatcher,
        {
            "finish_react": "finish_react",
            "llm_call": "llm_call",
            "analyze_clarify": "analyze_clarify",
        },
    )
    builder.add_conditional_edges(
        "analyze_clarify",
        _route_after_analyze,
        {"user_clarify": "user_clarify", "tool_dispatcher": "tool_dispatcher"},
    )
    builder.add_edge("user_clarify", "tool_dispatcher")
    builder.add_edge("finish_react", "respond")
    builder.add_edge("respond", END)

    tool_keys = sorted((tools or {}).keys())
    redirect_tool_keys = sorted((redirect_tools or {}).keys())
    logger.info(
        "build_analysis_graph: V0.3 pipeline wired — tools count=%d keys=%s "
        "redirect_tools count=%d keys=%s knowledge_enhancer=%s",
        len(tool_keys),
        tool_keys,
        len(redirect_tool_keys),
        redirect_tool_keys,
        knowledge_enhancer is not None,
    )

    return builder
