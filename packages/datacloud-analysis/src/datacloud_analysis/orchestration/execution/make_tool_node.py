"""make_tool_node：per-tool 节点工厂（V0.3 阶段 3）。

每个工具对应一个独立 LangGraph 节点：
  1. 从 state["messages"] 最后一条 AIMessage 提取对应 tool_call
  2. 捕获 ClarificationNeededError → execution_status="clarify_needed"
  3. 正常执行 → 写 ToolMessage 到 state["messages"]（MessagesState 自动累积）
  4. 检测 query data block，写入 react_last_query_data
  5. 清理澄清相关 state 字段
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tool_hook_plugins.types import ClarificationNeededError

logger = logging.getLogger(__name__)

_MAX_CONTENT_LEN = 4000


def make_tool_node(
    tool_name: str,
    tool_fn: Any,
    *,
    gateway_context: Any = None,
    loader: Any = None,
    redirect_tools_map: dict[str, Any] | None = None,
) -> Any:
    """返回指定工具的 LangGraph 节点函数闭包。

    Args:
        tool_name: 工具名称，与图节点名称一致。
        tool_fn:   LangChain BaseTool 实例。
        gateway_context: 请求级 gateway 上下文（工厂时绑定，运行时从 config 覆盖）。
        loader:    数据加载器（传递给 dispatch_tool hook 系统）。
        redirect_tools_map: 重定向工具映射（可选）。
    """
    tools_map: dict[str, Any] = {tool_name: tool_fn}
    if redirect_tools_map:
        tools_map.update(redirect_tools_map)

    async def _node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        _gateway_context = (config.get("configurable") or {}).get(
            "gateway_context"
        ) or gateway_context

        # 1. 从 state["messages"] 最后一条 AIMessage 提取本工具的 tool_call
        tc = _extract_tool_call(state, tool_name)
        if tc is None:
            # Resume 路径：从 pending_clarification_context 重建 tool_call
            tc = _extract_from_pending_context(state, tool_name)
        if tc is None:
            logger.error("[tool_node:%s] no tool_call found in state.messages", tool_name)
            return {"execution_status": "error"}

        # 2. 调用 dispatch_tool（before hook 通过 state→metadata 读 clarification_formatted_params）
        try:
            _tc_id, result = await dispatch_tool(
                tc,
                tools_map,
                state,
                gateway_context=_gateway_context,
                loader=loader,
            )
        except ClarificationNeededError as exc:
            logger.info(
                "[tool_node:%s] ClarificationNeededError round=%s",
                tool_name,
                state.get("react_round_idx"),
            )
            # 将 _clarification_cache 写入返回值，使 LangGraph 能 checkpoint 它；
            # 否则 resume 时 cache 丢失，before_call_back 会重跑 22 秒的 _analyze_clarification。
            return {
                "execution_status": "clarify_needed",
                "pending_clarification_context": {
                    **exc.context,
                    "tool_name": tool_name,
                    "react_round_idx": int(state.get("react_round_idx") or 0),
                },
                "_clarification_cache": state.get("_clarification_cache"),
            }

        # 3. 检测 query data block（records + meta 结构）
        _query_data: dict[str, Any] | None = None
        if isinstance(result, dict):
            data_block = result.get("data") if isinstance(result.get("data"), dict) else result
            if isinstance(data_block, dict) and "records" in data_block and "meta" in data_block:
                _query_data = data_block
                logger.info(
                    "[tool_node:%s] query_data detected records=%s",
                    tool_name,
                    len(data_block.get("records") or []),
                )

        # 4. 写 ToolMessage（MessagesState add_messages reducer 自动累积）
        content = _compress(result, tool_name)
        tool_msg = ToolMessage(
            content=content,
            tool_call_id=str(tc.get("id") or ""),
        )
        logger.info("[tool_node:%s] done tool_call_id=%s", tool_name, tc.get("id"))

        update: dict[str, Any] = {
            "messages": [tool_msg],
            "execution_status": None,
            "clarification_formatted_params": None,
            "pending_clarification_context": None,
            "clarification_analyze_result": None,
        }
        if _query_data is not None:
            update["react_last_query_data"] = _query_data
        return update

    return _node


# ── 辅助函数 ───────────────────────────────────────────────────────────────────


def _extract_tool_call(state: AgentState, tool_name: str) -> dict[str, Any] | None:
    """从 state["messages"] 最后一条 AIMessage 中提取指定工具的 tool_call。"""
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, AIMessage):
            for tc in getattr(msg, "tool_calls", None) or []:
                if tc.get("name") == tool_name:
                    return dict(tc)
            return None
    return None


def _extract_from_pending_context(state: AgentState, tool_name: str) -> dict[str, Any] | None:
    """Resume 路径：从 pending_clarification_context 重建 tool_call 结构。"""
    ctx = state.get("pending_clarification_context") or {}
    if ctx.get("tool_name") == tool_name:
        return {
            "name": tool_name,
            "args": ctx.get("structured_input") or {},
            "id": "",
        }
    return None


def _compress(result: Any, tool_name: str) -> str:
    """将工具返回值压缩为字符串（超长截断）。"""
    text = result if isinstance(result, str) else str(result)
    if len(text) > _MAX_CONTENT_LEN:
        logger.debug(
            "[tool_node:%s] result truncated %d→%d", tool_name, len(text), _MAX_CONTENT_LEN
        )
        return text[:_MAX_CONTENT_LEN] + "…[truncated]"
    return text
