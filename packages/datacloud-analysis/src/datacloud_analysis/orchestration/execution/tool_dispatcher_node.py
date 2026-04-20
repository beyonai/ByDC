"""tool_dispatcher_node：ReAct 工具分发节点。

从 react_messages_log 读最新 AIMessage，依次执行工具调用。
ClarificationNeededError → 路由到 analyze_clarify 子流程。
clarification_formatted_params 在 state 中时，before_call_back 通过 state→metadata 读取并应用。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.execution.react_loop import (
    _deserialize_messages,
    _serialize_messages,
    finish_react,
)
from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tool_hook_plugins.types import ClarificationNeededError

logger = logging.getLogger(__name__)


def make_tool_dispatcher_node(
    *,
    tools_list: list[Any],
    gateway_context: Any = None,
    loader: Any = None,
    redirect_tools_map: dict[str, Any] | None = None,
) -> Callable[[AgentState, RunnableConfig], Any]:
    """返回 tool_dispatcher_node 闭包。"""

    async def _tool_dispatcher(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """工具分发节点：从 react_messages_log 读最新 AIMessage，依次执行工具调用。

        正常完成 → 追加 ToolMessage，路由回 llm_call。
        finish_react → execution_status=finish_react，路由到 finish_react_node。
        ClarificationNeededError → execution_status=clarify_needed，路由到 analyze_clarify。
        """
        log = state.get("react_messages_log") or []
        messages = _deserialize_messages(log) if log else []

        # 取最后一条 AIMessage；react_messages_log 为空时回退到 state["messages"]
        # （llm_call_node 仅写 state["messages"]，resume 路径下 react_messages_log 可能为空）
        ai_msg: AIMessage | None = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                ai_msg = msg
                break
        if ai_msg is None:
            for msg in reversed(list(state.get("messages") or [])):
                if isinstance(msg, AIMessage):
                    ai_msg = msg
                    break
        if ai_msg is None:
            logger.error("[tool_dispatcher] no AIMessage found in react_messages_log or messages")
            return {"execution_status": "error"}

        tools_map: dict[str, Any] = {t.name: t for t in tools_list}
        tools_map["finish_react"] = finish_react
        if redirect_tools_map:
            tools_map.update(redirect_tools_map)

        calls = list(getattr(ai_msg, "tool_calls", None) or [])
        if not calls or calls[0].get("name") == "finish_react":
            return {"execution_status": "finish_react"}

        for tc in calls:
            tool_name = str(tc.get("name") or "")
            try:
                _tool_id, result = await dispatch_tool(
                    tc,
                    tools_map,
                    state,
                    gateway_context=gateway_context,
                    loader=loader,
                )
            except ClarificationNeededError as exc:
                logger.info(
                    "[tool_dispatcher] ClarificationNeededError tool=%s round=%s",
                    tool_name,
                    state.get("react_round_idx"),
                )
                return {
                    "execution_status": "clarify_needed",
                    "pending_clarification_context": {
                        **exc.context,
                        "tool_name": tool_name,
                        # react_messages_log 已 checkpoint，无需 snapshot
                        "react_round_idx": int(state.get("react_round_idx") or 1) - 1,
                    },
                }

            tool_msg = ToolMessage(
                content=str(result) if not isinstance(result, str) else result,
                tool_call_id=str(tc.get("id") or ""),
            )
            messages.append(tool_msg)
            logger.info("[tool_dispatcher] tool=%s done", tool_name)

        return {
            "react_messages_log": _serialize_messages(messages),
            "clarification_formatted_params": None,  # resume 后消费清理
            "execution_status": None,
        }

    return _tool_dispatcher
