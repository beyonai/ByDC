"""② Clarification node — HITL 追问澄清（design §4.2）.

Responsibilities
----------------
- 对 ambiguous_terms 中每个词逐一追问用户。
- 用户回复后写入 confirmed_terms / session_alias_map，并异步持久化别名。
- 支持多轮：每次 interrupt 只问剩余未解决的词。
- 连续两次空回复则跳过，带不完整结果继续执行。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from by_framework import EventType, StreamChunkEvent
from by_framework.core.protocol.content_type import SseReasonMessageType

from datacloud_analysis.orchestration.state import AgentState

logger = logging.getLogger(__name__)

# 连续空回复次数上限，超过则跳过剩余歧义词继续执行
_MAX_EMPTY_REPLIES = 2


async def clarification_node(
    state: AgentState,
    gateway_context: Any = None,
) -> dict[str, Any]:
    """追问用户澄清歧义术语，写入别名，返回更新后的 confirmed_terms / ambiguous_terms。

    Args:
        state: 当前 AgentState，ambiguous_terms 非空时才会进入本节点。
        gateway_context: 可选 AgentContext，用于推送思考日志。

    Returns:
        state 更新：confirmed_terms（追加）、ambiguous_terms（清空或剩余）、
        session_alias_map（追加）、query_mode / target_tool（可能更新）。
    """
    from langgraph.types import interrupt as lg_interrupt  # noqa: PLC0415

    ambiguous_terms: list[dict[str, Any]] = list(state.get("ambiguous_terms") or [])
    confirmed_terms: list[dict[str, Any]] = list(state.get("confirmed_terms") or [])
    session_alias_map: dict[str, str] = dict(state.get("session_alias_map") or {})
    query_mode: str = state.get("query_mode") or "analysis"
    target_tool: str = state.get("target_tool") or ""
    intent_text = str(state.get("intent") or "")
    tool_params_raw = state.get("tool_params")
    tool_params: dict[str, Any] = tool_params_raw if isinstance(tool_params_raw, dict) else {}

    if not ambiguous_terms:
        return {}

    empty_reply_count = 0
    newly_confirmed: list[dict[str, Any]] = []
    clarification_results: dict[str, Any] = {}

    remaining = list(ambiguous_terms)
    while remaining:
        term_info = remaining[0]
        mention = term_info.get("mention", "")
        candidates: list[dict[str, Any]] = term_info.get("candidates", [])

        # 构造追问提示
        if candidates:
            options_text = "\n".join(
                f"  {i+1}. {c['term_name']}（{c['term_type_code']}）"
                for i, c in enumerate(candidates[:5])
            )
            prompt = (
                f"「{mention}」有多个匹配，请选择您指的是哪个：\n"
                f"{options_text}\n"
                f"请输入序号（1-{min(len(candidates), 5)}），或直接描述您的意思，或回车跳过。"
            )
        else:
            prompt = (
                f"「{mention}」未找到匹配的业务术语，请描述它的含义，或回车跳过。"
            )

        user_reply: str = lg_interrupt(prompt)
        user_reply = (user_reply or "").strip()

        if not user_reply:
            empty_reply_count += 1
            if empty_reply_count >= _MAX_EMPTY_REPLIES:
                logger.info(
                    "clarification_node: %d consecutive empty replies, skipping remaining %d terms",
                    empty_reply_count, len(remaining),
                )
                break
            # 第一次空回复不跳过当前词，允许用户下一轮继续补充。
            continue

        empty_reply_count = 0

        # 解析用户回复
        resolved_candidate: dict[str, Any] | None = None
        if candidates and user_reply.isdigit():
            idx = int(user_reply) - 1
            if 0 <= idx < len(candidates):
                resolved_candidate = candidates[idx]

        if resolved_candidate is not None:
            confirmed_entry = {
                "mention": mention,
                "term_id": resolved_candidate["term_id"],
                "term_name": resolved_candidate["term_name"],
                "term_type_code": resolved_candidate.get("term_type_code", ""),
                "confidence": 1.0,
                "source": "clarification",
            }
            newly_confirmed.append(confirmed_entry)
            session_alias_map[mention] = resolved_candidate["term_id"]
            clarification_results[mention] = resolved_candidate
        else:
            # 用户提供了自定义描述
            confirmed_entry = {
                "mention": mention,
                "term_id": "",
                "term_name": mention,
                "term_type_code": "USER_DEFINED",
                "confidence": 1.0,
                "source": "clarification_custom",
                "user_description": user_reply,
            }
            newly_confirmed.append(confirmed_entry)
            session_alias_map[mention] = mention
            clarification_results[mention] = user_reply

        remaining.pop(0)

    # 异步持久化别名（fire-and-forget）
    if clarification_results:
        user_id: str | None = None
        if gateway_context is not None:
            user_id = getattr(gateway_context, "user_id", None)
        if user_id:
            try:
                from datacloud_analysis.tools.knowledge import save_clarification_results

                asyncio.create_task(
                    save_clarification_results(clarification_results, user_id)
                )
            except Exception as exc:
                logger.warning("clarification_node: save_clarification_results failed: %s", exc)

    confirmed_terms.extend(newly_confirmed)
    mention_to_term_name = {
        str(item.get("mention")): str(item.get("term_name"))
        for item in newly_confirmed
        if item.get("mention") and item.get("term_name")
    }
    rewritten_intent = _replace_mentions_in_text(intent_text, mention_to_term_name)
    rewritten_tool_params = _replace_mentions_in_params(tool_params, mention_to_term_name)

    await _emit_clarification_summary(gateway_context, newly_confirmed, remaining)

    return {
        "intent": rewritten_intent,
        "tool_params": rewritten_tool_params,
        "confirmed_terms": confirmed_terms,
        "ambiguous_terms": remaining,
        "session_alias_map": session_alias_map,
        "query_mode": query_mode,
        "target_tool": target_tool,
    }


async def _emit_clarification_prompt(
    gateway_context: Any,
    mention: str,
    prompt: str,
) -> None:
    if gateway_context is None:
        return
    await gateway_context.emit_chunk(
        StreamChunkEvent(content="术语澄清"),
        event_type=EventType.REASONING_LOG_DELTA.value,
        content_type=SseReasonMessageType.think_title.value,
    )
    await gateway_context.emit_chunk(
        StreamChunkEvent(content=f"■ 正在澄清：「{mention}」\n{prompt}"),
        event_type=EventType.REASONING_LOG_DELTA.value,
        content_type=SseReasonMessageType.think_text.value,
    )


def _replace_mentions_in_text(text: str, mapping: dict[str, str]) -> str:
    out = text
    for mention, replacement in mapping.items():
        if mention and replacement:
            out = out.replace(mention, replacement)
    return out


def _replace_mentions_in_params(params: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    def _walk(value: Any) -> Any:
        if isinstance(value, str):
            return _replace_mentions_in_text(value, mapping)
        if isinstance(value, dict):
            return {k: _walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_walk(v) for v in value]
        return value

    return _walk(params)


async def _emit_clarification_summary(
    gateway_context: Any,
    newly_confirmed: list[dict[str, Any]],
    remaining: list[dict[str, Any]],
) -> None:
    if gateway_context is None:
        return
    lines = []
    for t in newly_confirmed:
        if t.get("term_id"):
            lines.append(f"  ✓ 「{t['mention']}」→ {t['term_name']}")
        else:
            lines.append(f"  ✓ 「{t['mention']}」→ 自定义描述")
    for t in remaining:
        lines.append(f"  ⚠ 「{t.get('mention', '')}」跳过（仍有歧义）")
    summary = "\n".join(lines) if lines else "无澄清结果"
    await gateway_context.emit_chunk(
        StreamChunkEvent(content=f"■ 澄清完成：\n{summary}"),
        event_type=EventType.REASONING_LOG_DELTA.value,
        content_type=SseReasonMessageType.think_text.value,
    )
