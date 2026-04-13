from __future__ import annotations
import logging
from typing import Any
from langchain_core.runnables import RunnableConfig
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.orchestration.respond.formatter import format_result

logger = logging.getLogger(__name__)

async def respond_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    gw_ctx = (config.get("configurable") or {}).get("gateway_context")
    react_final = state.get("react_final") or {}
    workspace_dir = state.get("workspace_dir")

    # [DIAG] 诊断日志：确认 respond_node 收到的是当前轮还是上一轮的 react_final
    _qd = react_final.get("query_data") or {}
    _records = _qd.get("records") or [] if isinstance(_qd, dict) else []
    _first_rec = str(_records[0])[:80] if _records else "N/A"
    logger.warning(
        "[respond_node DIAG] result_type=%s answer_streamed=%s answer_preview=%r "
        "has_query_data=%s records_n=%d first_record_preview=%s",
        react_final.get("result_type"),
        react_final.get("answer_streamed"),
        str(react_final.get("answer") or "")[:80],
        bool(react_final.get("query_data")),
        len(_records),
        _first_rec,
    )
    logger.warning(
        "[respond_node DIAG] gw_ctx.message_id=%s gw_ctx.parent_message_id=%s",
        getattr(gw_ctx, "message_id", "N/A"),
        getattr(gw_ctx, "parent_message_id", "N/A"),
    )

    if not react_final:
        logger.warning("respond_node: react_final is empty")
        await format_result({"result_type": "text", "answer": ""}, gw_ctx, workspace_dir)
        return {}

    await format_result(react_final, gw_ctx, workspace_dir)
    return {}
