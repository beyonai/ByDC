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

# 模块级引用，供测试 mock 覆盖（冷启动路径使用）
try:
    from datacloud_analysis.tools.anchor_tools import _do_search_ontology
except Exception:  # noqa: BLE001
    _do_search_ontology = None  # type: ignore[assignment]

try:
    from datacloud_analysis.tools.tool_pool import TOOL_POOL, TOOL_TO_OBJECT, TOOL_POOL_THRESHOLD, is_anchor_mode
except Exception:  # noqa: BLE001
    TOOL_POOL = {}  # type: ignore[assignment]
    TOOL_TO_OBJECT = {}  # type: ignore[assignment]
    TOOL_POOL_THRESHOLD = 30  # type: ignore[assignment]

    def is_anchor_mode() -> bool:  # type: ignore[misc]
        return False


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
        if (
            _do_search_ontology is not None
            and is_anchor_mode()
            and not (state.get("active_tools") or [])
        ):
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

            # ── 阈值填充：解锁后若业务工具数仍低于 THRESHOLD，继续从 TOOL_POOL 补充 ──
            # activate_skill_* 不计入配额（skill wrapper 是按需激活的，不占工具槽）
            _business_count = sum(1 for t in existing if not t.startswith("activate_skill_"))
            _budget = TOOL_POOL_THRESHOLD - _business_count
            if _budget > 0:
                for _name in TOOL_POOL:
                    if _name in existing or _name.startswith("activate_skill_"):
                        continue
                    existing.add(_name)
                    _budget -= 1
                    if _budget <= 0:
                        break
                logger.info(
                    "[intend_node] cold_start: filled to threshold, total=%d", len(existing)
                )

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
