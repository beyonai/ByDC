"""HookAwareToolNode：在 prebuilt ToolNode 基础上注入 before/after_call_back 钩子。

继承 langgraph.prebuilt.ToolNode，覆写 ainvoke（公开 API，比 _run_one 稳定），
在工具执行前后调用插件钩子，ClarificationNeededError 转换为 Command 路由至澄清子流程。
"""

from __future__ import annotations

import ast
import contextlib
import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from datacloud_analysis.tool_hook_plugins import get_tool_hook_plugin_manager
from datacloud_analysis.tool_hook_plugins.types import ClarificationNeededError, HookContext

logger = logging.getLogger(__name__)


class HookAwareToolNode(ToolNode):
    """在 prebuilt ToolNode 基础上注入 before/after_call_back 钩子。

    执行流程：
    1. before_call_back：逐工具构建 HookContext，调用 run_before，可修改参数或触发澄清。
    2. ClarificationNeededError → Command(goto="analyze_clarify")，中断当前工具执行链。
    3. 将修改后的 tool_params patch 到 AIMessage.tool_calls，传入 super().ainvoke。
    4. after_call_back：遍历本轮新增 ToolMessage，调用 run_after。
    5. 检测 query_data block（records+meta）写入 react_last_query_data。
    """

    def __init__(
        self,
        tools: list[Any],
        *,
        loader: Any = None,
        gateway_context: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(tools, **kwargs)
        self._loader = loader
        self._gw_ctx = gateway_context

    async def ainvoke(
        self,
        state: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        # 兼容 dict / AgentState
        state_dict: dict[str, Any] = dict(state) if isinstance(state, dict) else state

        messages = list(state_dict.get("messages") or [])
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        _has_clarify_fp = bool(state_dict.get("clarification_formatted_params"))
        _last_ai_calls = list(last_ai.tool_calls or []) if last_ai else []
        logger.info(
            "[HookAwareToolNode] ainvoke entry: last_ai=%s tool_calls_count=%d"
            " clarification_formatted_params=%s",
            type(last_ai).__name__ if last_ai else "None",
            len(_last_ai_calls),
            _has_clarify_fp,
        )
        if last_ai is None or not (last_ai.tool_calls or []):
            logger.warning(
                "[HookAwareToolNode] early-exit: no tool_calls on last AIMessage"
                " → skipping hooks, calling super().ainvoke directly"
                " last_ai=%s",
                type(last_ai).__name__ if last_ai else "None",
            )
            return await super().ainvoke(state_dict, config, **kwargs)

        # ── Checkpoint replay guard ─────────────────────────────────────────────────────────────
        # OpenGauss checkpoint blob 丢失时，tools 节点会被错误激活（而非 user_clarify 节点恢复）。
        # 检测特征：pending_clarification_context 已设置（等待澄清）+ clarification_formatted_params 未设置
        # （user_clarify_node 尚未运行并写入格式化参数），说明当前调用属于脏 checkpoint replay。
        # 直接 Command(goto=analyze_clarify) 跳过工具执行和 7 秒 SDK 分析，回到澄清子流程。
        _pending_ctx_raw: dict[str, Any] | None = (
            dict(state_dict["pending_clarification_context"])
            if isinstance(state_dict.get("pending_clarification_context"), dict)
            else None
        )
        if _pending_ctx_raw and not state_dict.get("clarification_formatted_params"):
            logger.warning(
                "[HookAwareToolNode] REPLAY GUARD: pending_clarification_context set"
                " clarification_formatted_params=None → routing to analyze_clarify"
                " without tool execution tool=%s",
                str(_pending_ctx_raw.get("tool_name") or ""),
            )
            return Command(
                update={
                    "execution_status": "clarify_needed",
                    "pending_clarification_context": _pending_ctx_raw,
                },
                goto="analyze_clarify",
            )

        # Per-request gateway_context：config 优先，构造函数注入次之
        _gw_ctx = (
            ((config or {}).get("configurable") or {}).get("gateway_context") or self._gw_ctx  # type: ignore[attr-defined]
        )

        hook_manager = get_tool_hook_plugin_manager()
        patched_calls: list[dict[str, Any]] = []

        # before_call_back 会消费 complex_conditions（路由元字段），提前从原始 args 中保存，
        # 供后续推送"工具入参"时还原展示，不影响实际执行参数。
        original_complex_conditions_map: dict[str, list[str]] = {
            str(tc.get("id") or ""): list((tc.get("args") or {}).get("complex_conditions") or [])
            for tc in last_ai.tool_calls
        }

        for tc in last_ai.tool_calls:
            tool_name = str(tc.get("name") or "")
            ctx: HookContext = {
                "tool_name": tool_name,
                "tool_params": dict(tc.get("args") or {}),
                "session_id": str(state_dict.get("agent_id") or ""),
                "user_query": str(state_dict.get("user_query") or ""),
                "knowledge_snippets": list(state_dict.get("knowledge_snippets") or []),
                "knowledge_payload": dict(state_dict.get("knowledge_payload") or {}),
                "term_context": list(state_dict.get("confirmed_terms") or []),
                "metadata": {"loader": self._loader, "state": state_dict},
            }

            try:
                ctx, _before_decision = await hook_manager.run_before(ctx)
            except ClarificationNeededError as exc:
                logger.info(
                    "[HookAwareToolNode] ClarificationNeededError tool=%s round=%s",
                    tool_name,
                    state_dict.get("react_round_idx"),
                )
                return Command(
                    update={
                        "execution_status": "clarify_needed",
                        "pending_clarification_context": {
                            **exc.context,
                            "tool_name": tool_name,
                            "react_round_idx": int(state_dict.get("react_round_idx") or 0),
                        },
                    },
                    goto="analyze_clarify",
                )

            # query_* 工具剥离 compute-only 字段，防止插件内部重新注入空列表
            tp = dict(ctx.get("tool_params") or {})
            if tool_name.startswith("query_"):
                for _sf in ("dimensions", "metrics", "having"):
                    tp.pop(_sf, None)
            logger.info(
                "[HookAwareToolNode] tool=%s patched_args_keys=%s dimensions=%s metrics=%s",
                tool_name,
                sorted(tp.keys()),
                tp.get("dimensions"),
                tp.get("metrics"),
            )
            patched_calls.append({**tc, "args": tp})

        # 用修改后的 tool_calls 替换最后一条 AIMessage（Pydantic 不可变，必须 model_copy）
        patched_ai = last_ai.model_copy(update={"tool_calls": patched_calls})
        patched_state = {**state_dict, "messages": [*messages[:-1], patched_ai]}

        # tool_call_id → display_params，供工具执行后推送详情使用。
        # complex_conditions 已被 before_call_back 消费剥除，此处从原始入参还原，仅用于展示。
        # query_*/compute_* 工具始终展示该字段（含空列表），便于确认 LLM 是否判定为复杂查询。
        call_params_map: dict[str, dict[str, Any]] = {}
        for tc in patched_calls:
            tc_id = str(tc.get("id") or "")
            display_params = dict(tc.get("args") or {})
            tool_name_disp = str(tc.get("name") or "")
            orig_cc = original_complex_conditions_map.get(tc_id)
            if tool_name_disp.startswith(("query_", "compute_")):
                display_params["complex_conditions"] = orig_cc or []
            elif orig_cc:
                display_params["complex_conditions"] = orig_cc
            call_params_map[tc_id] = display_params

        # 实际工具执行（走 prebuilt ToolNode 原有逻辑）
        result = await super().ainvoke(patched_state, config, **kwargs)

        result_dict: dict[str, Any] = dict(result) if isinstance(result, dict) else {"messages": []}

        # after_call_back：遍历本轮产出的 ToolMessage
        for msg in result_dict.get("messages") or []:
            if not isinstance(msg, ToolMessage):
                continue
            after_ctx: HookContext = {
                "tool_name": msg.name or "",
                "tool_params": {},
                "tool_output": msg.content,
            }
            try:
                await hook_manager.run_after(after_ctx)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[HookAwareToolNode] run_after failed tool=%s: %s", msg.name, exc)

        # 推送工具调用详情（工具名 / 工具入参 / 工具返回）至 gateway_context，与 V0.3 保持一致
        if _gw_ctx is not None:
            from datacloud_analysis.orchestration.execution.tool_wrapper import (  # noqa: PLC0415
                _emit_tool_detail,
            )

            for msg in result_dict.get("messages") or []:
                if not isinstance(msg, ToolMessage) or (msg.name or "") == "finish_react":
                    continue
                params = call_params_map.get(str(msg.tool_call_id or ""), {})
                try:
                    async with _gw_ctx.sub_step(msg.name or "tool"):
                        if params:
                            await _emit_tool_detail(_gw_ctx, "工具入参", params)
                        # 将 msg.content（可能是 Python repr 字符串）解析回 dict，
                        # 保证 coerce_stream_chunk_text 走 dump_json 而非原样透传。
                        _raw = str(msg.content or "")
                        _parsed = _try_parse_to_dict(_raw) if _raw else None
                        _tool_out: Any = _parsed if _parsed is not None else _raw
                        await _emit_tool_detail(_gw_ctx, "工具返回", _tool_out)
                except Exception as detail_exc:  # noqa: BLE001
                    logger.debug(
                        "[HookAwareToolNode] emit tool detail failed tool=%s: %s",
                        msg.name,
                        detail_exc,
                    )

        # 检测 query_data block，为 finish_react_node 写入 react_last_query_data
        query_data = _extract_query_data_from_tool_messages(result_dict.get("messages") or [])
        if query_data is not None:
            result_dict["react_last_query_data"] = query_data

        return result_dict


# ── 辅助函数 ───────────────────────────────────────────────────────────────────


def _extract_query_data_from_tool_messages(
    messages: list[Any],
) -> dict[str, Any] | None:
    """从本轮 ToolMessage content 中检测 records+meta 结构，返回 query_data 或 None。"""
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        if msg.name == "finish_react":
            continue
        data = _try_parse_query_data(str(msg.content or ""))
        if data is not None:
            logger.info(
                "[HookAwareToolNode] query_data detected tool=%s records=%d",
                msg.name,
                len(data.get("records") or []),
            )
            return data
    return None


_DECIMAL_RE = re.compile(r"Decimal\('([^']+)'\)")
_NONLITERAL_RE = re.compile(r"\bdatetime\.(?:datetime|date|time)\b\([^)]*\)")


def _try_parse_to_dict(content: str) -> dict[str, Any] | None:
    """将 ToolMessage content 字符串解析回 dict，支持 JSON 和 Python repr 格式。

    用于 emit 前将 msg.content（prebuilt ToolNode 存储的字符串）还原为 dict，
    保证 coerce_stream_chunk_text 走 dump_json 路径而非原样透传字符串。
    """
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        cleaned = _DECIMAL_RE.sub(r"\1", content)
        cleaned = _NONLITERAL_RE.sub("None", cleaned)
        parsed = ast.literal_eval(cleaned)
        if isinstance(parsed, dict):
            return parsed  # type: ignore[return-value]
    except (ValueError, SyntaxError):
        pass
    return None


def _try_parse_query_data(content: str) -> dict[str, Any] | None:
    """尝试将 ToolMessage content 解析为 dict 并检测 records+meta 结构。

    支持 JSON 字符串和 Python repr 字符串（含 Decimal 值的工具返回经 str() 序列化后的格式）。
    """
    parsed: Any = None
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        # 兜底：Python repr，先剥离 Decimal('x') 和 datetime.*(…) 再 literal_eval
        try:
            cleaned = _DECIMAL_RE.sub(r"\1", content)
            cleaned = _NONLITERAL_RE.sub("None", cleaned)
            parsed = ast.literal_eval(cleaned)
        except (ValueError, SyntaxError):
            return None
    # 解包 MCP list 格式: [{"type": "text", "text": "...json..."}]
    if isinstance(parsed, list):
        for block in parsed:
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                with contextlib.suppress(json.JSONDecodeError, ValueError):
                    parsed = json.loads(block["text"])
                break
    if not isinstance(parsed, dict):
        return None
    # 解包 MCP dict 格式: {"content": [{"type": "text", "text": "...json..."}]}
    if isinstance(parsed.get("content"), list):
        for block in parsed["content"]:
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                with contextlib.suppress(json.JSONDecodeError, ValueError):
                    parsed = json.loads(block["text"])
                break
    if not isinstance(parsed, dict):
        return None
    # 支持 {"data": {...}} 嵌套 或 直接 {"records": [...], "meta": {...}}
    data_block = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
    if (
        isinstance(data_block, dict)
        and isinstance(data_block.get("records"), list)
        and "meta" in data_block
    ):
        return data_block
    return None
