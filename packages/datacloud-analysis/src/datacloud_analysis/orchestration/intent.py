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
from typing import cast

from gateway_sdk import EventType, StreamChunkEvent
from gateway_sdk.core.protocol.content_type import SseReasonMessageType
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tools.knowledge import search_knowledge

logger = logging.getLogger(__name__)


async def intent_node(
    state: AgentState,
    default_prompts: dict | None = None,
) -> dict:
    """Classify intent and attach knowledge context, then rewrite the query.

    Args:
        state: The current AgentState.

    Returns:
        State updates containing the rewritten intent and clarify_needed flag.
    """
    logger.debug("intent_node: classifying intent …")

    messages = state.get("messages", [])
    if not messages:
        return {"intent": "", "clarify_needed": False}

    last_user_msg = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])

    prompts_overwrite = state.get("prompts_overwrite") or default_prompts or {}

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

    sys_prompt = prompts_overwrite.get(
        "intent_prompt",
        f"""你是一个意图识别与改写专家。
用户原始问题：{last_user_msg}

相关业务知识：
{knowledge_text}

请判断用户意图是否清晰，并结合业务知识改写问题。
如果问题缺乏关键维度（如时间、明确指标），请判定为“不清晰”。

返回格式必须为严格的 JSON，包含两个字段：
- "rewritten_intent": "改写后的清晰问题，或者如果需要追问，填入追问内容"
- "clarify_needed": true/false
""",
    )

    response = await llm.ainvoke([SystemMessage(content=sys_prompt)])

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
    except Exception as e:
        logger.warning("Failed to parse intent JSON, fallback to default. Error: %s", e)
        rewritten_intent = str(last_user_msg)
        clarify_needed = False

    # 截断知识预览（避免 Redis/前端爆量）
    knowledge_preview = knowledge_text[:500] if knowledge_text else "无"

    # 向前端推送思考消息
    context = state.get("gateway_context")
    if context is not None:
        thinking = (
            ""
            f"■ 检索到的业务知识（节选）：\n{knowledge_preview}\n\n"
            f"■ 改写结果：{rewritten_intent}\n"
            f"■ 是否需要追问：{clarify_needed}"
        )
        # 推送思考标题
        await context.emit_chunk(
            StreamChunkEvent(content="问题理解"),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_title.value,
        )
        # 推送思考文本
        await context.emit_chunk(
            StreamChunkEvent(content=thinking),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_text.value,
        )

    return {
        "intent": rewritten_intent,
        "clarify_needed": clarify_needed,
        "knowledge_preview": knowledge_preview,
    }
