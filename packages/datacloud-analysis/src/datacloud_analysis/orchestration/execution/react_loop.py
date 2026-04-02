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
_TOOL_MSG_MAX_LEN = 2000   # ToolMessage 内容最大字符数
_TRIM_KEEP_ROUNDS = 6      # 滑动窗口：保留最近 N 轮 AI+Tool 消息对

@tool("finish_react")
async def finish_react(
    reason: str,
    answer: str,
    result_type: Literal["text", "csv_file", "json", "json_file", "query_result"] = "text",
    csv_file_path: str = "",
    data: str = "",
) -> dict[str, Any]:
    """ReAct 分析完毕时必须调用本工具，禁止直接输出最终答案。

    Args:
        reason: 结束原因（用于审计）
        answer: 文字类结论或分析。result_type=text 时为唯一输出；
                result_type=query_result 时若填写，系统会先推文字分析再推结构化数据。
        result_type: 'text' | 'csv_file' | 'json' | 'json_file' | 'query_result'
        csv_file_path: 文件路径（result_type=csv_file/json_file 时必填）
        data: JSON 字符串（result_type=json 时填写，工具返回的结构化数据）

    注意：
    - 调用 data_query 类工具后，返回中含 _hint 字段，请使用 result_type=query_result，
      系统会自动透传完整的 records/pagination/meta/file 结构，无需手动序列化。
      若需同时返回文字分析，填写 answer 字段即可（先推文字，后推结构化数据）。
    - execute_code 执行后会将 _result 自动保存到同名 .json 文件（result_file 字段），
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

def _conversation_messages_for_llm(state: Any) -> list[HumanMessage | AIMessage]:
    """Collect prior Human/AI turns from graph state for multi-turn ReAct.

    Worker 会把业务历史 + 本轮用户消息写入 ``state["messages"]``；若此处仅用
    ``user_query``（来自最后一条用户话），模型将看不到上一轮助手的回复（例如网格列表），
    导致「前 3 个网格」等指代无法解析。
    """
    out: list[HumanMessage | AIMessage] = []
    for m in state.get("messages") or []:
        if isinstance(m, (HumanMessage, AIMessage)):
            out.append(m)
    return out


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

def _compress_tool_result(result: Any, tool_name: str) -> str:
    """将工具返回值压缩为 ToolMessage 内容，避免大数据撑爆上下文。

    策略：
    - 含 _hint 的 dict（data_query 类）：直接使用 _hint，LLM 已获得足够决策信息
    - 含 records+meta 的 data block：替换为行数摘要
    - 其他：JSON 序列化后截断至 _TOOL_MSG_MAX_LEN 字符
    """
    if isinstance(result, dict):
        # 优先使用 _hint（已由 tool_wrapper 注入）
        hint = result.get("_hint")
        if hint:
            return str(hint)
        # 识别 data_query data block（直接或嵌套在 data 键下）
        data_block = result.get("data") if isinstance(result.get("data"), dict) else result
        if isinstance(data_block, dict) and "records" in data_block and "meta" in data_block:
            records = data_block.get("records") or []
            meta = data_block.get("meta") or {}
            meta_keys = list(meta.keys()) if isinstance(meta, dict) else []
            file_block = data_block.get("file")
            file_hint = ""
            if isinstance(file_block, dict) and file_block.get("file_url"):
                file_hint = f", file_url={file_block['file_url']}"
            return (
                f"[{tool_name} \u8fd4\u56de: {len(records)} \u6761 records"
                f", meta={meta_keys}{file_hint}]"
                f" \u8bf7\u7acb\u5373\u8c03\u7528 finish_react \u4f7f\u7528 result_type=query_result\u3002"
            )
    # 通用：序列化后截断
    try:
        text = json.dumps(result, ensure_ascii=False, default=str) if isinstance(result, (dict, list)) else str(result)
    except Exception:
        text = repr(result)
    if len(text) > _TOOL_MSG_MAX_LEN:
        return text[:_TOOL_MSG_MAX_LEN] + f"... [\u5df2\u622a\u65ad, \u539f\u957f {len(text)} \u5b57\u7b26]"
    return text


def _trim_messages_window(messages: list) -> list:
    """滑动窗口裁剪：保留 SystemMessage + HumanMessage + 最近 _TRIM_KEEP_ROUNDS 轮。

    只裁剪送给 LLM 的副本，原始 messages 列表不受影响。
    """
    head = []
    tail = []
    for i, m in enumerate(messages):
        if isinstance(m, (SystemMessage, HumanMessage)):
            head.append(m)
        else:
            tail = messages[i:]
            break
    if not tail:
        return list(messages)
    # 每轮 = 1 AIMessage + N ToolMessage，保留最近 _TRIM_KEEP_ROUNDS * 2 条（保守估计）
    keep = _TRIM_KEEP_ROUNDS * 2
    if len(tail) > keep:
        trimmed_count = len(tail) - keep
        tail = tail[-keep:]
        logger.debug("[react_loop] trim_messages: dropped %d old messages, kept %d", trimmed_count, len(tail))
    return head + tail


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
    conv = _conversation_messages_for_llm(state)
    if conv:
        messages.extend(conv)
        logger.info("[react_loop] seeded from state.messages: %d human/ai message(s)", len(conv))
    else:
        user_query = str(state.get("user_query") or state.get("enriched_query") or "")
        if user_query:
            messages.append(HumanMessage(content=user_query))
        else:
            for m in reversed(state.get("messages") or []):
                if isinstance(m, HumanMessage):
                    messages.append(HumanMessage(content=m.content))
                    break

    # 缓存最近一次 data_query 类工具返回的完整 data block（records+meta+pagination+file）
    # 供 result_type=query_result 时原样透传给 formatter，避免 LLM 二次序列化丢失结构
    _last_query_data: dict[str, Any] | None = None

    for round_idx in range(max_rounds):
        logger.info("[react_loop] round=%d/%d", round_idx + 1, max_rounds)
        ai_msg: AIMessage = await llm_with_tools.ainvoke(_trim_messages_window(messages))
        messages.append(ai_msg)

        if not getattr(ai_msg, "tool_calls", None):
            # L2: 无 tool_calls，直接文字结束
            logger.info("[react_loop] stop: no_tool_call at round=%d", round_idx + 1)
            if _last_query_data is not None:
                logger.info(
                    "[react_loop] no_tool_call: force query_result with cached data (records=%d has_file=%s)",
                    len(_last_query_data.get("records") or []),
                    bool(_last_query_data.get("file")),
                )
                return {
                    "react_final": {
                        "result_type": "query_result",
                        "answer": str(ai_msg.content or ""),
                        "query_data": _last_query_data,
                        "stop_reason": "no_tool_call_with_query_data",
                    },
                    "react_rounds": round_idx + 1,
                }
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

            # 缓存 data_query 结果：识别含 records+meta 的 data block
            if isinstance(result, dict):
                data_block = result.get("data") if isinstance(result.get("data"), dict) else result
                if isinstance(data_block, dict) and "records" in data_block and "meta" in data_block:
                    _last_query_data = data_block
                    logger.info(
                        "[react_loop] cached query_data: records=%d has_file=%s",
                        len(data_block.get("records") or []),
                        bool(data_block.get("file")),
                    )

            # L1: finish_react 终止
            if isinstance(result, dict) and result.get("__finish__"):
                logger.info("[react_loop] stop: finish_tool at round=%d", round_idx + 1)
                final = {**result, "stop_reason": "finish_tool"}
                # 如果 LLM 声明 query_result，注入缓存的 data block
                if final.get("result_type") == "query_result" and _last_query_data is not None:
                    logger.info(
                        "[react_loop] finish_tool: inject query_data (records=%d has_file=%s)",
                        len(_last_query_data.get("records") or []),
                        bool(_last_query_data.get("file")),
                    )
                    final["query_data"] = _last_query_data
                    # 如已返回结构化表格，避免文本与表格矛盾
                    answer = str(final.get("answer") or "")
                    if answer:
                        meta = _last_query_data.get("meta") if isinstance(_last_query_data, dict) else {}
                        columns_raw = meta.get("columns", []) if isinstance(meta, dict) else []
                        col_names: list[str] = []
                        for col in columns_raw:
                            if isinstance(col, dict):
                                name = str(col.get("name") or col.get("label") or "")
                                if name:
                                    col_names.append(name)
                            elif isinstance(col, str):
                                col_names.append(col)
                        has_count_col = any("数量" in n for n in col_names)
                        has_row_data = bool(_last_query_data.get("records"))
                        if has_count_col and has_row_data and ("未" in answer and "数量" in answer):
                            final["answer"] = "已返回结果表，详见下方数据。"
                return {
                    "react_final": final,
                    "react_rounds": round_idx + 1,
                }

            messages.append(
                ToolMessage(content=_compress_tool_result(result, tc["name"]), tool_call_id=tool_id)
            )

    # L3: 超出最大轮数
    logger.warning("[react_loop] stop: max_rounds=%d reached", max_rounds)
    if _last_query_data is not None:
        logger.info(
            "[react_loop] max_rounds: force query_result with cached data (records=%d has_file=%s)",
            len(_last_query_data.get("records") or []),
            bool(_last_query_data.get("file")),
        )
        return {
            "react_final": {
                "result_type": "query_result",
                "answer": _summarize_last_output(messages),
                "query_data": _last_query_data,
                "stop_reason": "max_rounds_with_query_data",
            },
            "react_rounds": max_rounds,
        }
    return {
        "react_final": {
            "result_type": "text",
            "answer": _summarize_last_output(messages),
            "stop_reason": "max_rounds",
        },
        "react_rounds": max_rounds,
    }
