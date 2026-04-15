from __future__ import annotations

import inspect
import json
import logging
import os
from collections.abc import Callable
from typing import Any

from langchain_core.runnables import RunnableConfig

from datacloud_analysis.orchestration.intend.command_router import CommandRouter
from datacloud_analysis.orchestration.message_util import last_human_text
from datacloud_analysis.orchestration.state import AgentState

_router = CommandRouter()
logger = logging.getLogger(__name__)


def _format_knowledge_for_prompt(knowledge_json: str) -> str:
    """将 knowledge JSON 转为人类可读字段映射文本（降低 token 消耗）。"""
    try:
        data = json.loads(knowledge_json)
        items = data.get("paradigmList", [])
        lines = []
        for item in items:
            name = item.get("name") or item.get("termName") or ""
            desc = item.get("fieldName") or item.get("description") or ""
            if name and desc:
                lines.append(f"{name} → {desc}")
        return "\n".join(lines) if lines else knowledge_json
    except Exception:
        return knowledge_json


def _trace_user_query_enabled() -> bool:
    return os.environ.get("DATACLOUD_TRACE_USER_QUERY", "").strip().lower() in ("1", "true", "yes")


def _message_line_preview(msg: Any, *, max_len: int = 100) -> str:
    cls = type(msg).__name__
    raw = getattr(msg, "content", "")
    one = raw.replace("\n", "\\n") if isinstance(raw, str) else repr(raw)
    if len(one) > max_len:
        one = one[: max_len - 3] + "..."
    return f"{cls}({one})"


async def _invoke_knowledge_enhancer(
    knowledge_enhancer: Callable[..., Any],
    *,
    user_query: str,
    gateway_context: Any,
    message_parent_id: str,
) -> Any:
    try:
        signature = inspect.signature(knowledge_enhancer)
        params = list(signature.parameters.values())
        accepts_varargs = any(param.kind is inspect.Parameter.VAR_POSITIONAL for param in params)
        positional_count = sum(
            1
            for param in params
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        )
        if accepts_varargs or positional_count >= 3:
            value = knowledge_enhancer(user_query, gateway_context, message_parent_id)
        elif positional_count == 2:
            value = knowledge_enhancer(user_query, gateway_context)
        else:
            value = knowledge_enhancer(user_query)
    except (TypeError, ValueError):
        # Some callables don't expose inspectable signatures (or expose dynamic wrappers).
        try:
            value = knowledge_enhancer(user_query, gateway_context, message_parent_id)
        except TypeError:
            value = knowledge_enhancer(user_query)

    if inspect.isawaitable(value):
        return await value
    return value


async def intend_node(
    state: AgentState,
    config: RunnableConfig,
    knowledge_enhancer: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    gw_ctx = (config.get("configurable") or {}).get("gateway_context")
    messages = state.get("messages") or []
    # 必须用「最后一条用户话」，不能取 messages[-1]：合并后的 state 常以 AIMessage 结尾，
    # 否则会误把助手回复当作用户问题，表现为意图/识别永远像第一轮。
    user_query = last_human_text(messages)

    if _trace_user_query_enabled():
        gw = config.get("configurable") or {}
        gctx = gw.get("gateway_context")
        sid = getattr(gctx, "session_id", "") if gctx is not None else ""
        tail_type = type(messages[-1]).__name__ if messages else "empty"
        logger.info(
            "[user_query_trace] intend_node session=%s messages_n=%d tail_msg_type=%s "
            "resolved_user_query_len=%d resolved_preview=%r",
            sid,
            len(messages),
            tail_type,
            len(user_query),
            user_query[:400] + ("..." if len(user_query) > 400 else ""),
        )
        for idx, m in enumerate(messages):
            logger.info(
                "[user_query_trace] intend_node msg[%d] %s",
                idx,
                _message_line_preview(m, max_len=160),
            )

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

    # 2. 非命令查询直接走 react 路径，无需 LLM 意图分类
    updates: dict[str, Any] = {
        "intent": "react",
        "intent_source": "react",
        "execution_status": "execution",
        "user_query": user_query,
    }

    # 3. 知识增强（仅当 knowledge_enhancer 提供时调用）
    if knowledge_enhancer is not None:
        try:
            _cfg = config.get("configurable") or {}
            message_pid = str(_cfg.get("knowledge_enhance_node_id") or "")
            result = await _invoke_knowledge_enhancer(
                knowledge_enhancer,
                user_query=user_query,
                gateway_context=gw_ctx,
                message_parent_id=message_pid,
            )
            knowledge_payload: dict[str, Any] = {
                "needs_clarification": result.needs_clarification,
                "form": result.form,
                "knowledge": result.knowledge,
                "query": getattr(result, "query", user_query),
            }
            updates["knowledge_payload"] = knowledge_payload
            if result.knowledge:
                snippet = _format_knowledge_for_prompt(result.knowledge)
                updates["knowledge_snippets"] = [snippet] if snippet else []
        except Exception:
            logger.exception("[intend_node] knowledge_enhancer failed, skipping")

    return updates
