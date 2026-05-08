from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

try:
    from langgraph.errors import GraphBubbleUp  # interrupt / GraphInterrupt base
except ImportError:  # pragma: no cover - langgraph not installed or older version
    GraphBubbleUp = type(None)  # type: ignore[assignment,misc]

from datacloud_analysis.orchestration.execution.tool_wrapper import dispatch_tool

logger = logging.getLogger(__name__)

# SSE 协议常量 — 与 by_framework EventType / SseMessageType 保持一致
_EVENT_TYPE_ANSWER_DELTA = "answerDelta"
_EVENT_TYPE_REASONING_LOG_DELTA = "reasoningLogDelta"
_EVENT_TYPE_REASONING_LOG_START = "reasoningLogStart"
_CONTENT_TYPE_TEXT = "1002"  # SseMessageType.text / SseReasonMessageType.think_text

# ── Thinking token 辅助函数 ──────────────────────────────────────────────────

# 过短或客套话前缀，对用户没有信息量的 thinking 内容
_FILLER_PREFIXES = ("好的", "当然", "根据", "明白", "OK", "Sure", "Of course")
_MEANINGFUL_THINKING_MIN_LEN = 10  # 少于此字符数的 thinking 直接过滤
_FILLER_SHORT_THRESHOLD = 30  # 以客套前缀开头且短于此长度则过滤


def _extract_content_text(content: Any) -> str:
    """从 AIMessage.content 提取纯文字（TextBlock）内容。

    - str → 直接返回
    - None → 返回 ""
    - list → 拼接所有 type=="text" 的 TextBlock（dict 或对象）
    - 其他意外类型 → 安全返回 ""（不抛异常）
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            try:
                # dict 形式
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(str(block.get("text", "")))
                else:
                    # 对象形式（ThinkingBlock / TextBlock attr 访问）
                    if getattr(block, "type", None) == "text":
                        parts.append(str(getattr(block, "text", "")))
            except Exception:
                pass
        return "".join(parts)
    # 意外类型：尽力转 str，不抛异常
    try:
        return str(content)
    except Exception:
        return ""


def _extract_thinking_text(content: Any) -> str:
    """从 AIMessage.content 提取 thinking（ThinkingBlock）内容。

    - str / None → 返回 ""（非 extended_thinking 模型不包含 ThinkingBlock）
    - list → 拼接所有 type=="thinking" 的 ThinkingBlock（dict 或对象）
    - 其他类型 → 返回 ""
    """
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        try:
            if isinstance(block, dict):
                if block.get("type") == "thinking":
                    parts.append(str(block.get("thinking", "")))
            else:
                if getattr(block, "type", None) == "thinking":
                    parts.append(str(getattr(block, "thinking", "")))
        except Exception:
            pass
    return "".join(parts)


def _is_meaningful_thinking(text: str) -> bool:
    """判断 thinking 文本是否有推送价值。

    过滤规则：
    1. 空字符串 → False
    2. 长度 < _MEANINGFUL_THINKING_MIN_LEN → False
    3. 以客套前缀开头 且 长度 < _FILLER_SHORT_THRESHOLD → False
    4. 其他 → True
    """
    if not text:
        return False
    if len(text) < _MEANINGFUL_THINKING_MIN_LEN:
        return False
    return not (
        len(text) < _FILLER_SHORT_THRESHOLD and any(text.startswith(p) for p in _FILLER_PREFIXES)
    )


async def _emit_thinking_token(
    token: str, *, message_id: str, config: RunnableConfig | None = None
) -> None:
    """推送单个 thinking token（静默降级，不抛异常）。

    - token 为空 → 不推送
    - message_id：由调用方按轮次生成，同一轮 LLM 思考共享同一个 ID
    """
    if not token:
        return
    try:
        from datacloud_data_sdk.stream_text import (
            coerce_stream_chunk_text,  # type: ignore  # noqa: PLC0415
        )
        from langchain_core.callbacks import adispatch_custom_event  # noqa: PLC0415

        await adispatch_custom_event(
            "dc_stream_chunk",
            {
                "content": coerce_stream_chunk_text(token),
                "event_type": _EVENT_TYPE_REASONING_LOG_DELTA,
                "content_type": _CONTENT_TYPE_TEXT,
                "message_id": message_id,
            },
            config=config,
        )
    except Exception as exc:
        logger.debug("[react_loop] thinking_token emit failed: %s", exc)


async def _emit_stream_token(
    token: str, *, message_id: str, config: RunnableConfig | None = None
) -> None:
    """推送单个流式文字 token（ReAct 中间思考过程 → 思考区）。

    - message_id：由调用方按轮次生成，同一轮 LLM 思考共享同一个 ID
    """
    if not token:
        return
    try:
        from datacloud_data_sdk.stream_text import (
            coerce_stream_chunk_text,  # type: ignore  # noqa: PLC0415
        )
        from langchain_core.callbacks import adispatch_custom_event  # noqa: PLC0415

        await adispatch_custom_event(
            "dc_stream_chunk",
            {
                "content": coerce_stream_chunk_text(token),
                "event_type": _EVENT_TYPE_REASONING_LOG_DELTA,
                "content_type": _CONTENT_TYPE_TEXT,
                "message_id": message_id,
            },
            config=config,
        )
    except Exception as exc:
        logger.debug("[react_loop] stream_token emit failed: %s", exc)


async def _emit_answer_token(
    token: str, *, message_id: str, config: RunnableConfig | None = None
) -> None:
    """推送 finish_react.answer 增量 token（→ 答案区 ANSWER_DELTA）。"""
    if not token:
        return
    try:
        from datacloud_data_sdk.stream_text import (
            coerce_stream_chunk_text,  # type: ignore  # noqa: PLC0415
        )
        from langchain_core.callbacks import adispatch_custom_event  # noqa: PLC0415

        await adispatch_custom_event(
            "dc_stream_chunk",
            {
                "content": coerce_stream_chunk_text(token),
                "event_type": _EVENT_TYPE_ANSWER_DELTA,
                "content_type": _CONTENT_TYPE_TEXT,
                "message_id": message_id,
            },
            config=config,
        )
    except Exception as exc:
        logger.warning("[react_loop] answer_token emit failed: %s", exc)


async def _emit_thinking_done_notification(
    elapsed_secs: float, *, config: RunnableConfig | None = None
) -> None:
    """首轮 LLM 收到第一个 chunk 时推送耗时通知到思考气泡区（无论耗时长短）。"""
    try:
        from langchain_core.callbacks import adispatch_custom_event  # noqa: PLC0415

        msg_id = f"thinking_done_{int(time.time() * 1000)}"
        text = f"久等了，我思考了 {elapsed_secs:.0f} 秒，继续干活"
        await adispatch_custom_event(
            "dc_stream_chunk",
            {
                "content": text,
                "event_type": _EVENT_TYPE_REASONING_LOG_START,
                "content_type": _CONTENT_TYPE_TEXT,
                "message_id": msg_id,
            },
            config=config,
        )
        logger.info("[thinking_notify] elapsed=%.1fs notified", elapsed_secs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[thinking_notify] emit failed: %s", exc)


# 错误信息中触发 tools schema 诊断 dump 的关键词（命中即说明是 schema 过大/格式错误）
_TOOLS_SCHEMA_ERR_KEYWORDS: tuple[str, ...] = (
    "schema exceeds",
    "tools.function",
    "is not a valid moonshot",
    "Invalid request",
)
# 单条日志最大输出长度，超过则分段（避免被某些 logging handler 截断）
_TOOLS_DUMP_CHUNK_SIZE = 8000


def _extract_bound_tools(llm_with_tools: Any) -> Any:
    """沿 RunnableBinding 链向下查找已绑定的 tools schema（OpenAI 协议格式）。"""
    bound: Any = llm_with_tools
    for _ in range(5):
        kw = getattr(bound, "kwargs", None)
        if isinstance(kw, dict) and "tools" in kw:
            return kw["tools"]
        bound = getattr(bound, "bound", None)
        if bound is None:
            break
    return None


def _dump_bound_tools_diagnostic(llm_with_tools: Any, exc: BaseException) -> None:
    """schema 过大类 400 错误时 dump tools schema 用于离线分析。

    仅当错误信息命中 ``_TOOLS_SCHEMA_ERR_KEYWORDS`` 时触发，避免正常错误污染日志。
    """
    err_str = str(exc)
    if not any(kw in err_str for kw in _TOOLS_SCHEMA_ERR_KEYWORDS):
        return
    try:
        tools = _extract_bound_tools(llm_with_tools)
    except Exception as diag_exc:  # noqa: BLE001
        logger.warning("[react_loop] tools 提取失败: %s", diag_exc)
        return
    if tools is None:
        logger.warning("[react_loop] tools dump: 未能从 llm_with_tools 提取 tools")
        return
    try:
        tools_json = json.dumps(tools, ensure_ascii=False)
    except Exception as diag_exc:  # noqa: BLE001
        logger.warning("[react_loop] tools 序列化失败: %s", diag_exc)
        return

    per_tool: list[tuple[int, str]] = []
    if isinstance(tools, list):
        for t in tools:
            name = "?"
            if isinstance(t, dict):
                fn = t.get("function") if isinstance(t.get("function"), dict) else t
                name = str(fn.get("name", "?")) if isinstance(fn, dict) else "?"
            with contextlib.suppress(Exception):
                per_tool.append((len(json.dumps(t, ensure_ascii=False)), name))
    per_tool.sort(reverse=True)
    logger.error(
        "[react_loop][TOOLS_DUMP] total_size=%d count=%d top10=%s",
        len(tools_json),
        len(tools) if isinstance(tools, list) else -1,
        per_tool[:10],
    )
    total_chunks = (len(tools_json) - 1) // _TOOLS_DUMP_CHUNK_SIZE + 1
    for idx in range(0, len(tools_json), _TOOLS_DUMP_CHUNK_SIZE):
        logger.error(
            "[react_loop][TOOLS_DUMP_BODY %d/%d] %s",
            idx // _TOOLS_DUMP_CHUNK_SIZE + 1,
            total_chunks,
            tools_json[idx : idx + _TOOLS_DUMP_CHUNK_SIZE],
        )


async def _stream_llm_call(
    llm_with_tools: Any,
    messages_window: list,
    gateway_context: Any = None,
    *,
    thinking_message_id: str = "model_thinking",
    query_received_at: float | None = None,
    round_idx: int = 0,
    config: RunnableConfig | None = None,
) -> tuple[Any, bool]:
    """流式调用 LLM，实时向 gateway_context 推送文字 token。

    返回 (assembled_ai_msg, did_stream_text)：
    - assembled_ai_msg: 完整的 AIMessage（由所有 chunk 累加而成）
    - did_stream_text: 是否推送过非空文字内容（供调用方标记 answer_streamed）

    注意事项：
    - tool_calls（包括多个并行调用）在全部 chunk 收集完后统一读取，不影响推送
    - 若 astream 返回空或累加失败，自动 fallback 至 ainvoke
    - thinking_message_id：由 run_react_loop 每轮生成，同一轮 LLM 思考段共享同一个 ID，
      下一轮或工具调用时切换为新 ID，实现思考气泡分段隔离
    """
    full_msg = None
    did_stream_text = False

    # 本次流式调用的答案 message_id：同一次 _stream_llm_call 内所有 answer token 共享此 ID，
    # 不同轮次调用时间戳不同，前端据此将各轮答案分为独立气泡。
    _answer_msg_id = f"ans_text_{int(time.time() * 1000)}"

    # 用于追踪 finish_react tool call 的流式 answer 参数
    _fr_idx: int | None = None  # finish_react 对应的 tool_call_chunks index
    _fr_args_acc: str = ""  # 已累积的 args JSON 字符串
    _fr_answer_emitted: int = 0  # 已推送的 answer 字符数

    # 用于检测 MiniMax 累积式 thinking（每个 chunk 含完整 thinking 全文，非增量）
    _thinking_acc: str = ""

    # [DIAG] 发送前打印 messages_window 中 AIMessage/ToolMessage 的 ID 关系，
    # 便于复现 tool_call_id  is not found（空 ID）等 400 错误。
    for _di, _dm in enumerate(messages_window):
        if isinstance(_dm, AIMessage):
            _tcs = list(getattr(_dm, "tool_calls", None) or [])
            if _tcs:
                logger.warning(
                    "[_stream_llm_call DIAG] window[%d] AIMessage tool_calls=%s",
                    _di,
                    [{"id": repr(_tc.get("id")), "name": _tc.get("name")} for _tc in _tcs],
                )
        elif isinstance(_dm, ToolMessage):
            logger.warning(
                "[_stream_llm_call DIAG] window[%d] ToolMessage tool_call_id=%r name=%r",
                _di,
                getattr(_dm, "tool_call_id", ""),
                getattr(_dm, "name", ""),
            )

    _thinking_notified = False
    try:
        async for chunk in llm_with_tools.astream(messages_window):
            # 首个 chunk 到达：计算等待耗时并推送通知（仅首轮，无论耗时长短）
            if not _thinking_notified:
                _thinking_notified = True
                if round_idx == 0 and query_received_at is not None:
                    elapsed = time.monotonic() - query_received_at
                    await _emit_thinking_done_notification(elapsed, config=config)

            # 累加 chunk
            if full_msg is None:
                full_msg = chunk
            else:
                try:
                    full_msg = full_msg + chunk
                except Exception:
                    # 部分 provider 的 chunk 不支持 +，保留最后一个 chunk
                    full_msg = chunk

            # ① 推送 thinking block（MiniMax reasoning_split=true / Claude extended_thinking）
            # MiniMax 为累积式：每个 chunk 含截至当前的完整 thinking，需提取增量后推送；
            # Anthropic 原生 extended thinking 为增量式，直接追加即可。
            _thinking_raw = _extract_thinking_text(chunk.content)
            if _thinking_raw:
                if _thinking_raw.startswith(_thinking_acc) and len(_thinking_raw) > len(
                    _thinking_acc
                ):
                    # 累积式：本 chunk 是上一次的超集，取新增部分
                    _thinking_delta = _thinking_raw[len(_thinking_acc) :]
                    _thinking_acc = _thinking_raw
                else:
                    # 增量式：直接追加
                    _thinking_delta = _thinking_raw
                    _thinking_acc += _thinking_raw
                if _thinking_delta:
                    await _emit_thinking_token(
                        _thinking_delta, message_id=thinking_message_id, config=config
                    )

            # ② 推送 LLM content 文字 token（ReAct 思考过程）
            # 仅在无 tool_call_chunks 时推送：部分模型生成 tool_call 时 content 里会带工具名，
            # 这类内容由 worker.py on_tool_start 的 sub_step 处理，避免重复推送。
            # 注意：did_stream_text 不在此处设为 True——
            # 此处推送的是 REASONING_LOG_DELTA（思考区），不是 ANSWER_DELTA（答案区）。
            # 若 LLM 绕过 finish_react 直接输出 content，formatter 仍需通过 _emit_text
            # 走 ANSWER_DELTA 正式推送，answer_streamed 必须保持 False 才能触发该路径。
            _has_tool_calls = bool(getattr(chunk, "tool_call_chunks", None))
            if not _has_tool_calls:
                _content_delta = _extract_content_text(chunk.content)
                if _content_delta:
                    await _emit_stream_token(
                        _content_delta, message_id=thinking_message_id, config=config
                    )
                    # 不设 did_stream_text = True，保证 formatter 仍走 _emit_text → ANSWER_DELTA

            # 实时推送 finish_react.answer 参数的增量内容（→ 答案区 ANSWER_DELTA）
            for tcc in getattr(chunk, "tool_call_chunks", None) or []:
                # 第一个 chunk 上有 name，后续 chunk name 为 None
                if tcc.get("name") == "finish_react":
                    _fr_idx = tcc.get("index")
                if _fr_idx is not None and tcc.get("index") == _fr_idx:
                    _fr_args_acc += tcc.get("args") or ""
                    m = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)', _fr_args_acc)
                    if m:
                        current = m.group(1)
                        if len(current) > _fr_answer_emitted:
                            delta = current[_fr_answer_emitted:]
                            await _emit_answer_token(
                                delta, message_id=_answer_msg_id, config=config
                            )
                            did_stream_text = True
                            _fr_answer_emitted = len(current)
    except Exception as exc:
        _dump_bound_tools_diagnostic(llm_with_tools, exc)
        logger.warning("[react_loop] astream failed (%s), fallback to ainvoke", exc)
        full_msg = None
        did_stream_text = False

    if full_msg is None:
        logger.warning("[react_loop] astream returned nothing, fallback to ainvoke")
        try:
            full_msg = await llm_with_tools.ainvoke(messages_window)
        except Exception as exc:
            _dump_bound_tools_diagnostic(llm_with_tools, exc)
            raise
        did_stream_text = False

    # [DIAG] 诊断日志：记录本次 LLM 调用流式推送的 finish_react.answer 内容
    if _fr_answer_emitted > 0:
        m = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)', _fr_args_acc)
        _streamed_answer = m.group(1) if m else _fr_args_acc[:200]
        logger.warning(
            "[_stream_llm_call DIAG] did_stream=%s fr_answer_emitted=%d streamed_answer_preview=%r",
            did_stream_text,
            _fr_answer_emitted,
            _streamed_answer[:200],
        )

    return full_msg, did_stream_text


async def _invoke_llm_with_fallback(
    primary_llm_with_tools: Any,
    fallback_llm_with_tools: Any | None,
    messages_window: list,
    gateway_context: Any,
    *,
    state: Any,
    round_idx: int,
    thinking_message_id: str,
    config: RunnableConfig | None = None,
) -> tuple[Any, bool]:
    """调用 LLM，内置三层容错：

    1. 主模型 + 指数退避重试（使用代码内默认策略）
    2. 备用模型 + 指数退避重试（若运行时显式注入备用模型实例）
    3. 全部不可用 → 保存断点到 Redis + 向用户推送引导文案 + 抛 _LlmUnavailableError

    thinking_message_id：本轮 LLM 思考段的消息 ID，穿透传给 _stream_llm_call，
    确保同一轮思考输出归属同一条消息气泡。
    """
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        CHECKPOINT_REPLY,
        save_llm_failure_checkpoint,
    )
    from datacloud_analysis.orchestration.execution.llm_retry import stream_llm_call_with_retry

    if not str(thinking_message_id or "").strip():
        raise ValueError("thinking_message_id must be a non-empty string")

    _query_received_at: float | None = state.get("query_received_at") if state else None

    # ── 主模型（含重试）────────────────────────────────────────────────────────
    last_exc: Exception
    try:
        return await stream_llm_call_with_retry(
            _stream_llm_call,
            primary_llm_with_tools,
            messages_window,
            gateway_context,
            thinking_message_id=thinking_message_id,
            query_received_at=_query_received_at,
            round_idx=round_idx,
            config=config,
        )
    except Exception as primary_exc:
        logger.warning("[LLM] 主模型全部重试失败 round=%d: %s", round_idx + 1, primary_exc)
        last_exc = primary_exc

    # ── 备用模型（含重试）──────────────────────────────────────────────────────
    if fallback_llm_with_tools is not None:
        try:
            logger.warning("[LLM] 主模型失败，切换到备用模型")
            return await stream_llm_call_with_retry(
                _stream_llm_call,
                fallback_llm_with_tools,
                messages_window,
                gateway_context,
                thinking_message_id=thinking_message_id,
                # 备用模型切换时通知已由主模型分支处理（或主模型连首 chunk 都未产生）
                # 不再重复推送，query_received_at 保持 None
                config=config,
            )
        except Exception as fallback_exc:
            logger.error("[LLM] 备用模型也失败 round=%d: %s", round_idx + 1, fallback_exc)
            last_exc = fallback_exc

    # ── 全部不可用：保存断点 + 推送引导文案 ────────────────────────────────────
    session_id = str(getattr(gateway_context, "session_id", "") or "") if gateway_context else ""
    redis_client = getattr(gateway_context, "redis", None) or getattr(
        gateway_context, "_redis_client", None
    )
    await save_llm_failure_checkpoint(redis_client, session_id, state, round_idx, last_exc)
    await _emit_stream_token(CHECKPOINT_REPLY, message_id=thinking_message_id, config=config)
    raise _LlmUnavailableError(CHECKPOINT_REPLY) from last_exc


_DEFAULT_MAX_ROUNDS = 10
_TOOL_MSG_MAX_LEN = 2000  # ToolMessage 内容最大字符数
_TRIM_KEEP_ROUNDS = 6  # 滑动窗口：保留最近 N 轮 AI+Tool 消息对


class _LlmUnavailableError(RuntimeError):
    """主模型与备用模型全部不可用时抛出。携带已向用户推送的引导文案。"""


# resume replay 信号：当 react_loop 从缓存恢复并重新执行被中断的 tool 时设为 True。
# tool 内部通过此信号跳过 llm_enhance 等昂贵操作。
is_resume_replay: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "is_resume_replay",
    default=False,
)


# ---- messages 序列化 / 反序列化（用于写入 LangGraph State）----


def _serialize_messages(messages: list) -> list[dict[str, Any]]:
    """将 LangChain Message 列表序列化为可 JSON 持久化的 dict 列表。"""
    result: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append({"type": "system", "content": str(msg.content or "")})
        elif isinstance(msg, HumanMessage):
            result.append({"type": "human", "content": str(msg.content or "")})
        elif isinstance(msg, AIMessage):
            result.append(
                {
                    "type": "ai",
                    "content": str(msg.content or ""),
                    "tool_calls": list(getattr(msg, "tool_calls", []) or []),
                }
            )
        elif isinstance(msg, ToolMessage):
            result.append(
                {
                    "type": "tool",
                    "content": str(msg.content or ""),
                    "tool_call_id": str(getattr(msg, "tool_call_id", "") or ""),
                }
            )
        else:
            # 未知类型：尽力序列化
            result.append(
                {
                    "type": "unknown",
                    "content": str(getattr(msg, "content", repr(msg))),
                }
            )
    return result


def _deserialize_messages(data: list[dict[str, Any]]) -> list:
    """将 dict 列表反序列化为 LangChain Message 对象列表。"""
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        msg_type = item.get("type", "")
        content = item.get("content", "")
        if msg_type == "system":
            result.append(SystemMessage(content=content))
        elif msg_type == "human":
            result.append(HumanMessage(content=content))
        elif msg_type == "ai":
            result.append(
                AIMessage(
                    content=content,
                    tool_calls=list(item.get("tool_calls") or []),
                )
            )
        elif msg_type == "tool":
            result.append(
                ToolMessage(
                    content=content,
                    tool_call_id=str(item.get("tool_call_id") or ""),
                )
            )
        else:
            result.append(HumanMessage(content=content))
    return result


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
    - 【重要】result_type=query_result 时，answer 字段只写一句话的文字摘要
      （例如"共有 N 家企业"），绝对不要在 answer 里写数据表格或列表，
      数据已经通过 query_data 自动结构化展示，写进 answer 会导致重复输出。
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


def _build_llm(state: Any, llm_config: dict[str, Any] | None = None) -> Any:
    """构建 LLM 实例。

    优先使用 llm_config（由 OntologyAgentConfig 经 configurable 透传），
    回退至 DATACLOUD_LLM_* 环境变量。

    支持的环境变量（llm_config 未提供对应字段时生效）：
      DATACLOUD_LLM_MODEL_PROVIDER  协议类型：openai（默认）或 anthropic
      DATACLOUD_LLM_MODEL           模型名称（纯名称，不含 provider 前缀）
      DATACLOUD_LLM_API_KEY         API Key
      DATACLOUD_LLM_API_BASE        API Base URL；anthropic 官方 API 可不填
      DATACLOUD_LLM_TEMPERATURE     温度，默认 0.0
      DATACLOUD_LLM_MODEL_KWARGS    JSON 字符串，透传额外参数，如 {"max_tokens": 8192}
    """
    import json as _json

    _ = state
    cfg = llm_config or {}
    provider = (
        str(cfg.get("provider") or os.getenv("DATACLOUD_LLM_MODEL_PROVIDER", "openai"))
        .strip()
        .lower()
    )
    model = str(cfg.get("model") or os.getenv("DATACLOUD_LLM_MODEL", "")).strip()
    api_key = str(cfg.get("api_key") or os.getenv("DATACLOUD_LLM_API_KEY", "")).strip()
    api_base = str(cfg.get("base_url") or os.getenv("DATACLOUD_LLM_API_BASE", "")).strip()
    raw_temp = cfg.get("temperature")
    temperature = (
        float(raw_temp)
        if raw_temp is not None
        else float(os.getenv("DATACLOUD_LLM_TEMPERATURE", "0.0") or "0.0")
    )

    raw_kwargs = os.getenv("DATACLOUD_LLM_MODEL_KWARGS", "").strip()
    extra_kwargs: dict[str, Any] = {}
    if raw_kwargs:
        try:
            extra_kwargs = _json.loads(raw_kwargs)
        except Exception:
            logger.warning("DATACLOUD_LLM_MODEL_KWARGS 解析失败，已忽略: %s", raw_kwargs)
    # llm_config.model_kwargs 优先级高于环境变量
    if cfg.get("model_kwargs"):
        extra_kwargs = {**extra_kwargs, **cfg["model_kwargs"]}

    if not model:
        logger.warning("DATACLOUD_LLM_MODEL 未配置，回退至 gpt-4o")
        return init_chat_model(model="gpt-4o", model_provider="openai", temperature=0.0)

    kwargs: dict[str, Any] = {"model": model, "temperature": temperature, **extra_kwargs}
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["base_url"] = api_base

    if provider == "anthropic":
        return init_chat_model(model_provider="anthropic", **kwargs)
    else:
        return init_chat_model(model_provider="openai", **kwargs)


def _build_system_message(
    system_prompt: str,
    stable_system_prompt: str | None = None,
    dynamic_prompt: str | None = None,
) -> SystemMessage:
    """构建 SystemMessage，按 LLM provider 自动选择是否注入 cache_control。

    - provider=anthropic：使用结构化 content list，stable 前缀附带
      ``cache_control: {"type": "ephemeral"}`` 以启用 Prompt Caching。
    - 其他 provider（openai 兼容等）：使用纯字符串，避免 OpenAI API
      因未知字段 ``cache_control`` 报 400 错误。
    - stable_system_prompt=None：始终退回纯字符串（兼容旧调用方）。
    """
    _provider = os.getenv("DATACLOUD_LLM_MODEL_PROVIDER", "openai").strip().lower()
    if stable_system_prompt is not None and _provider == "anthropic":
        _content: list[dict] = [
            {
                "type": "text",
                "text": stable_system_prompt,
                "cache_control": {"type": "ephemeral"},
            },
        ]
        if dynamic_prompt:
            _content.append({"type": "text", "text": dynamic_prompt})
        return SystemMessage(content=_content)
    return SystemMessage(content=system_prompt)


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
            # 小结果集（≤5行）带上实际数据，防止 LLM 把「行数」误当「字段值」
            if len(records) <= 5:
                records_json = json.dumps(records, ensure_ascii=False, default=str)
                return (
                    f"[{tool_name} 返回: {len(records)} 条 records: {records_json}"
                    f", meta={meta_keys}{file_hint}]"
                    f" 请立即调用 finish_react 使用 result_type=query_result。"
                )
            return (
                f"[{tool_name} 返回: {len(records)} 条 records"
                f", meta={meta_keys}{file_hint}]"
                f" 请立即调用 finish_react 使用 result_type=query_result。"
            )
    # 通用：序列化后截断
    try:
        text = (
            json.dumps(result, ensure_ascii=False, default=str)
            if isinstance(result, (dict, list))
            else str(result)
        )
    except Exception:
        text = repr(result)
    if len(text) > _TOOL_MSG_MAX_LEN:
        return (
            text[:_TOOL_MSG_MAX_LEN]
            + f"... [\u5df2\u622a\u65ad, \u539f\u957f {len(text)} \u5b57\u7b26]"
        )
    return text


def _trim_messages_window(messages: list) -> list:
    """滑动窗口裁剪：保留 SystemMessage + HumanMessage + 最近 _TRIM_KEEP_ROUNDS 轮。

    只裁剪送给 LLM 的副本，原始 messages 列表不受影响。
    裁剪后确保 tail 不以孤儿 ToolMessage 开头（其对应 AIMessage 已被截断），
    避免 LLM API 返回 400 tool_call_id not found 错误。
    """
    head: list[Any] = []
    tail: list[Any] = []
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
        # 截断后 tail 头部可能残留孤儿 ToolMessage（其 AIMessage 已被截断）。
        # 判定准则：任何出现在第一个 AIMessage 之前的 ToolMessage 都是孤儿——
        # 合法对话结构保证 ToolMessage 只能跟在其对应的 AIMessage 之后。
        # 不做 tool_call_id 比对，避免同名工具在不同轮次复用相同 id 时误判。
        first_ai_idx = next(
            (i for i, m in enumerate(tail) if isinstance(m, AIMessage)),
            0,
        )
        orphan_count = first_ai_idx
        if first_ai_idx:
            tail = tail[first_ai_idx:]
        logger.debug(
            "[react_loop] trim_messages: dropped %d old messages, kept %d, orphans_removed=%d",
            trimmed_count,
            len(tail),
            orphan_count,
        )
    result = head + tail
    # 检查消息历史中是否存在孤立的 AIMessage（有 tool_calls 但后面紧跟另一个 AIMessage 而非 ToolMessage）。
    # checkpoint blob 丢失时会出现此情况，发给 LLM 会返回 400 (2013)。
    # 修复：删除孤立的 AIMessage 及其后直到下一个 AIMessage 之间的所有 ToolMessage。
    cleaned: list[Any] = []
    i = 0
    while i < len(result):
        msg = result[i]
        if isinstance(msg, AIMessage) and (msg.tool_calls or []):
            # 收集该 AIMessage 对应的 tool_call_ids
            tc_ids = {tc.get("id") for tc in (msg.tool_calls or []) if tc.get("id")}
            # 向后扫描，找到对应的 ToolMessage 或下一个 AIMessage
            j = i + 1
            found_tool_msgs: list[Any] = []
            matched_ids: set[str] = set()
            while j < len(result):
                m = result[j]
                if isinstance(m, AIMessage):
                    break  # 遇到下一个 AIMessage，停止扫描
                if isinstance(m, ToolMessage):
                    tid = getattr(m, "tool_call_id", None)
                    if tid in tc_ids:
                        matched_ids.add(tid)
                    found_tool_msgs.append(m)
                j += 1
            if tc_ids and not matched_ids:
                # 孤立 AIMessage：没有任何对应的 ToolMessage，删除该 AIMessage 及其后的孤立 ToolMessage
                logger.warning(
                    "[react_loop] trim_messages: orphan AIMessage tool_calls detected"
                    " (no matching ToolMessage) → removing AIMessage and %d trailing ToolMessages"
                    " to avoid 400 (2013) tool_call_ids=%s",
                    len(found_tool_msgs),
                    tc_ids,
                )
                i = j  # 跳过孤立的 AIMessage 和其后的 ToolMessage
                continue
        cleaned.append(msg)
        i += 1
    return cleaned


async def run_react_loop(
    *,
    state: Any,
    tools_list: list[BaseTool],
    system_prompt: str,
    stable_system_prompt: str | None = None,
    dynamic_prompt: str | None = None,
    max_rounds: int | None = None,
    gateway_context: Any = None,
    loader: Any = None,
    redirect_tools_map: dict[str, BaseTool] | None = None,
) -> dict[str, Any]:
    """执行 ReAct 主循环，返回 react_final 字典。

    停止信号优先级：
    L1: LLM 调用 finish_react 工具（最优，携带结构化元数据）
    L2: LLM 不产生 tool_calls，直接文字回答
    L3: 超出 max_rounds 轮数
    """
    if max_rounds is None:
        max_rounds = int(os.getenv("DATACLOUD_REACT_MAX_ROUNDS", str(_DEFAULT_MAX_ROUNDS)))

    # ── 请求追踪 ID：串联本次问答的所有工具调用和 SQL ─────────────────────────
    from datacloud_data_sdk.trace_context import current_trace_id as _trace_id_var

    _trace_id = uuid.uuid4().hex[:8]
    _trace_token = _trace_id_var.set(_trace_id)

    # ── 日志：打印本轮用户提问 ──────────────────────────────────────────────────
    _user_query_log = str(state.get("user_query") or state.get("enriched_query") or "")
    logger.warning("[%s] ════ USER_QUERY: %s", _trace_id, _user_query_log)

    # ── LLM 失败断点检测：前次请求模型全不可用时保存了断点，本次恢复 ──────────────
    _session_id = str(getattr(gateway_context, "session_id", "") or "") if gateway_context else ""
    _redis_client = (
        (getattr(gateway_context, "redis", None) or getattr(gateway_context, "_redis_client", None))
        if gateway_context
        else None
    )
    from datacloud_analysis.orchestration.execution.llm_checkpoint import (
        delete_llm_failure_checkpoint,
        load_llm_failure_checkpoint,
    )

    _llm_failure_ckpt = await load_llm_failure_checkpoint(_redis_client, _session_id)
    if _llm_failure_ckpt is not None:
        logger.warning(
            "[LLM] 检测到 LLM 失败断点，从断点恢复 session=%s completed_steps=%d",
            _session_id,
            _llm_failure_ckpt.get("completed_steps", 0),
        )
        # 补充上次请求时保存的 state 字段（如 confirmed_terms 等上下文）
        _ckpt_state: dict = _llm_failure_ckpt.get("state_snapshot") or {}
        for _k, _v in _ckpt_state.items():
            if not state.get(_k):
                state[_k] = _v
        # 消费后立即删除，避免影响后续正常请求
        await delete_llm_failure_checkpoint(_redis_client, _session_id)

    # tools_map 包含 finish_react（LLM 可见工具集）
    tools_map: dict[str, BaseTool] = {t.name: t for t in tools_list}
    tools_map["finish_react"] = finish_react

    llm = _build_llm(state)
    # bind_tools 仅绑定 LLM 可见工具（不含 redirect_tools，避免 LLM 直接调用内部路由工具）
    llm_with_tools = llm.bind_tools(list(tools_map.values()))

    # 备用模型（每次请求独立构建，不缓存；未配置时为 None）
    from datacloud_analysis.orchestration.execution.llm_retry import _build_fallback_llm as _bfl

    _fallback_llm = _bfl()
    fallback_llm_with_tools = (
        _fallback_llm.bind_tools(list(tools_map.values())) if _fallback_llm else None
    )

    # redirect_tools：仅供 before_callback redirect 使用，不暴露给 LLM
    # 在 bind_tools 之后才合并，确保 LLM 看不到这些工具
    if redirect_tools_map:
        tools_map.update(redirect_tools_map)

    # 检测是否resume：state中有react_checkpoint标记
    react_checkpoint = state.get("react_checkpoint")
    if react_checkpoint:
        # 立即清除state中的checkpoint，避免下次问答误用
        state["react_checkpoint"] = None
        # Resume模式：恢复messages和round_idx
        # 注意：checkpoint里的messages是序列化的dict，需要重建Message对象
        messages_data = react_checkpoint.get("messages", [])
        messages = []
        for msg_data in messages_data:
            if isinstance(msg_data, dict):
                msg_type = msg_data.get("type")
                if msg_type == "system":
                    messages.append(SystemMessage(content=msg_data.get("content", "")))
                elif msg_type == "human":
                    messages.append(HumanMessage(content=msg_data.get("content", "")))
                elif msg_type == "ai":
                    messages.append(
                        AIMessage(
                            content=msg_data.get("content", ""),
                            tool_calls=msg_data.get("tool_calls", []),
                        )
                    )
                elif msg_type == "tool":
                    messages.append(
                        ToolMessage(
                            content=msg_data.get("content", ""),
                            tool_call_id=msg_data.get("tool_call_id", ""),
                        )
                    )
            else:
                messages.append(msg_data)

        start_round = react_checkpoint.get("round_idx", 0)
        _last_query_data = react_checkpoint.get("last_query_data")
        logger.info(
            "[react_loop] RESUME from checkpoint: round=%d messages=%d", start_round, len(messages)
        )
    else:
        # 首次执行：初始化messages
        # Prompt Caching：仅 Anthropic 协议支持 cache_control，OpenAI 兼容协议退回纯字符串
        messages: list = [
            _build_system_message(system_prompt, stable_system_prompt, dynamic_prompt)
        ]
        conv = _conversation_messages_for_llm(state)
        if conv:
            messages.extend(conv)
            # [DIAG] 诊断日志：打印历史消息内容预览
            for _i, _m in enumerate(conv):
                logger.warning(
                    "[react_loop DIAG] seeded conv[%d] type=%s preview=%r",
                    _i,
                    type(_m).__name__,
                    str(getattr(_m, "content", ""))[:200],
                )
            logger.info(
                "[react_loop] seeded from state.messages: %d human/ai message(s)", len(conv)
            )
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

        # ---- resume replay: 方案 B — 从 LangGraph State 恢复中断上下文 ----
        # resume 检测：从 LangGraph State 读取中断上下文（方案 B，跨实例/重启可靠）
        _resume_ctx: dict[str, Any] | None = None
        _state_msgs = state.get("react_messages")
        if _state_msgs is not None:
            _resume_ctx = {
                "messages": _deserialize_messages(_state_msgs),
                "pending_tool_calls": list(state.get("react_pending_tool_calls") or []),
                "round_idx": int(state.get("react_round_idx") or 0),
                "last_query_data": state.get("react_last_query_data"),
            }
            # 消费后立即清除，避免下次问答误用
            state["react_messages"] = None
            state["react_pending_tool_calls"] = None
            state["react_round_idx"] = None
            state["react_last_query_data"] = None
            logger.info(
                "[react_loop] resume check: hit state react_messages messages=%d pending=%d round=%d",
                len(_state_msgs),
                len(_resume_ctx["pending_tool_calls"]),
                _resume_ctx["round_idx"],
            )
        else:
            logger.info("[react_loop] resume check: no react_messages in state, fresh start")
        if _resume_ctx is not None:
            messages = list(_resume_ctx["messages"])
            _last_query_data = _resume_ctx.get("last_query_data")
            pending_tool_calls: list[dict[str, Any]] = list(_resume_ctx["pending_tool_calls"])
            start_round = int(_resume_ctx.get("round_idx", 0))
            logger.info(
                "[react_loop] resume replay: restored %d messages, %d pending tool_calls, "
                "round=%d msg_types=%s",
                len(messages),
                len(pending_tool_calls),
                start_round + 1,
                [type(m).__name__ for m in messages],
            )
            # 设置 resume replay 信号，让 tool 内部知道当前是 resume 重放
            _resume_token = is_resume_replay.set(True)
            try:
                for tc in pending_tool_calls:
                    _t0 = time.monotonic()
                    tool_id, result = await dispatch_tool(
                        tc, tools_map, state, gateway_context=gateway_context, loader=loader
                    )
                    logger.info(
                        "[react_loop] resume replay: tool=%s elapsed=%.3fs",
                        tc.get("name", "?"),
                        time.monotonic() - _t0,
                    )

                    if isinstance(result, dict):
                        data_block = (
                            result.get("data") if isinstance(result.get("data"), dict) else result
                        )
                        if (
                            isinstance(data_block, dict)
                            and "records" in data_block
                            and "meta" in data_block
                        ):
                            _last_query_data = data_block

                    if isinstance(result, dict) and result.get("__finish__"):
                        return {
                            "react_final": {**result, "stop_reason": "finish_tool"},
                            "react_rounds": start_round + 1,
                        }

                    messages.append(
                        ToolMessage(
                            content=_compress_tool_result(result, tc["name"]),
                            tool_call_id=str(tc.get("id") or ""),
                        )
                    )
            finally:
                is_resume_replay.reset(_resume_token)
            # 从下一轮继续
            start_round += 1
        else:
            start_round = 0

    # ── TTFB 计时起点：执行阶段（react_loop LLM 调用）正式开始 ──────────────────
    if gateway_context is not None and hasattr(gateway_context, "mark_execution_start"):
        gateway_context.mark_execution_start()

    for round_idx in range(start_round, max_rounds):
        logger.info("[react_loop] round=%d/%d", round_idx + 1, max_rounds)

        # 每轮 LLM 思考段生成独立 message_id：
        # 同一轮内的所有 thinking/stream token 归属同一条消息气泡；
        # 工具调用完成后进入下一轮时切换新 ID，实现消息分段隔离。
        _thinking_message_id = uuid.uuid4().hex[:12]

        # Resume时跳过LLM调用，直接用checkpoint里的ai_msg
        _skip_checkpoint_this_round = False  # 本轮是否跳过checkpoint存储（resume时）
        try:
            if react_checkpoint and round_idx == start_round:
                ai_msg_data = react_checkpoint.get("ai_msg")
                if ai_msg_data:
                    # 从dict重建AIMessage对象（messages已包含，无需append）
                    if isinstance(ai_msg_data, dict):
                        ai_msg = AIMessage(
                            content=ai_msg_data.get("content", ""),
                            tool_calls=ai_msg_data.get("tool_calls", []),
                        )
                    else:
                        ai_msg = ai_msg_data
                    logger.info(
                        "[react_loop] RESUME: reuse ai_msg from checkpoint (tool_calls=%d)",
                        len(getattr(ai_msg, "tool_calls", [])),
                    )
                    _did_stream = False
                else:
                    # Checkpoint损坏，重新调用LLM（流式）
                    messages_window = _trim_messages_window(messages)
                    ai_msg, _did_stream = await _invoke_llm_with_fallback(
                        llm_with_tools,
                        fallback_llm_with_tools,
                        messages_window,
                        gateway_context,
                        state=state,
                        round_idx=round_idx,
                        thinking_message_id=_thinking_message_id,
                    )
                    messages.append(ai_msg)
                react_checkpoint = None  # 清除局部变量，后续轮次正常执行
                _skip_checkpoint_this_round = True  # 本轮是resume，跳过checkpoint存储
            else:
                messages_window = _trim_messages_window(messages)
                ai_msg, _did_stream = await _invoke_llm_with_fallback(
                    llm_with_tools,
                    fallback_llm_with_tools,
                    messages_window,
                    gateway_context,
                    state=state,
                    round_idx=round_idx,
                    thinking_message_id=_thinking_message_id,
                )
                messages.append(ai_msg)
        except _LlmUnavailableError as _llm_err:
            # 引导文案已由 _invoke_llm_with_fallback 推送，此处直接返回
            return {
                "react_final": {
                    "result_type": "text",
                    "answer": str(_llm_err),
                    "stop_reason": "llm_unavailable",
                    "answer_streamed": True,
                },
                "react_rounds": round_idx + 1,
                "react_checkpoint": None,
            }

        if not getattr(ai_msg, "tool_calls", None):
            # L2: 无 tool_calls，直接文字结束
            logger.info("[react_loop] stop: no_tool_call at round=%d", round_idx + 1)
            if _last_query_data is not None:
                logger.info(
                    "[react_loop] no_tool_call: force query_result with cached data (records=%d has_file=%s)",
                    len(_last_query_data.get("records") or []),
                    bool(_last_query_data.get("file")),
                )
                answer_text = str(ai_msg.content or "")
                if (
                    any(token in answer_text for token in ("records", "result_type", "pagination"))
                    or len(answer_text) > 800
                ):
                    answer_text = ""
                return {
                    "react_final": {
                        "result_type": "query_result",
                        "answer": answer_text,
                        "query_data": _last_query_data,
                        "stop_reason": "no_tool_call_with_query_data",
                        "answer_streamed": _did_stream,
                    },
                    "react_rounds": round_idx + 1,
                    "react_checkpoint": None,
                }
            return {
                "react_final": {
                    "result_type": "text",
                    "answer": str(ai_msg.content or ""),
                    "stop_reason": "no_tool_call",
                    "answer_streamed": _did_stream,
                },
                "react_rounds": round_idx + 1,
                "react_checkpoint": None,
            }
        for tc_idx, tc in enumerate(ai_msg.tool_calls):
            # 检查是否是delegate工具（可能interrupt）
            tool_name = tc.get("name", "")
            t_delegate = tools_map.get(tool_name)
            is_delegate = t_delegate is not None and getattr(
                t_delegate, "_is_agent_delegate", False
            )

            # 如果是delegate工具，保存checkpoint到state（顶层字段）
            # resume模式下跳过，避免重复存储
            if is_delegate and not _skip_checkpoint_this_round:
                # 序列化messages：提取关键字段
                serialized_messages = []
                for msg in messages:
                    if isinstance(msg, SystemMessage):
                        serialized_messages.append({"type": "system", "content": msg.content})
                    elif isinstance(msg, HumanMessage):
                        serialized_messages.append({"type": "human", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        serialized_messages.append(
                            {
                                "type": "ai",
                                "content": msg.content,
                                "tool_calls": getattr(msg, "tool_calls", []),
                            }
                        )
                    elif isinstance(msg, ToolMessage):
                        serialized_messages.append(
                            {
                                "type": "tool",
                                "content": msg.content,
                                "tool_call_id": msg.tool_call_id,
                            }
                        )

                # 序列化ai_msg
                serialized_ai_msg = {
                    "type": "ai",
                    "content": ai_msg.content,
                    "tool_calls": getattr(ai_msg, "tool_calls", []),
                }

                checkpoint_data = {
                    "messages": serialized_messages,
                    "round_idx": round_idx,
                    "ai_msg": serialized_ai_msg,
                    "last_query_data": _last_query_data,
                }
                state["react_checkpoint"] = checkpoint_data
                logger.info("[react_loop] saved checkpoint to state before delegate tool")

            try:
                tool_id, result = await dispatch_tool(
                    tc, tools_map, state, gateway_context=gateway_context, loader=loader
                )
            except GraphBubbleUp:
                # 方案 B：将中断上下文写入 LangGraph State（由 checkpoint 跨实例/重启持久化）
                _pending = list(ai_msg.tool_calls[tc_idx:])
                state["react_messages"] = _serialize_messages(messages)
                state["react_pending_tool_calls"] = _pending
                state["react_round_idx"] = round_idx
                state["react_last_query_data"] = _last_query_data
                _s_key = (
                    str(getattr(gateway_context, "session_id", "") or "") if gateway_context else ""
                )
                logger.info(
                    "[react_loop] interrupt: saving to state session=%s messages=%d "
                    "pending=%d round=%d msg_types=%s",
                    _s_key,
                    len(messages),
                    len(_pending),
                    round_idx + 1,
                    [type(m).__name__ for m in messages],
                )
                raise

            # 缓存 data_query 结果：识别含 records+meta 的 data block
            if isinstance(result, dict):
                data_block = result.get("data") if isinstance(result.get("data"), dict) else result
                if (
                    isinstance(data_block, dict)
                    and "records" in data_block
                    and "meta" in data_block
                ):
                    _last_query_data = data_block
                    logger.info(
                        "[react_loop] cached query_data: records=%d has_file=%s",
                        len(data_block.get("records") or []),
                        bool(data_block.get("file")),
                    )

            # L1: finish_react 终止
            if isinstance(result, dict) and result.get("__finish__"):
                logger.info("[react_loop] stop: finish_tool at round=%d", round_idx + 1)
                final = {**result, "stop_reason": "finish_tool", "answer_streamed": _did_stream}
                if _last_query_data is not None:
                    logger.info(
                        "[react_loop] finish_tool: cached query_data found (records=%d has_file=%s)",
                        len(_last_query_data.get("records") or []),
                        bool(_last_query_data.get("file")),
                    )
                    # [DIAG] 记录 query_data 第一条记录，便于排查轮次是否对应
                    _qd_recs = _last_query_data.get("records") or []
                    logger.warning(
                        "[react_loop DIAG] finish_react query_data first_rec=%s",
                        str(_qd_recs[0])[:120] if _qd_recs else "N/A",
                    )
                    # 如果 LLM 未显式选择 query_result，也强制走结构化输出
                    if final.get("result_type") not in {"query_result", "csv_file", "json_file"}:
                        final["result_type"] = "query_result"
                    if final.get("result_type") == "query_result":
                        final["query_data"] = _last_query_data
                        # 如已返回结构化表格，避免文本与表格矛盾：
                        # 1. answer 含 JSON 关键词或超长 → 清空
                        # 2. answer 含 Markdown 表格（LLM 误把表格写进 answer）→ 清空，
                        #    防止 _stream_llm_call 已流式推送 + format_result 再次渲染导致重复
                        answer = str(final.get("answer") or "")
                        if answer:
                            _is_json_like = (
                                any(
                                    token in answer
                                    for token in ("records", "result_type", "pagination")
                                )
                                or len(answer) > 800
                            )
                            _is_md_table = answer.count("|") > 6 and (
                                "| --- |" in answer
                                or "| --- " in answer
                                or "|---|" in answer
                                or "|---" in answer
                            )
                            if _is_json_like or _is_md_table:
                                if _is_md_table:
                                    logger.warning(
                                        "[react_loop] answer contains markdown table, clearing to avoid "
                                        "double render (streamed=%s len=%d)",
                                        final.get("answer_streamed"),
                                        len(answer),
                                    )
                                final["answer"] = ""
                                answer = ""
                            meta = (
                                _last_query_data.get("meta")
                                if isinstance(_last_query_data, dict)
                                else {}
                            )
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
                            if (
                                has_count_col
                                and has_row_data
                                and ("未" in answer and "数量" in answer)
                            ):
                                final["answer"] = "已返回结果表，详见下方数据。"
                return {
                    "react_final": final,
                    "react_rounds": round_idx + 1,
                    "react_checkpoint": None,
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
            "react_checkpoint": None,
        }
    return {
        "react_final": {
            "result_type": "text",
            "answer": _summarize_last_output(messages),
            "stop_reason": "max_rounds",
        },
        "react_rounds": max_rounds,
        "react_checkpoint": None,
    }
