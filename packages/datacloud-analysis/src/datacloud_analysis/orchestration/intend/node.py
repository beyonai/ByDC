from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.intend.command_router import CommandRouter
from datacloud_analysis.orchestration.message_util import last_human_text
from datacloud_analysis.orchestration.state import AgentState

_router = CommandRouter()
logger = logging.getLogger(__name__)


def _message_line_preview(msg: Any, *, max_len: int = 100) -> str:
    cls = type(msg).__name__
    raw = getattr(msg, "content", "")
    one = raw.replace("\n", "\\n") if isinstance(raw, str) else repr(raw)
    if len(one) > max_len:
        one = one[: max_len - 3] + "..."
    return f"{cls}({one})"


async def intend_node(
    state: AgentState,
    config: RunnableConfig,
) -> dict[str, Any]:
    gw_ctx = (config.get("configurable") or {}).get("gateway_context")
    messages = state.get("messages") or []
    user_query = last_human_text(messages)

    # target_tool 短路：跳过 LLM，直接构造 tool_call 走 tool_dispatcher
    target_tool = str(state.get("target_tool") or "").strip()
    if target_tool:
        logger.info(
            "[intend_node] target_tool=%r → bypassing LLM, injecting tool_call", target_tool
        )
        tool_call_id = f"tc_{uuid.uuid4().hex[:12]}"
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": tool_call_id,
                    "name": target_tool,
                    "args": {"query": user_query},
                    "type": "tool_call",
                }
            ],
        )
        return {
            "intent": "react",
            "intent_source": "target_tool",
            "execution_status": "target_tool_direct",
            "user_query": user_query,
            "messages": [ai_msg],
            "react_round_idx": 1,
        }

    # 1. 命令路由
    result = await _router.try_dispatch(
        user_query=user_query,
        state=state,
        config=config,
        gateway_context=gw_ctx,
    )
    if result["handled"]:
        return {
            "intent": "command",
            "intent_source": "command",
            "command_result": result["payload"],
            "execution_status": "command_done",
            "user_query": user_query,
        }

    # 冷启动锚点：anchor mode 且 active_tools 为空时，框架自动调用 search_ontology
    # 将结果写入 active_tools，LLM 第一轮就有工具可用
    _cold_start_active_tools: list[str] | None = None
    try:
        from datacloud_analysis.tools.anchor_tools import (  # noqa: PLC0415
            _do_search_ontology,
        )
        from datacloud_analysis.tools.tool_pool import (  # noqa: PLC0415
            TOOL_POOL,
            TOOL_TO_OBJECT,
            is_anchor_mode,
        )

        if is_anchor_mode() and not (state.get("active_tools") or []):
            logger.info(
                "[intend_node] cold_start: anchor mode, active_tools empty → search_ontology(%r)",
                user_query,
            )
            hits = _do_search_ontology(user_query, scope="all", type_filter="all", top_k=3)
            existing: set[str] = set()
            for hit in hits:
                obj_code = hit.get("objectCode") or hit.get("object_code", "")
                if not obj_code:
                    continue
                new = [
                    n
                    for n, c in TOOL_TO_OBJECT.items()
                    if c == obj_code and n in TOOL_POOL and n not in existing
                ]
                existing.update(new)
            _cold_start_active_tools = list(existing)
            logger.info(
                "[intend_node] cold_start: unlocked %d tools", len(_cold_start_active_tools)
            )
    except Exception:  # noqa: BLE001
        logger.debug("[intend_node] cold_start search_ontology skipped", exc_info=True)

    result_dict: dict[str, Any] = {
        "intent": "react",
        "intent_source": "react",
        "execution_status": "execution",
        "user_query": user_query,
    }
    if _cold_start_active_tools is not None:
        result_dict["active_tools"] = _cold_start_active_tools
    return result_dict
