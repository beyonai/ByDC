from __future__ import annotations
import json
import logging
import os
from typing import Any, Literal
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, tool
from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ROUNDS = 10

@tool("finish_react")
async def finish_react(
    reason: str,
    answer: str,
    result_type: Literal["text", "csv_file", "json", "json_file"] = "text",
    csv_file_path: str = "",
    data: str = "",
) -> dict[str, Any]:
    """ReAct 分析完毕时必须调用本工具，禁止直接输出最终答案。

    Args:
        reason: 结束原因（用于审计）
        answer: 文字类结论（result_type=text 时必填）
        result_type: 'text' | 'csv_file' | 'json' | 'json_file'
        csv_file_path: 文件路径（result_type=csv_file/json_file 时必填）
        data: JSON 字符串（result_type=json 时填写，工具返回的结构化数据）

    注意：execute_code 执行后会将 _result 自动保存到同名 .json 文件（result_file 字段），
    此时推荐使用 result_type=json_file，csv_file_path 填写 result_file 路径。
    """
    parsed_data: Any = None
    if result_type == "json" and data:
        try:
            parsed_data = json.loads(data)
        except Exception:
            parsed_data = data
    return {
        "__finish__": True,
        "answer": answer,
        "result_type": result_type,
        "csv_file_path": csv_file_path,
        "data": parsed_data,
    }

def _summarize_last_output(messages: list) -> str:
    """从消息历史中提取最后一条有意义的输出作为兜底答案。"""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            content = str(msg.content or "")
            if content:
                return content[:2000]
        if isinstance(msg, AIMessage):
            content = str(msg.content or "")
            if content:
                return content[:2000]
    return "任务已执行完成，但未能生成明确结论。"

def _build_llm(state: Any) -> Any:
    """从环境变量构建 LLM（优先 reasoning，其次 coding，最后 openai 默认）。"""
    for env_prefix in ("DATACLOUD_LLM_REASONING", "DATACLOUD_LLM_CODING"):
        api_base = os.getenv(f"{env_prefix}_API_BASE", "")
        api_key = os.getenv(f"{env_prefix}_API_KEY", "")
        model = os.getenv(f"{env_prefix}_MODEL", "")
        if api_base and api_key and model:
            return init_chat_model(
                model=model,
                model_provider="openai",
                api_key=api_key,
                base_url=api_base,
                temperature=0.0,
            )
    # 兜底
    return init_chat_model(model="gpt-4o", model_provider="openai", temperature=0.0)

async def run_react_loop(
    *,
    state: Any,
    tools_list: list[BaseTool],
    system_prompt: str,
    max_rounds: int | None = None,
    gateway_context: Any = None,
) -> dict[str, Any]:
    """执行 ReAct 主循环，返回 react_final 字典。

    停止信号优先级：
    L1: LLM 调用 finish_react 工具（最优，携带结构化元数据）
    L2: LLM 不产生 tool_calls，直接文字回答
    L3: 超出 max_rounds 轮数
    """
    if max_rounds is None:
        max_rounds = int(os.getenv("DATACLOUD_REACT_MAX_ROUNDS", str(_DEFAULT_MAX_ROUNDS)))

    # tools_map 包含 finish_react
    tools_map: dict[str, BaseTool] = {t.name: t for t in tools_list}
    tools_map["finish_react"] = finish_react

    llm = _build_llm(state)
    llm_with_tools = llm.bind_tools(list(tools_map.values()))

    messages: list = [SystemMessage(content=system_prompt)]
    user_query = str(state.get("user_query") or state.get("enriched_query") or "")
    if user_query:
        messages.append(HumanMessage(content=user_query))
    else:
        # 从 state.messages 中取最后一条用户消息
        for m in reversed(state.get("messages") or []):
            if isinstance(m, HumanMessage):
                messages.append(HumanMessage(content=m.content))
                break

    for round_idx in range(max_rounds):
        logger.info("[react_loop] round=%d/%d", round_idx + 1, max_rounds)
        ai_msg: AIMessage = await llm_with_tools.ainvoke(messages)
        messages.append(ai_msg)

        if not getattr(ai_msg, "tool_calls", None):
            # L2: 无 tool_calls，直接文字结束
            logger.info("[react_loop] stop: no_tool_call at round=%d", round_idx + 1)
            return {
                "react_final": {
                    "result_type": "text",
                    "answer": str(ai_msg.content or ""),
                    "stop_reason": "no_tool_call",
                },
                "react_rounds": round_idx + 1,
            }

        for tc in ai_msg.tool_calls:
            tool_id, result = await dispatch_tool(tc, tools_map, state, gateway_context=gateway_context)

            # L1: finish_react 终止
            if isinstance(result, dict) and result.get("__finish__"):
                logger.info("[react_loop] stop: finish_tool at round=%d", round_idx + 1)
                return {
                    "react_final": {**result, "stop_reason": "finish_tool"},
                    "react_rounds": round_idx + 1,
                }

            messages.append(
                ToolMessage(content=str(result) if result is not None else "", tool_call_id=tool_id)
            )

    # L3: 超出最大轮数
    logger.warning("[react_loop] stop: max_rounds=%d reached", max_rounds)
    return {
        "react_final": {
            "result_type": "text",
            "answer": _summarize_last_output(messages),
            "stop_reason": "max_rounds",
        },
        "react_rounds": max_rounds,
    }
