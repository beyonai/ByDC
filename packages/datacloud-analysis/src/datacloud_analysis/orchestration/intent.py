"""① Intent parsing — workflow first node (design §3.1 PRE_KNOW).

Responsibilities
----------------
- Call the knowledge tool to classify intent and attach 1-hop knowledge snippets.
- Determine if the intent is clear or ambiguous.
- Emit a REASONING_LOG_DELTA thinking event with knowledge + rewrite result.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, cast

from by_framework import EventType, StreamChunkEvent
from by_framework.core.protocol.content_type import SseReasonMessageType
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tools.knowledge import search_knowledge

logger = logging.getLogger(__name__)

# Gateway 持久化会话历史条数（与 get_history(limit) 语义一致，非「天数」）
_INTENT_SHORT_TERM_HISTORY_LIMIT = 6


def _plain_text(content: Any) -> str:
    """Normalize message content for deduplication."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def _summarize_roles(msgs: list[BaseMessage]) -> str:
    """Compact role sequence for logs (e.g. ``human,ai,human``)."""

    labels: list[str] = []
    for m in msgs:
        if isinstance(m, HumanMessage):
            labels.append("human")
        elif isinstance(m, AIMessage):
            labels.append("ai")
        elif isinstance(m, SystemMessage):
            labels.append("system")
        else:
            labels.append(type(m).__name__)
    return ",".join(labels)


def _history_records_to_messages(records: list[dict[str, Any]]) -> list[BaseMessage]:
    """Turn gateway history rows into LangChain messages (chronological)."""

    out: list[BaseMessage] = []
    for row in records:
        role = str(row.get("role") or "").lower()
        raw = row.get("content")
        text = raw if isinstance(raw, str) else (str(raw) if raw is not None else "")
        if role in ("assistant", "ai"):
            out.append(AIMessage(content=text))
        elif role == "system":
            out.append(SystemMessage(content=text))
        else:
            out.append(HumanMessage(content=text))
    return out


async def _load_short_term_history_messages(
    gateway_context: Any,
    *,
    limit: int,
    current_user_plain: str,
) -> list[BaseMessage]:
    """Load recent session history from the gateway; drop trailing duplicate of current user turn."""

    if gateway_context is None:
        logger.info("intent_node: short_term_memory skipped (gateway_context is None)")
        return []
    if limit <= 0:
        logger.info("intent_node: short_term_memory skipped (limit=%d)", limit)
        return []
    session_id = getattr(gateway_context, "session_id", "")
    try:
        history_mgr = gateway_context.agent_runtime_state.session_manager.history
        records = await history_mgr.get_history(limit)
    except Exception as exc:
        logger.warning("intent_node: session history get_history failed: %s", exc)
        return []

    raw_count = len(records)
    logger.info(
        "intent_node: short_term_memory get_history limit=%d session_id=%s raw_rows=%d",
        limit,
        session_id,
        raw_count,
    )

    msgs = _history_records_to_messages(records)
    dropped_tail = False
    if (
        msgs
        and isinstance(msgs[-1], HumanMessage)
        and _plain_text(msgs[-1].content) == current_user_plain
    ):
        msgs = msgs[:-1]
        dropped_tail = True

    logger.info(
        "intent_node: short_term_memory after_dedup count=%d dropped_tail_duplicate=%s roles=%s",
        len(msgs),
        dropped_tail,
        _summarize_roles(msgs),
    )
    return msgs

# ---------------------------------------------------------------------------
# Static system prompt — contains NO variable interpolation.
# All dynamic content (knowledge, user question, tools) goes into Layer 3
# HumanMessage so that this prefix is 100% KV-Cache-friendly.
# ---------------------------------------------------------------------------
_INTENT_STATIC_SYSTEM = """你是一个意图识别与改写专家。

## 任务说明
请判断用户意图是否清晰，结合业务知识改写问题，并选择正确的路由模式。
如果问题缺乏关键维度（如时间、明确指标），请判定为"不清晰"。

## query_mode 判定规则
- "online_query"：单次向已绑定工具取数即可（单表/单对象查询、列表、明细），\
不需要多步规划、代码沙箱、多表关联分析或复杂报表叙事。
- "analysis"：需要任务拆解、多步执行、统计对比、关联、趋势、归因等，或不确定用哪个工具。

当 query_mode 为 "online_query" 时：
- "target_tool" 必须从本轮 HumanMessage 提供的【可用工具列表】中选且仅选一个；\
若列表为空则必须使用 "analysis"。
- "tool_params" 为对象：传给该工具的参数，键名须与工具实际接受的参数一致\
（如 question、include_plan 等），不要臆造不存在的键。

## 返回格式（严格 JSON，无多余字段）
{
  "rewritten_intent": "改写后的清晰问题，或者如果需要追问，填入追问内容",
  "clarify_needed": true/false,
  "query_mode": "online_query" 或 "analysis",
  "target_tool": "工具名或空字符串",
  "tool_params": {}
}
"""


async def intent_node(
    state: AgentState,
    gateway_context: Any = None,
    default_prompts: dict | None = None,
    default_tools: dict[str, Any] | None = None,
) -> dict:
    """Classify intent and attach knowledge context, then rewrite the query.

    Args:
        state: The current AgentState.
        gateway_context: Optional AgentContext from runnable config (not checkpointed).
        default_prompts: Prompt overrides from graph compile closure (not checkpointed).
        default_tools: Tool registry from graph compile closure; must not live in state
            when using a persistent checkpointer (tools contain non-serializable callables).

    Short-term memory (when ``gateway_context`` is set):
        Loads up to ``_INTENT_SHORT_TERM_HISTORY_LIMIT`` messages from
        ``session_manager.history``; removes a trailing user row if it duplicates the
        current turn. If any history remains, graph ``messages[-4:-1]`` is omitted (2a).

    Returns:
        State updates containing the rewritten intent and clarify_needed flag.
    """
    logger.debug("intent_node: classifying intent …")

    messages = state.get("messages", [])
    if not messages:
        return {
            "intent": "",
            "clarify_needed": False,
            "query_mode": "analysis",
            "target_tool": "",
            "tool_params": {},
        }

    last_user_msg = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
    current_user_plain = _plain_text(last_user_msg)

    prompts_overwrite = state.get("prompts_overwrite") or default_prompts or {}
    dynamic_tools = state.get("dynamic_tools") or default_tools or {}
    tool_names = sorted(dynamic_tools.keys()) if isinstance(dynamic_tools, dict) else []
    tools_line = ", ".join(tool_names) if tool_names else "（当前无动态工具，请使用 analysis）"

    # 1. Search knowledge
    knowledge_snippets = await search_knowledge.ainvoke({"query": str(last_user_msg)})
    knowledge_text = json.dumps(knowledge_snippets, ensure_ascii=False) if knowledge_snippets else "无"

    # 2. Call LLM to rewrite and check intent
    model = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    if not model.startswith("openai:"):
        model = f"openai:{model}"

    llm = init_chat_model(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DATACLOUD_LLM_REASONING_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DATACLOUD_LLM_REASONING_API_BASE"),
    )

    # Layer 0: static system prompt — no variable interpolation, 100% KV-Cache hit.
    # Support legacy key "intent_prompt" for backward compatibility.
    static_sys = prompts_overwrite.get(
        "intent_system_prompt",
        prompts_overwrite.get("intent_prompt", _INTENT_STATIC_SYSTEM),
    )

    # Layer 3: all dynamic content in a single HumanMessage (current-turn only).
    dynamic_human = HumanMessage(content=(
        f"【本轮可用工具（用于 online_query 选型）】：{tools_line}\n\n"
        f"【检索到的相关业务知识】：\n{knowledge_text}\n\n"
        f"【用户当前提问】：{last_user_msg}\n\n"
        "请基于以上背景，输出路由 JSON。"
    ))

    # Layer 1：Gateway 最近 N 条会话历史（与本轮用户句去重，避免与 Layer 3 重复）。
    # 策略 2a：若历史非空则不再拼接 state.messages[-4:-1]，以免与持久化历史重叠。
    history_layer = await _load_short_term_history_messages(
        gateway_context,
        limit=_INTENT_SHORT_TERM_HISTORY_LIMIT,
        current_user_plain=current_user_plain,
    )
    graph_context_layer: list[BaseMessage] = (
        [] if history_layer else list(messages[-4:-1])
    )
    if history_layer:
        logger.info(
            "intent_node: llm_context 2a gateway_history=%d graph_slice=0",
            len(history_layer),
        )
    elif messages[-4:-1]:
        logger.info(
            "intent_node: llm_context 2a gateway_history=0 graph_slice=%d",
            len(messages[-4:-1]),
        )
    else:
        logger.info("intent_node: llm_context 2a gateway_history=0 graph_slice=0")

    try:
        response = await llm.ainvoke(
            [SystemMessage(content=static_sys)]
            + history_layer
            + graph_context_layer
            + [dynamic_human]
        )
    except Exception as exc:
        logger.warning("intent_node: LLM call failed, falling back to defaults. Error: %s", exc)
        return {
            "intent": str(last_user_msg),
            "clarify_needed": False,
            "knowledge_preview": knowledge_text[:500] if knowledge_text else "无",
            "query_mode": "analysis",
            "target_tool": "",
            "tool_params": {},
        }

    try:
        content = cast(str, response.content)
        # 尝试提取 JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        rewritten_intent = result.get("rewritten_intent", str(last_user_msg))
        clarify_needed = result.get("clarify_needed", False)
        query_mode = result.get("query_mode", "analysis")
        if query_mode not in ("online_query", "analysis"):
            query_mode = "analysis"
        target_tool = result.get("target_tool", "")
        if not isinstance(target_tool, str):
            target_tool = str(target_tool) if target_tool is not None else ""
        raw_tp = result.get("tool_params", {})
        tool_params = raw_tp if isinstance(raw_tp, dict) else {}
    except Exception as e:
        logger.warning("Failed to parse intent JSON, fallback to default. Error: %s", e)
        rewritten_intent = str(last_user_msg)
        clarify_needed = False
        query_mode = "analysis"
        target_tool = ""
        tool_params = {}

    # 截断知识预览（避免 Redis/前端爆量）
    knowledge_preview = knowledge_text[:500] if knowledge_text else "无"

    async def _emit_intent_reasoning_snapshot() -> None:
        """Push intent-phase reasoning to the gateway (reads latest locals each call)."""

        if gateway_context is None:
            return
        thinking = (
            ""
            f"■ 检索到的业务知识（节选）：\n{knowledge_preview}\n\n"
            f"■ 改写结果：{rewritten_intent}\n"
            f"■ 是否需要追问：{clarify_needed}\n"
            f"■ 路由：{query_mode}"
            + (f" / 工具：{target_tool}" if query_mode == "online_query" else "")
        )
        await gateway_context.emit_chunk(
            StreamChunkEvent(content="问题理解"),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_title.value,
        )
        
        await gateway_context.emit_chunk(
            StreamChunkEvent(content=thinking),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_text.value,
        )

    # 必须在 interrupt() 之前推送思考：若在 clarify_needed 时先 interrupt，节点在挂起点之前
    # 不会执行后面的 emit，前端会只有「思考中」而无「问题理解」；且无 checkpointer 时 Worker
    # 无法 aget_state 检测中断，会误判为正常结束。
    await _emit_intent_reasoning_snapshot()

    # 当意图不清晰时，通过 interrupt() 挂起图；resume 后返回值写入 rewritten_intent。
    if clarify_needed:
        logger.info("intent_node: clarify_needed=True, calling interrupt() for HITL")
        from langgraph.types import interrupt as lg_interrupt  # noqa: PLC0415

        user_reply = lg_interrupt(rewritten_intent)
        if user_reply:
            rewritten_intent = str(user_reply)
            clarify_needed = False
        await _emit_intent_reasoning_snapshot()

    return {
        "intent": rewritten_intent,
        "clarify_needed": clarify_needed,
        "knowledge_preview": knowledge_preview,
        "query_mode": query_mode,
        "target_tool": target_tool,
        "tool_params": tool_params,
    }
