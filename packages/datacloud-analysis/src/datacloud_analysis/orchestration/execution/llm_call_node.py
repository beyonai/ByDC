"""llm_call_node：ReAct LLM 调用节点（V0.3 阶段 3）。

每轮从 state["messages"] 读取完整对话历史，调用 LLM，将 AIMessage 写入 state["messages"]。
LangGraph MessagesState 的 add_messages reducer 自动累积并 checkpoint，无需 react_messages_log。
interrupt() 只重跑工具节点，本节点作为独立图节点不受影响。
"""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.execution.llm_retry import _build_fallback_llm
from datacloud_analysis.orchestration.execution.react_loop import (
    _build_llm,
    _build_system_message,
    _invoke_llm_with_fallback,
    _trim_messages_window,
    finish_react,
)
from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ROUNDS = int(os.getenv("DATACLOUD_REACT_MAX_ROUNDS", "10"))


def _build_runtime_dynamic_prompt(state: AgentState, gateway_context: Any) -> str | None:
    """从 state 的 knowledge_snippets 和 gateway_context 构建每次请求的动态 prompt 部分。"""
    parts: list[str] = []

    knowledge_snippets = list(state.get("knowledge_snippets") or [])
    if knowledge_snippets:
        parts.append("\n\n## 数据查询知识增强\n" + "\n".join(str(s) for s in knowledge_snippets))

    _header_meta: dict[str, Any] = {}
    with contextlib.suppress(AttributeError):
        _header_meta = gateway_context.current_command.header.metadata or {}  # type: ignore[union-attr]

    _current_command = (
        getattr(gateway_context, "current_command", None) if gateway_context is not None else None
    )
    _header = getattr(_current_command, "header", None)
    # 优先读 header 直接字段，缺失时回退到 header.metadata dict（两处存储路径均支持）
    _user_code = str(
        getattr(_header, "user_code", "") or _header_meta.get("user_code") or ""
    ).strip()
    _user_name = str(
        getattr(_header, "user_name", "") or _header_meta.get("user_name") or ""
    ).strip()
    logger.info(
        "[_build_runtime_dynamic_prompt] gateway_context=%s header=%s user_code=%r user_name=%r",
        type(gateway_context).__name__,
        type(_header).__name__ if _header is not None else "None",
        _user_code,
        _user_name,
    )
    _now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    _runtime_lines = ["\n\n## 当前会话信息", f"- 当前时间：{_now_str}"]
    if _user_name and _user_code:
        _runtime_lines.append(f"- 当前用户：{_user_name}（工号：{_user_code}）")
    elif _user_name:
        _runtime_lines.append(f"- 当前用户：{_user_name}")
    elif _user_code:
        _runtime_lines.append(f"- 当前用户工号：{_user_code}")
    parts.append("\n".join(_runtime_lines))

    result = "".join(parts) if parts else None
    logger.info("[_build_runtime_dynamic_prompt] dynamic_prompt=%r", result)
    return result


def make_llm_call_node(
    *,
    tools_list: list[Any],
    system_prompt: str,
    stable_system_prompt: str | None = None,
    dynamic_prompt: str | None = None,
    max_rounds: int = _DEFAULT_MAX_ROUNDS,
    gateway_context: Any = None,
) -> Callable[[AgentState, RunnableConfig], Any]:
    """返回 llm_call_node 闭包（在 build_analysis_graph 中调用）。"""

    async def _llm_call(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """ReAct LLM 节点：每轮调用 LLM，将 AIMessage 写入 state["messages"]。

        从 state["messages"] 读取完整对话历史（含前几轮 AIMessage + ToolMessage），
        追加系统提示后调用 LLM，返回 AIMessage。
        通过 {"messages": [ai_msg]} 正常 return，MessagesState reducer 自动累积 checkpoint。
        """
        current_round = int(state.get("react_round_idx") or 0)
        if current_round >= max_rounds:
            logger.warning(
                "[llm_call] max_rounds=%d exceeded at round=%d", max_rounds, current_round
            )
            return {"execution_status": "max_rounds_exceeded", "react_round_idx": current_round}

        # ── Agent checkpoint replay guard ──────────────────────────────────────────────────────
        # OpenGauss checkpoint blob 丢失时，agent 节点可能与 user_clarify 同时被错误激活。
        # 检测特征：pending_clarification_context 已设置（等待澄清）+ clarification_formatted_params 未设置
        # （user_clarify_node 尚未运行写入格式化参数），说明当前 agent 调用属于脏 checkpoint replay。
        # 直接设置 agent_abort=True 信号跳过 LLM 调用；should_continue 据此路由到 END 终止该路径。
        _pending_ctx_ac: dict[str, Any] | None = state.get("pending_clarification_context")
        _clarify_fp_ac: Any = state.get("clarification_formatted_params")
        if _pending_ctx_ac and not _clarify_fp_ac:
            logger.warning(
                "[llm_call] AGENT REPLAY GUARD: pending_clarification_context set"
                " clarification_formatted_params=None → aborting bad agent activation"
                " (skipping LLM call) round=%d",
                current_round,
            )
            return {"agent_abort": True}

        # Per-request gateway_context: prefer config over factory closure
        _gateway_context = (config.get("configurable") or {}).get(
            "gateway_context"
        ) or gateway_context

        tools_map = {t.name: t for t in tools_list}
        tools_map["finish_react"] = finish_react
        _llm_config: dict[str, Any] | None = (config.get("configurable") or {}).get("llm_config")
        llm = _build_llm(state, llm_config=_llm_config)
        fallback_llm = _build_fallback_llm()
        llm_with_tools = llm.bind_tools(list(tools_map.values()))
        fallback_with_tools = (
            fallback_llm.bind_tools(list(tools_map.values())) if fallback_llm else None
        )

        # 每轮从 state["messages"] 重建消息列表（系统提示 + 对话历史）
        _dynamic = dynamic_prompt or _build_runtime_dynamic_prompt(state, _gateway_context)
        logger.info(
            "[llm_call] round=%d gateway_context=%s dynamic_preview=%r",
            current_round,
            type(_gateway_context).__name__ if _gateway_context is not None else "None",
            (_dynamic or "")[:120],
        )
        # Anthropic: dynamic 由 _build_system_message 注入 system（带 cache_control）。
        # 其他 provider: system message 保持纯静态（最大化可缓存前缀），
        # dynamic 注入第一条 HumanMessage，不影响 system + tools 的缓存命中。
        _provider = os.getenv("DATACLOUD_LLM_MODEL_PROVIDER", "openai").strip().lower()
        system_msg = _build_system_message(
            system_prompt,
            stable_system_prompt,
            _dynamic if _provider == "anthropic" else None,
        )
        conv = list(state.get("messages") or [])
        if conv:
            if _dynamic and _provider != "anthropic" and isinstance(conv[0], HumanMessage):
                patched = HumanMessage(content=_dynamic + "\n\n" + str(conv[0].content))
                messages = [system_msg, patched, *conv[1:]]
            else:
                messages = [system_msg, *conv]
        else:
            messages = [system_msg]
            if query := str(state.get("user_query") or state.get("enriched_query") or ""):
                _content = (_dynamic + "\n\n" + query) if _dynamic else query
                messages.append(HumanMessage(content=_content))

        thinking_id = uuid.uuid4().hex[:12]
        messages_window = _trim_messages_window(messages)
        ai_msg, _did_stream = await _invoke_llm_with_fallback(
            llm_with_tools,
            fallback_with_tools,
            messages_window,
            _gateway_context,
            state=state,
            round_idx=current_round,
            thinking_message_id=thinking_id,
            config=config,
        )

        calls = list(getattr(ai_msg, "tool_calls", None) or [])
        _usage = getattr(ai_msg, "usage_metadata", None) or {}
        _resp_meta = getattr(ai_msg, "response_metadata", None) or {}
        logger.info(
            "[llm_call] round=%d tool_calls=%d streamed=%s usage=%s resp_meta_keys=%s",
            current_round,
            len(calls),
            _did_stream,
            _usage,
            sorted(_resp_meta.keys()),
        )

        return {
            "messages": [ai_msg],
            "react_round_idx": current_round + 1,
            "execution_status": None,
            "answer_streamed": _did_stream,
            "agent_abort": False,
            # 新 turn 开始（round=0）时清除上一 turn 残留的 react_final，
            # 防止 LLM 直接回答（不调 finish_react）时 respond_node 读到陈旧值。
            **({"react_final": None} if current_round == 0 else {}),
        }

    return _llm_call
