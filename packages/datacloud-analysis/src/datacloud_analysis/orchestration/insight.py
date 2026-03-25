"""④ Summary and reply generation (design §3.1 INSIGHT).

Responsibilities
----------------
- Collect outputs from all completed sub-tasks (from state results or workspace).
- Emit a REASONING_LOG_DELTA thinking event with the merged query results.
- Call the *reasoning* LLM to synthesise a coherent answer.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from gateway_sdk import EventType, StreamChunkEvent
from gateway_sdk.core.protocol.content_type import SseReasonMessageType
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, SystemMessage

from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)


async def insight_node(state: AgentState) -> dict:
    """Generate the final answer and report from completed sub-task outputs.

    Input state keys:
        results: List of execution results (or file paths).
        messages: Conversation history.
        clarify_needed: bool

    Output state updates:
        messages: Append the final LLM response.
    """
    logger.debug("insight_node: synthesising final answer …")

    messages = state.get("messages", [])
    if state.get("clarify_needed"):
        # 如果前面判定需要追问，此时直接让 LLM 构造追问语句
        # 或者直接取 intent 里的内容作为追问
        intent = state.get("intent", "能具体说明一下吗？")
        return {"messages": [AIMessage(content=intent)]}

    results = state.get("results", [])
    
    # 读取所有结果（如果是文件路径，则读出内容）
    aggregated_data = []
    for res in results:
        if isinstance(res, dict) and "file_path" in res:
            try:
                with open(res["file_path"], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    aggregated_data.append({
                        "task_id": res["task_id"],
                        "data": data
                    })
            except Exception as e:
                logger.error("Failed to read intermediate result: %s", e)
        else:
            aggregated_data.append(res)
            
    data_context = json.dumps(aggregated_data, ensure_ascii=False)

    # 向前端推送合并数据查询思考消息
    context = state.get("gateway_context")
    if context is not None and aggregated_data:
        plan = state.get("plan", [])
        task_map = {t["id"]: t.get("description", "") for t in plan}
        lines = []
        for item in aggregated_data:
            task_id = item.get("task_id", "?")
            desc = task_map.get(task_id, "")
            data_preview = str(item.get("data", ""))[:200]
            lines.append(f"■ {task_id}：{desc}\n  → {data_preview}")
        thinking = (
            f"共 {len(aggregated_data)} 个任务已完成：\n"
            + "\n".join(lines)
        )

        # 推送思考标题
        await context.emit_chunk(
            StreamChunkEvent(content="数据分析"),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_title.value,
        )
        # 推送思考文本
        await context.emit_chunk(
            StreamChunkEvent(content=thinking),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_text.value,
        )


    model = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    if not model.startswith("openai:"):
        model = f"openai:{model}"
        
    llm = init_chat_model(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DATACLOUD_LLM_REASONING_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DATACLOUD_LLM_REASONING_API_BASE"),
    )

    sys_prompt = f"""你是一个高级数据分析师。
以下是执行查询任务后获得的数据结果：
{data_context}

请结合原始问题，直接给出专业的自然语言分析总结，不要使用任何占位符。回答尽量详实清晰。
"""
    
    # 调用大模型生成总结
    response = await llm.ainvoke(messages + [SystemMessage(content=sys_prompt)])
    
    return {"messages": [response]}
