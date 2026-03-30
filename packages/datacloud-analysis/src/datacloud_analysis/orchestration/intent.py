"""Intent parsing node (workflow entry)."""

from __future__ import annotations

import json
import logging
import os
import unicodedata
from typing import Any, cast

from by_framework import EventType, StreamChunkEvent
from by_framework.core.protocol.content_type import SseReasonMessageType
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tools.knowledge import search_knowledge

logger = logging.getLogger(__name__)

_INTENT_SHORT_TERM_HISTORY_LIMIT = 6


def _plain_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def _is_numeric_or_symbol_only_input(text: str) -> bool:
    """Return True when the input is composed only of digits/symbols."""
    compact = "".join(ch for ch in text if not ch.isspace())
    if not compact:
        return False

    has_supported_char = False
    for ch in compact:
        if ch.isalpha() or ("\u4e00" <= ch <= "\u9fff"):
            return False
        if ch.isdigit():
            has_supported_char = True
            continue
        category = unicodedata.category(ch)
        if category.startswith(("P", "S")):
            has_supported_char = True
            continue
        return False
    return has_supported_char


def _summarize_roles(msgs: list[BaseMessage]) -> str:
    labels: list[str] = []
    for msg in msgs:
        if isinstance(msg, HumanMessage):
            labels.append("human")
        elif isinstance(msg, AIMessage):
            labels.append("ai")
        elif isinstance(msg, SystemMessage):
            labels.append("system")
        else:
            labels.append(type(msg).__name__)
    return ",".join(labels)


def _history_records_to_messages(records: list[dict[str, Any]]) -> list[BaseMessage]:
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
    except Exception as exc:  # noqa: BLE001
        logger.warning("intent_node: session history get_history failed: %s", exc)
        return []

    logger.info(
        "intent_node: short_term_memory get_history limit=%d session_id=%s raw_rows=%d",
        limit,
        session_id,
        len(records),
    )

    msgs = _history_records_to_messages(records)
    dropped_tail = False
    if msgs and isinstance(msgs[-1], HumanMessage) and _plain_text(msgs[-1].content) == current_user_plain:
        msgs = msgs[:-1]
        dropped_tail = True

    logger.info(
        "intent_node: short_term_memory after_dedup count=%d dropped_tail_duplicate=%s roles=%s",
        len(msgs),
        dropped_tail,
        _summarize_roles(msgs),
    )
    return msgs


_INTENT_STATIC_SYSTEM = """你是意图识别与问题改写专家。

请输出严格 JSON（不要 markdown），字段如下：
{
  "rewritten_intent": "改写后的问题或追问文本",
  "clarify_needed": true/false,
  "query_mode": "online_query" | "analysis" | "chitchat" | "agent_delegate",
  "target_tool": "工具名或空字符串",
  "tool_params": {},
  "concept_terms": ["业务术语列表"]
}

规则：
1. chitchat 时，target_tool 必须是 ""，tool_params 必须是 {}，concept_terms 必须是 []。
2. online_query 时，target_tool 必须从“本轮可用工具列表”中选择一个。
3. 若工具不确定或需要多步推理，query_mode 使用 analysis。
4. concept_terms 仅抽取业务对象/指标/术语，不含时间词、语气词、纯数字。
"""


async def intent_node(
    state: AgentState,
    gateway_context: Any = None,
    default_prompts: dict[str, Any] | None = None,
    default_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    logger.debug("intent_node: classifying intent")

    messages = state.get("messages", [])
    if not messages:
        return {
            "intent": "",
            "chitchat_reply": None,
            "clarify_needed": False,
            "query_mode": "analysis",
            "target_tool": "",
            "tool_params": {},
        }

    last_user_msg = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
    current_user_plain = _plain_text(last_user_msg)

    if _is_numeric_or_symbol_only_input(current_user_plain):
        logger.info(
            "intent_node: numeric/symbol-only input detected, force chitchat. input=%r",
            current_user_plain,
        )
        forced_reply = (
            f"我没有理解“{current_user_plain}”的业务意图。"
            "请告诉我你想查询的对象、指标和时间范围。"
        )
        return {
            "intent": forced_reply,
            "chitchat_reply": forced_reply,
            "clarify_needed": False,
            "knowledge_preview": "无",
            "query_mode": "chitchat",
            "target_tool": "",
            "tool_params": {},
            "concept_terms": [],
            "confirmed_terms": [],
            "ambiguous_terms": [],
        }

    prompts_overwrite = state.get("prompts_overwrite") or default_prompts or {}
    dynamic_tools = state.get("dynamic_tools") or default_tools or {}
    tool_names = sorted(dynamic_tools.keys())
    tools_line = ", ".join(tool_names) if tool_names else "（当前无动态工具，建议 analysis）"

    agent_tool_names = sorted(
        key for key, tool in dynamic_tools.items() if getattr(tool, "_is_agent_delegate", False)
    )
    agent_tools_line = ", ".join(agent_tool_names) if agent_tool_names else "（无）"

    knowledge_payload = await search_knowledge.ainvoke({"query": str(last_user_msg)})
    knowledge_text = json.dumps(knowledge_payload, ensure_ascii=False) if knowledge_payload else "无"

    model = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    if not model.startswith("openai:"):
        model = f"openai:{model}"

    llm = init_chat_model(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DATACLOUD_LLM_REASONING_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DATACLOUD_LLM_REASONING_API_BASE"),
    )

    static_sys = prompts_overwrite.get(
        "intent_system_prompt",
        prompts_overwrite.get("intent_prompt", _INTENT_STATIC_SYSTEM),
    )
    dynamic_human = HumanMessage(
        content=(
            f"【本轮可用工具】{tools_line}\n\n"
            f"【Agent委托工具】{agent_tools_line}\n\n"
            f"【知识检索结果】\n{knowledge_text}\n\n"
            f"【用户问题】{last_user_msg}\n"
        )
    )

    history_layer = await _load_short_term_history_messages(
        gateway_context,
        limit=_INTENT_SHORT_TERM_HISTORY_LIMIT,
        current_user_plain=current_user_plain,
    )
    graph_context_layer: list[BaseMessage] = [] if history_layer else list(messages[-4:-1])
    logger.info(
        "intent_node: llm_context 2a gateway_history=%d graph_slice=%d",
        len(history_layer),
        len(graph_context_layer),
    )

    try:
        response = await llm.ainvoke(
            [SystemMessage(content=static_sys)] + history_layer + graph_context_layer + [dynamic_human]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("intent_node: LLM call failed, falling back to defaults. Error: %s", exc)
        return {
            "intent": str(last_user_msg),
            "chitchat_reply": None,
            "clarify_needed": False,
            "knowledge_preview": knowledge_text[:500] if knowledge_text else "无",
            "query_mode": "analysis",
            "target_tool": "",
            "tool_params": {},
        }

    try:
        content = cast(str, response.content)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        result = json.loads(content)

        rewritten_intent = result.get("rewritten_intent", str(last_user_msg))
        clarify_needed = bool(result.get("clarify_needed", False))
        query_mode = str(result.get("query_mode", "analysis"))
        if query_mode not in ("online_query", "analysis", "chitchat", "agent_delegate"):
            query_mode = "analysis"

        raw_target = result.get("target_tool", "")
        target_tool = raw_target if isinstance(raw_target, str) else str(raw_target or "")
        raw_tool_params = result.get("tool_params", {})
        tool_params = raw_tool_params if isinstance(raw_tool_params, dict) else {}
        raw_concept_terms = result.get("concept_terms", [])
        concept_terms = (
            [str(term) for term in raw_concept_terms if str(term).strip()]
            if isinstance(raw_concept_terms, list)
            else []
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("intent_node: parse intent JSON failed, fallback to default. Error: %s", exc)
        rewritten_intent = str(last_user_msg)
        clarify_needed = False
        query_mode = "analysis"
        target_tool = ""
        tool_params = {}
        concept_terms = []

    knowledge_preview = knowledge_text[:500] if knowledge_text else "无"
    confirmed_terms: list[dict[str, Any]] = []
    ambiguous_terms: list[dict[str, Any]] = []

    if concept_terms and query_mode != "chitchat":
        user_id = getattr(gateway_context, "user_id", None) if gateway_context is not None else None
        try:
            from datacloud_analysis.tools.knowledge import (
                disambiguate_candidates,
                search_all_candidates,
                update_term_scores,
            )

            candidates_map = await search_all_candidates(concept_terms, user_id=user_id)
            confirmed_terms, ambiguous_terms = await disambiguate_candidates(
                candidates_map,
                str(last_user_msg),
                llm=llm,
            )
            logger.info(
                "intent_node: term_search concept_terms=%d confirmed=%d ambiguous=%d",
                len(concept_terms),
                len(confirmed_terms),
                len(ambiguous_terms),
            )

            score_records = [
                {"name_id": term.get("name_id"), "success": True}
                for term in confirmed_terms
                if term.get("name_id")
            ]
            if score_records:
                await update_term_scores(score_records, gateway_context=gateway_context)
        except Exception as exc:  # noqa: BLE001
            logger.warning("intent_node: term retrieval/disambiguation failed: %s", exc)
            confirmed_terms = []
            ambiguous_terms = [
                {
                    "mention": term,
                    "candidates": [],
                    "reason": "术语检索失败，需人工确认",
                }
                for term in concept_terms
            ]

    async def _emit_intent_reasoning_snapshot() -> None:
        if gateway_context is None:
            return
        term_line = ""
        if confirmed_terms:
            term_line += (
                "\n■ 已确认术语："
                + ", ".join(f"{t['mention']}→{t['term_name']}" for t in confirmed_terms)
            )
        if ambiguous_terms:
            term_line += "\n■ 待澄清术语：" + ", ".join(t["mention"] for t in ambiguous_terms)
        thinking = (
            f"■ 检索到的业务知识（节选）：\n{knowledge_preview}\n\n"
            f"■ 改写结果：{rewritten_intent}\n"
            f"■ 是否需要追问：{clarify_needed}\n"
            f"■ 路由：{query_mode}"
            + (f" / 工具：{target_tool}" if query_mode in ("online_query", "agent_delegate") else "")
            + (" / 闲聊直出" if query_mode == "chitchat" else "")
            + term_line
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

    await _emit_intent_reasoning_snapshot()

    if query_mode == "chitchat":
        target_tool = ""
        tool_params = {}

    return {
        "intent": rewritten_intent,
        "chitchat_reply": None,
        "clarify_needed": clarify_needed,
        "knowledge_preview": knowledge_preview,
        "query_mode": query_mode,
        "target_tool": target_tool,
        "tool_params": tool_params,
        "concept_terms": concept_terms,
        "confirmed_terms": confirmed_terms,
        "ambiguous_terms": ambiguous_terms,
    }

