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

    agent_tool_names = sorted(
        k for k, v in dynamic_tools.items() if getattr(v, "_is_agent_delegate", False)
    )
    data_tool_names = sorted(
        k for k, v in dynamic_tools.items() if not getattr(v, "_is_agent_delegate", False)
    )
    agent_tools_line = ", ".join(agent_tool_names) if agent_tool_names else "（无）"
    data_tools_line = ", ".join(data_tool_names) if data_tool_names else "（无）"

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

## 当前 Agent 可用的工具

数据查询工具（直接取数，单步即可）：
{data_tools_line}

Agent委托工具（将整个任务移交给专项子Agent处理）：
{agent_tools_line}

请判断用户意图是否清晰，并结合业务知识改写问题。
如果问题缺乏关键维度（如时间、明确指标），请判定为"不清晰"。

## query_mode 判定规则
- "online_query"：单次向数据查询工具取数即可（单表/单对象查询、列表、明细），不需要多步规划或复杂分析。
- "agent_delegate"：问题属于某个专项子Agent的职责范围，应整体移交给 Agent委托工具处理。
- "analysis"：需要任务拆解、多步执行、统计对比、关联、趋势、归因等，或不确定用哪个工具。

当 query_mode 为 "online_query" 时：
- "target_tool" 必须从【数据查询工具】列表中选且仅选一个；若列表为空则必须使用 "analysis"。
- "tool_params" 为对象：传给该工具的参数，键名须与工具实际接受的参数一致（如 question、include_plan 等），不要臆造不存在的键。

当 query_mode 为 "agent_delegate" 时：
- "target_tool" 必须从【Agent委托工具】列表中选且仅选一个；若列表为空则必须使用 "analysis"。
- "tool_params" 填空对象 {{}}。

返回格式必须为严格的 JSON，包含字段：
- "rewritten_intent": "改写后的清晰问题，或者如果需要追问，填入追问内容"
- "clarify_needed": true/false
- "query_mode": "online_query"、"agent_delegate" 或 "analysis"
- "target_tool": 字符串；非 online_query/agent_delegate 时填空字符串 ""
- "tool_params": 对象；非 online_query 时填空对象 {{}}
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
        query_mode = result.get("query_mode", "analysis")
        if query_mode not in ("online_query", "agent_delegate", "analysis"):
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
            + (f" / 工具：{target_tool}" if query_mode in ("online_query", "agent_delegate") else "")
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
