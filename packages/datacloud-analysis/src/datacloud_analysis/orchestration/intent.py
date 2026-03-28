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

from by_framework import EventType, StreamChunkEvent
from by_framework.core.protocol.content_type import SseReasonMessageType
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tools.knowledge import search_knowledge

logger = logging.getLogger(__name__)

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
        return {
            "intent": "",
            "clarify_needed": False,
            "query_mode": "analysis",
            "target_tool": "",
            "tool_params": {},
        }

    last_user_msg = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])

    prompts_overwrite = state.get("prompts_overwrite") or default_prompts or {}
    dynamic_tools = state.get("dynamic_tools") or {}
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

    response = await llm.ainvoke(
        [SystemMessage(content=static_sys)]  # Layer 0: static prefix, 100% cache hit
        + messages[-4:-1]                     # Layer 2: last 2 turns (pronoun resolution)
        + [dynamic_human]                     # Layer 3: current-turn dynamic content
    )

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

    # 向前端推送思考消息
    context = state.get("gateway_context")
    if context is not None:
        thinking = (
            ""
            f"■ 检索到的业务知识（节选）：\n{knowledge_preview}\n\n"
            f"■ 改写结果：{rewritten_intent}\n"
            f"■ 是否需要追问：{clarify_needed}\n"
            f"■ 路由：{query_mode}"
            + (f" / 工具：{target_tool}" if query_mode == "online_query" else "")
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
        "query_mode": query_mode,
        "target_tool": target_tool,
        "tool_params": tool_params,
    }
