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
    context = state.get("gateway_context")

    model = os.getenv("DATACLOUD_LLM_REASONING_MODEL", "openai:Qwen/Qwen3-235B-A22B")
    if not model.startswith("openai:"):
        model = f"openai:{model}"
        
    llm = init_chat_model(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DATACLOUD_LLM_REASONING_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DATACLOUD_LLM_REASONING_API_BASE"),
    )

    if state.get("clarify_needed"):
        intent = state.get("intent", "未匹配到具体查询意图")
        
        # 依然向前端发个标题让界面显得连贯
        if context is not None:
            await context.emit_chunk(
                StreamChunkEvent(content="意图澄清与对话"),
                event_type=EventType.REASONING_LOG_DELTA.value,
                content_type=SseReasonMessageType.think_title.value,
            )
            await context.emit_chunk(
                StreamChunkEvent(content=f"识别为闲聊或未明确数据意图：{intent}"),
                event_type=EventType.REASONING_LOG_DELTA.value,
                content_type=SseReasonMessageType.think_text.value,
            )
            
        sys_prompt = f"""你是一个高级数据分析管家。
检测到用户的问题可能不在我们的业务查询范围内，或者意图不清晰（系统内部识别意图：{intent}）。
请以高情商、友好的助手口吻回复用户，婉拒无关闲聊，告知你仅负责企业风险查证、账单流水分发、销售数据查询等专业业务查询，并引导用户在授权范围内重新提问。"""
        
        # 让 LLM 生成高情商回答，同时 worker 会完美监听到流
        response = await llm.ainvoke(messages + [SystemMessage(content=sys_prompt)])
        return {"messages": [response]}

    results = state.get("results", [])
    
    # 读取所有结果（如果是文件路径，则读出内容）
    aggregated_data = []
    for res in results:
        if isinstance(res, dict) and "file_path" in res and "preview" in res:
            # intercept the modified data_query payload
            task_id_info = res.get("task_id", "?")
            file_path = res["file_path"]
            preview = res.get("preview", [])
            total = res.get("total", len(preview))
            columns = res.get("columns", [])
            
            md_lines = []
            if columns:
                headers = [col.get("label", col.get("name", "")) for col in columns]
                md_lines.append("| " + " | ".join(headers) + " |")
                md_lines.append("|" + "|".join(["---"] * len(headers)) + "|")
                keys = [col.get("name") for col in columns]
                
                for row in preview:
                    cells = [str(row.get(k, "")) for k in keys]
                    md_lines.append("| " + " | ".join(cells) + " |")
            
            md_table = "\n".join(md_lines)
            notice = res.get("overflow_notice")
            if not notice:
                if total > len(preview):
                    notice = f"*【重要】数据量较大（共 {total} 条），此处仅展示前 {len(preview)} 条。详细数据路径: {file_path}*"
                else:
                    notice = f"*共 {total} 条，已全量展示。*"
            
            final_md = f"【数据查询结果】\n{md_table}\n{notice}"
            
            aggregated_data.append({
                "task_id": task_id_info,
                "data": final_md
            })
            
        elif isinstance(res, dict) and "file_path" in res:
            try:
                with open(res["file_path"], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    aggregated_data.append({
                        "task_id": res.get("task_id", "?"),
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




    sys_prompt = f"""你是一个高级数据分析师。
以下是各个子任务执行后的数据结果集合（部分数据已为您转化为格式化的 Markdown 表格）：
{data_context}

分析注意事项：
1. 请结合原始问题，直接给出专业的自然语言分析总结。
2. 尽量详实清晰，不能使用占位符。
3. 当需要在回复中直接呈现数据列表/明细时，请**务必原样保留或直接使用我们提供的 Markdown 表格格式**进行展示。
"""
    
    # 调用大模型生成总结
    response = await llm.ainvoke(messages + [SystemMessage(content=sys_prompt)])
    
    return {"messages": [response]}
