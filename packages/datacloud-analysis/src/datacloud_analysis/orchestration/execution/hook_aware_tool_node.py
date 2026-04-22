"""HookAwareToolNode：在 prebuilt ToolNode 基础上注入 before/after_call_back 钩子。

继承 langgraph.prebuilt.ToolNode，覆写 ainvoke（公开 API，比 _run_one 稳定），
在工具执行前后调用插件钩子，ClarificationNeededError 转换为 Command 路由至澄清子流程。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from datacloud_analysis.tool_hook_plugins import get_tool_hook_plugin_manager
from datacloud_analysis.tool_hook_plugins.types import ClarificationNeededError, HookContext

logger = logging.getLogger(__name__)


class HookAwareToolNode(ToolNode):
    """在 prebuilt ToolNode 基础上注入 before/after_call_back 钩子。

    执行流程：
    1. before_call_back：逐工具构建 HookContext，调用 run_before，可修改参数或触发澄清。
    2. ClarificationNeededError → Command(goto="analyze_clarify")，中断当前工具执行链。
    3. 将修改后的 tool_params patch 到 AIMessage.tool_calls，传入 super().ainvoke。
    4. after_call_back：遍历本轮新增 ToolMessage，调用 run_after。
    5. 检测 query_data block（records+meta）写入 react_last_query_data。
    """

    def __init__(
        self,
        tools: list[Any],
        *,
        loader: Any = None,
        gateway_context: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(tools, **kwargs)
        self._loader = loader
        self._gw_ctx = gateway_context

    async def ainvoke(
        self,
        state: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        # 兼容 dict / AgentState
        state_dict: dict[str, Any] = dict(state) if isinstance(state, dict) else state

        messages = list(state_dict.get("messages") or [])
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last_ai is None or not (last_ai.tool_calls or []):
            return await super().ainvoke(state_dict, config, **kwargs)

        # Per-request gateway_context：config 优先，构造函数注入次之
        _gw_ctx = (
            ((config or {}).get("configurable") or {}).get("gateway_context") or self._gw_ctx  # type: ignore[attr-defined]
        )

        hook_manager = get_tool_hook_plugin_manager()
        patched_calls: list[dict[str, Any]] = []

        for tc in last_ai.tool_calls:
            tool_name = str(tc.get("name") or "")
            ctx: HookContext = {
                "tool_name": tool_name,
                "tool_params": dict(tc.get("args") or {}),
                "session_id": str(state_dict.get("agent_id") or ""),
                "user_query": str(state_dict.get("user_query") or ""),
                "knowledge_snippets": list(state_dict.get("knowledge_snippets") or []),
                "knowledge_payload": dict(state_dict.get("knowledge_payload") or {}),
                "term_context": list(state_dict.get("confirmed_terms") or []),
                "metadata": {"loader": self._loader, "state": state_dict},
            }

            try:
                ctx, _before_decision = await hook_manager.run_before(ctx)
            except ClarificationNeededError as exc:
                logger.info(
                    "[HookAwareToolNode] ClarificationNeededError tool=%s round=%s",
                    tool_name,
                    state_dict.get("react_round_idx"),
                )
                return Command(
                    update={
                        "execution_status": "clarify_needed",
                        "pending_clarification_context": {
                            **exc.context,
                            "tool_name": tool_name,
                            "react_round_idx": int(state_dict.get("react_round_idx") or 0),
                        },
                    },
                    goto="analyze_clarify",
                )

            patched_calls.append({**tc, "args": dict(ctx.get("tool_params") or {})})

        # 用修改后的 tool_calls 替换最后一条 AIMessage（Pydantic 不可变，必须 model_copy）
        patched_ai = last_ai.model_copy(update={"tool_calls": patched_calls})
        patched_state = {**state_dict, "messages": [*messages[:-1], patched_ai]}

        # 实际工具执行（走 prebuilt ToolNode 原有逻辑）
        result = await super().ainvoke(patched_state, config, **kwargs)

        result_dict: dict[str, Any] = dict(result) if isinstance(result, dict) else {"messages": []}

        # after_call_back：遍历本轮产出的 ToolMessage
        for msg in result_dict.get("messages") or []:
            if not isinstance(msg, ToolMessage):
                continue
            after_ctx: HookContext = {
                "tool_name": msg.name or "",
                "tool_params": {},
                "tool_output": msg.content,
            }
            try:
                await hook_manager.run_after(after_ctx)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[HookAwareToolNode] run_after failed tool=%s: %s", msg.name, exc)

        # 检测 query_data block，为 finish_react_node 写入 react_last_query_data
        query_data = _extract_query_data_from_tool_messages(result_dict.get("messages") or [])
        if query_data is not None:
            result_dict["react_last_query_data"] = query_data

        return result_dict


# ── 辅助函数 ───────────────────────────────────────────────────────────────────


def _extract_query_data_from_tool_messages(
    messages: list[Any],
) -> dict[str, Any] | None:
    """从本轮 ToolMessage content 中检测 records+meta 结构，返回 query_data 或 None。"""
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        if msg.name == "finish_react":
            continue
        data = _try_parse_query_data(str(msg.content or ""))
        if data is not None:
            logger.info(
                "[HookAwareToolNode] query_data detected tool=%s records=%d",
                msg.name,
                len(data.get("records") or []),
            )
            return data
    return None


def _try_parse_query_data(content: str) -> dict[str, Any] | None:
    """尝试将 ToolMessage content 解析为 JSON 并检测 records+meta 结构。"""
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    # 支持 {"data": {...}} 嵌套 或 直接 {"records": [...], "meta": {...}}
    data_block = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
    if (
        isinstance(data_block, dict)
        and isinstance(data_block.get("records"), list)
        and "meta" in data_block
    ):
        return data_block
    return None
