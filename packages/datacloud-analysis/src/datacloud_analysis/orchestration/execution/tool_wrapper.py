from __future__ import annotations
import json
import logging
from typing import Any
from langchain_core.tools import BaseTool
from datacloud_analysis.tool_hook_plugins import get_tool_hook_plugin_manager
from datacloud_analysis.tool_hook_plugins.types import HookContext

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset({"password", "token", "secret", "api_key", "apikey"})

def _sanitize(params: dict[str, Any]) -> str:
    sanitized = {
        k: "***" if any(s in k.lower() for s in _SENSITIVE_KEYS) else v
        for k, v in params.items()
    }
    try:
        return json.dumps(sanitized, ensure_ascii=False, default=str)[:500]
    except Exception:
        return repr(sanitized)[:500]

def _summarize_output(output: Any) -> str:
    """将工具输出截断为可读的思考日志摘要（最多 200 字符）。"""
    if output is None:
        return "（无返回）"
    if isinstance(output, (dict, list)):
        try:
            text = json.dumps(output, ensure_ascii=False, default=str)
        except Exception:
            text = repr(output)
    else:
        text = str(output)
    if len(text) > 200:
        return text[:200] + "..."
    return text

def inject_reason_field(t: BaseTool) -> BaseTool:
    """往工具的 args_schema 注入 reason: str 字段（可选，默认空字符串）。

    同时包装底层 coroutine/func，确保 reason 在传入原始实现前被剥除，
    避免原始函数因收到意外的 reason 关键字参数而抛出 TypeError。
    """
    try:
        from pydantic import BaseModel, Field, create_model  # noqa: PLC0415

        original_schema = t.args_schema
        if original_schema is None:
            return t

        # 创建新的 schema，在顶部插入 reason 字段（可选）
        original_fields = {}
        for field_name, field_info in original_schema.model_fields.items():
            original_fields[field_name] = (field_info.annotation, field_info)

        new_fields = {
            "reason": (str, Field(default="", description="选择本工具的理由")),
            **original_fields,
        }
        NewSchema = create_model(
            f"{original_schema.__name__}WithReason",
            **new_fields,
        )
        t.args_schema = NewSchema

        # 包装底层 coroutine，在调用原始实现前剥除 reason
        if hasattr(t, "coroutine") and t.coroutine is not None:
            _orig_coro = t.coroutine

            async def _coro_strip_reason(**kw: Any) -> Any:
                kw.pop("reason", None)
                return await _orig_coro(**kw)

            t.coroutine = _coro_strip_reason

        # 包装底层 func（同步），同样剥除 reason
        if hasattr(t, "func") and t.func is not None:
            _orig_func = t.func

            def _func_strip_reason(**kw: Any) -> Any:
                kw.pop("reason", None)
                return _orig_func(**kw)

            t.func = _func_strip_reason

    except Exception as exc:
        logger.warning("inject_reason_field failed for tool=%s: %s", getattr(t, "name", "?"), exc)
    return t

class ToolHookError(Exception):
    def __init__(self, decision: dict[str, Any]) -> None:
        self.decision = decision
        super().__init__(str(decision))

async def _emit_thinking(gateway_context: Any, text: str) -> None:
    """向前端推送工具调用思考日志。"""
    if gateway_context is None:
        return
    try:
        from by_framework import EventType, StreamChunkEvent  # type: ignore
        from by_framework.core.protocol.content_type import SseReasonMessageType  # type: ignore
        await gateway_context.emit_chunk(
            StreamChunkEvent(content=text),
            event_type=EventType.REASONING_LOG_START.value,
            content_type=SseReasonMessageType.think_text.value,
        )
    except Exception as exc:
        logger.debug("_emit_thinking failed: %s", exc)


async def dispatch_tool(
    tool_call: dict[str, Any],
    tools_map: dict[str, BaseTool],
    state: Any,
    *,
    gateway_context: Any = None,
) -> tuple[str, Any]:
    """调用工具，串联 before/after hook，记录 reason 日志。

    特殊工具：
    - finish_react：直接返回终止标记，不走 hook
    - ask_user：直接调用，不走 hook（interrupt 会挂起进程）
    """
    tool_name = tool_call["name"]
    raw_params = dict(tool_call.get("args") or {})
    tool_call_id = str(tool_call.get("id") or "")

    # --- 特殊工具：finish_react ---
    if tool_name == "finish_react":
        return tool_call_id, {"__finish__": True, **raw_params}

    # --- 特殊工具：ask_user ---
    if tool_name == "ask_user":
        t = tools_map.get("ask_user")
        if t is None:
            return tool_call_id, "（ask_user 工具未挂载）"
        result = await t.ainvoke(raw_params)
        return tool_call_id, result

    # --- 提取 reason 并记录 ---
    reason = raw_params.pop("reason", "")

    # --- 解包嵌套参数（兜底）：如果 LLM 产生了 {"params": {...}} 嵌套结构，展开它 ---
    if (
        len(raw_params) == 1
        and "params" in raw_params
        and isinstance(raw_params["params"], dict)
    ):
        raw_params = raw_params["params"]

    logger.info(
        "[tool_call] tool=%s reason=%s params=%s",
        tool_name, reason, _sanitize(raw_params),
    )

    # --- 推送工具调用思考日志 ---
    await _emit_thinking(
        gateway_context,
        f"\u6b63\u5728\u8c03\u7528\u5de5\u5177 {tool_name}\uff1a{reason}\n\n",
    )

    # --- 构建 HookContext ---
    ctx: HookContext = {
        "tool_name": tool_name,
        "tool_params": dict(raw_params),
        "session_id": str(state.get("agent_id") or ""),
        "user_query": str(state.get("user_query") or ""),
        "workspace_dir": state.get("workspace_dir"),
        "knowledge_snippets": list(state.get("knowledge_snippets") or []),
        "term_context": list(state.get("confirmed_terms") or []),
    }

    hook_manager = get_tool_hook_plugin_manager()

    # --- before hook ---
    ctx, before_decision = await hook_manager.run_before(ctx)
    if before_decision:
        action = str(before_decision.get("action") or "")
        if action == "short_circuit":
            result_payload = (before_decision.get("result") or {})
            return tool_call_id, result_payload.get("tool_output", "（short_circuit）")
        if action == "fail":
            raise ToolHookError(before_decision)

    # --- 实际工具调用 ---
    t = tools_map.get(tool_name)
    if t is None:
        logger.warning("dispatch_tool: tool '%s' not found in tools_map", tool_name)
        ctx["tool_output"] = None
        ctx["tool_error"] = {"error_type": "ToolNotFound", "message": f"Tool '{tool_name}' not found"}
    else:
        try:
            # 将 gateway_context 注入 InvocationContext，使 SDK 内的 GatewayProgressReporter
            # 能通过 get_gateway_context() 获取到 context 并推送心跳日志
            try:
                from datacloud_data_sdk.context import InvocationContext  # type: ignore
                _inv_ctx: Any = InvocationContext(gateway_context=gateway_context)
                _inv_ctx.__enter__()
                try:
                    output = await t.ainvoke(ctx["tool_params"])
                finally:
                    _inv_ctx.__exit__(None, None, None)
            except ImportError:
                output = await t.ainvoke(ctx["tool_params"])
            ctx["tool_output"] = output
            ctx["tool_error"] = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("dispatch_tool: tool='%s' raised: %s", tool_name, exc)
            ctx["tool_output"] = None
            ctx["tool_error"] = {"error_type": type(exc).__name__, "message": str(exc)}

    # --- after hook ---
    ctx, after_decision = await hook_manager.run_after(ctx)
    if after_decision:
        action = str(after_decision.get("action") or "")
        if action == "recover":
            result_payload = (after_decision.get("result") or {})
            ctx["tool_output"] = result_payload.get("tool_output", ctx.get("tool_output"))
        if action == "fail":
            raise ToolHookError(after_decision)

    # --- 推送工具返回思考日志 ---
    final_output = ctx.get("tool_output")
    if ctx.get("tool_error"):
        err_msg = ctx["tool_error"].get("message", "")
        logger.info("[tool_return] tool=%s error=%s", tool_name, err_msg)
        await _emit_thinking(
            gateway_context,
            f"\u5de5\u5177 {tool_name} \u8fd4\u56de\u9519\u8bef\uff1a{err_msg}\n\n",
        )
    else:
        # 完整打印到 log，供日志检查
        try:
            full_output_str = json.dumps(final_output, ensure_ascii=False, default=str)
        except Exception:
            full_output_str = repr(final_output)
        logger.info("[tool_return] tool=%s output=%s", tool_name, full_output_str)

        output_preview = _summarize_output(final_output)
        await _emit_thinking(
            gateway_context,
            f"\u5de5\u5177 {tool_name} \u8fd4\u56de\uff1a{output_preview}\n\n",
        )

        # --- data_query 结构识别：records+meta 或 file.file_url ---
        if isinstance(final_output, dict):
            # 兼容两种包装：{data: {...}} 或直接 {records, meta, ...}
            data_block = final_output.get("data") if isinstance(final_output.get("data"), dict) else final_output
            if isinstance(data_block, dict):
                records = data_block.get("records")
                file_block = data_block.get("file") if isinstance(data_block.get("file"), dict) else None
                file_url = str(file_block.get("file_url", "") if file_block else "").strip()

                if file_url and "file_url" not in final_output:
                    # overflow 场景：有 CSV 文件，告知 LLM 用 result_type=query_result
                    final_output = dict(final_output)
                    final_output["file_url"] = file_url
                    final_output["_hint"] = (
                        f"\u6570\u636e\u91cf\u8f83\u5927\uff0c\u5df2\u5b58\u5165\u6587\u4ef6 {file_url}\u3002"
                        "\u8bf7\u8c03\u7528 finish_react \u65f6\u4f7f\u7528 result_type=query_result\uff0c"
                        "\u7cfb\u7edf\u4f1a\u81ea\u52a8\u900f\u4f20\u5b8c\u6574\u7ed3\u6784\u3002"
                    )
                    logger.info("[tool_return] data_query file_url detected: %s", file_url)
                elif isinstance(records, list) and records and "records" not in final_output:
                    # 小数据场景：records 直接在内存里，告知 LLM 用 result_type=query_result
                    final_output = dict(final_output)
                    final_output["_hint"] = (
                        "\u6570\u636e\u5df2\u8fd4\u56de records \u5b57\u6bb5\u3002"
                        "\u8bf7\u8c03\u7528 finish_react \u65f6\u4f7f\u7528 result_type=query_result\uff0c"
                        "\u7cfb\u7edf\u4f1a\u81ea\u52a8\u900f\u4f20\u5b8c\u6574\u7ed3\u6784\uff0c\u65e0\u9700\u624b\u52a8\u5e8f\u5217\u5316\u3002"
                    )
                    logger.info("[tool_return] data_query records detected: count=%d", len(records))

    return tool_call_id, final_output
