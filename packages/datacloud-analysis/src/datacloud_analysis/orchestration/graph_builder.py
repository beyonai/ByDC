"""Assemble the DataCloud analysis StateGraph.

V0.3 architecture: intend → llm_call → (Send) per-tool-node → llm_call → ... → finish_react → respond
V0.4 architecture（feature flag DATACLOUD_USE_PREBUILT_REACT=true）:
    intend → agent → HookAwareToolNode(tools) → finish_react_node / analyze_clarify → respond
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, ToolMessage
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

_DEFAULT_MAX_ROUNDS = int(os.getenv("DATACLOUD_REACT_MAX_ROUNDS", "10"))


# ── V0.4 路由函数（feature flag 新路径）────────────────────────────────────────


def should_continue(state: AgentState) -> Literal["tools", "respond"]:
    """agent 节点出口：决定是否继续调用工具。

    L2: AIMessage 无 tool_calls → respond（LLM 直接文字回答）
    L3: execution_status=max_rounds_exceeded 或 react_round_idx >= max_rounds → respond
    其他: → tools（finish_react 也必须走 tools 节点执行工具体）
    """
    status = str(state.get("execution_status") or "")
    if status == "max_rounds_exceeded":
        return "respond"

    messages = list(state.get("messages") or [])
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if last_ai is None or not (last_ai.tool_calls or []):
        return "respond"

    if int(state.get("react_round_idx") or 0) >= _DEFAULT_MAX_ROUNDS:
        return "respond"

    return "tools"


def after_tools_route(state: AgentState) -> Literal["agent", "finish_react_node"]:
    """tools 节点出口（正常执行路径）。

    L1: 本轮 ToolMessage 中含 finish_react → finish_react_node
    其他: → agent（继续下一轮 LLM 推理）

    ClarificationNeededError 由 HookAwareToolNode 返回 Command 直接路由，不经过此函数。
    """
    messages = list(state.get("messages") or [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            break
        if isinstance(msg, ToolMessage) and msg.name == "finish_react":
            return "finish_react_node"
    return "agent"


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
    loader: Any = None,
    redirect_tools: dict[str, Any] | None = None,
) -> StateGraph[AgentState]:
    """Return an uncompiled StateGraph.

    路由由 DATACLOUD_USE_PREBUILT_REACT 环境变量控制：
    - false（默认）：V0.3 自研图拓扑（旧路径，现有生产代码）
    - true：V0.4 prebuilt ToolNode 图拓扑（新路径）
    """
    use_prebuilt = os.getenv("DATACLOUD_USE_PREBUILT_REACT", "false").strip().lower() == "true"
    if use_prebuilt:
        logger.info("build_analysis_graph: V0.4 prebuilt path (DATACLOUD_USE_PREBUILT_REACT=true)")
        return _build_prebuilt_graph(
            prompts_overwrite=prompts_overwrite,
            tools=tools,
            loader=loader,
            redirect_tools=redirect_tools,
        )
    return _build_legacy_graph(
        prompts_overwrite=prompts_overwrite,
        tools=tools,
        loader=loader,
        redirect_tools=redirect_tools,
    )


def _build_legacy_graph(
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
    loader: Any = None,
    redirect_tools: dict[str, Any] | None = None,
) -> StateGraph[AgentState]:
    """V0.3 自研 StateGraph（旧路径，现有生产代码不修改）。"""
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
                Send(tc["name"], state) for tc in non_finish if tc.get("name") in _tool_node_names
            ]
            if sends:
                return sends  # type: ignore[return-value]

        return "tool_dispatcher"

    # ── 注册节点 ─────────────────────────────────────────────────────────────────
    async def _intend(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await intend_node(state, config)
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
        "redirect_tools count=%d keys=%s",
        len(tool_keys),
        tool_keys,
        len(redirect_tool_keys),
        redirect_tool_keys,
    )

    return builder


# ── V0.4 prebuilt 图构建（feature flag 新路径）────────────────────────────────


def _build_prebuilt_graph(
    prompts_overwrite: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
    loader: Any = None,
    redirect_tools: dict[str, Any] | None = None,
) -> StateGraph[AgentState]:
    """V0.4 新图拓扑：intend → agent → HookAwareToolNode(tools) → respond。

    新增节点：
    - agent：复用 make_llm_call_node（与旧路径相同的 LLM 调用逻辑）
    - tools：HookAwareToolNode（before/after hook，ClarificationNeededError→Command）

    删除节点（相比 V0.3）：
    - tool_dispatcher_node、per-tool Send 节点（make_tool_node）

    保留节点：
    - intend、finish_react_node、analyze_clarify、user_clarify、respond
    """
    from datacloud_analysis.orchestration.execution.hook_aware_tool_node import (  # noqa: PLC0415
        HookAwareToolNode,
    )
    from datacloud_analysis.orchestration.execution.react_loop import finish_react  # noqa: PLC0415

    builder: StateGraph[AgentState] = StateGraph(AgentState)

    # ── system prompt ────────────────────────────────────────────────────────────
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

    # ── tools_list（含 finish_react sentinel 工具）────────────────────────────────
    tools_list = _build_tools_list(tools)
    # finish_react 必须在 ToolNode tools 列表中，ToolNode 才能执行它
    all_tools = [*tools_list, finish_react]

    # ── 节点闭包 ─────────────────────────────────────────────────────────────────
    llm_call_fn = make_llm_call_node(
        tools_list=tools_list,
        system_prompt=stable_system_prompt,
        stable_system_prompt=stable_system_prompt,
    )

    hook_tool_node = HookAwareToolNode(all_tools, loader=loader)

    # ── 节点包装（统一 _as_state_update 校验）────────────────────────────────────
    async def _intend(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await intend_node(state, config)
        return _as_state_update(result, node_name="intend")

    async def _agent(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await llm_call_fn(state, config)
        return _as_state_update(result, node_name="agent")

    async def _finish_react(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await finish_react_node(state, config)
        return _as_state_update(result, node_name="finish_react_node")

    async def _analyze_clarify(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await analyze_clarify_node(state, config)
        return _as_state_update(result, node_name="analyze_clarify")

    async def _user_clarify(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await user_clarify_node(state, config)
        return _as_state_update(result, node_name="user_clarify")

    async def _respond(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        result = await respond_node(state, config)
        return _as_state_update(result, node_name="respond")

    # ── 注册节点 ─────────────────────────────────────────────────────────────────
    builder.add_node("intend", _intend)
    builder.add_node("agent", _agent)
    builder.add_node("tools", hook_tool_node)  # HookAwareToolNode 直接作为节点
    builder.add_node("finish_react_node", _finish_react)
    builder.add_node("analyze_clarify", _analyze_clarify)
    builder.add_node("user_clarify", _user_clarify)
    builder.add_node("respond", _respond)

    # ── 边 ───────────────────────────────────────────────────────────────────────
    builder.add_edge(START, "intend")
    builder.add_conditional_edges(
        "intend",
        _route_after_intend,
        {"command_done": END, "llm_call": "agent"},
    )
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "respond": "respond"},
    )
    builder.add_conditional_edges(
        "tools",
        after_tools_route,
        {"agent": "agent", "finish_react_node": "finish_react_node"},
    )
    # ClarificationNeededError 由 HookAwareToolNode 返回 Command(goto="analyze_clarify")
    # LangGraph 自动路由，无需额外 add_conditional_edges
    builder.add_conditional_edges(
        "analyze_clarify",
        _route_after_analyze,
        {"user_clarify": "user_clarify", "tool_dispatcher": "tools"},
    )
    builder.add_edge("user_clarify", "tools")
    builder.add_edge("finish_react_node", "respond")
    builder.add_edge("respond", END)

    tool_keys = sorted((tools or {}).keys())
    logger.info(
        "_build_prebuilt_graph: V0.4 pipeline wired — tools count=%d keys=%s",
        len(tool_keys),
        tool_keys,
    )

    return builder
