from __future__ import annotations

import json
import logging
from contextlib import nullcontext
from typing import Any

from datacloud_data_sdk.stream_text import coerce_stream_chunk_text
from langchain_core.tools import BaseTool

from datacloud_analysis.tool_hook_plugins import get_tool_hook_plugin_manager
from datacloud_analysis.tool_hook_plugins.types import HookContext
from datacloud_analysis.workspace.runtime import resolve_shared_workspace_dir

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
        from pydantic import BaseModel, Field, create_model  # noqa: PLC0415, F401

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

_THINK_EVENT_TYPE = "reasoningLogDelta"

_THINK_CONTENT_TYPE = "1002"


class ToolHookError(Exception):
    def __init__(self, decision: dict[str, Any]) -> None:
        self.decision = decision
        super().__init__(str(decision))


async def _emit_think(gateway_context: Any, text: str) -> None:
    """在 sub_step 内推送 think_text 内容。"""
    try:
        from by_framework import StreamChunkEvent  # type: ignore
        chunk = StreamChunkEvent(content=text)
    except ImportError:
        chunk = text  # type: ignore[assignment]
    try:
        emit_kwargs: dict[str, Any] = {
            "event_type": _THINK_EVENT_TYPE,
            "content_type": _THINK_CONTENT_TYPE,
        }
        await gateway_context.emit_chunk(chunk, **emit_kwargs)
    except Exception as exc:
        logger.debug("_emit_think failed: %s", exc)


async def _emit_child_think(
    gateway_context: Any,
    text: Any,
) -> None:
    """Emit a child reasoning chunk under the current reasoning node."""
    child_message_id = ""
    generate_message_id = getattr(gateway_context, "generate_message_id", None)
    if callable(generate_message_id):
        try:
            child_message_id = str(generate_message_id() or "")
        except Exception:
            logger.debug("generate_message_id failed in _emit_child_think", exc_info=True)

    child_parent_message_id = str(getattr(gateway_context, "message_id", "") or "")
    # content = _summarize_output(text)
    content = text
    try:
        from by_framework import StreamChunkEvent  # type: ignore

        child_chunk: Any = StreamChunkEvent(content=content)
    except ImportError:
        child_chunk = content

    emit_kwargs: dict[str, Any] = {
        "event_type": _THINK_EVENT_TYPE,
        "content_type": _THINK_CONTENT_TYPE,
    }
    if child_message_id:
        emit_kwargs["message_id"] = child_message_id
    if child_parent_message_id:
        emit_kwargs["parent_message_id"] = child_parent_message_id
    await gateway_context.emit_chunk(child_chunk, **emit_kwargs)


async def _emit_tool_detail(
    gateway_context: Any,
    title: str,
    detail: Any,
) -> None:
    """Emit a third-level reasoning node under the current tool step."""
    async with gateway_context.sub_step(title):
        await _emit_child_think(gateway_context, detail)


async def _invoke_tool_with_runtime_context(
    tool: BaseTool,
    tool_params: dict[str, Any],
    *,
    gateway_context: Any = None,
) -> Any:
    """Inject gateway runtime context into tools that explicitly declare it."""
    runtime_context_param = str(
        getattr(tool, "_datacloud_runtime_context_param", "") or ""
    ).strip()
    if runtime_context_param and gateway_context is not None:
        invoke_params = dict(tool_params)
        invoke_params[runtime_context_param] = gateway_context

        coroutine = getattr(tool, "coroutine", None)
        if coroutine is not None:
            return await coroutine(**invoke_params)

        func = getattr(tool, "func", None)
        if func is not None:
            return func(**invoke_params)

        logger.debug(
            "runtime-context tool has no direct callable; fallback to ainvoke: tool=%s",
            getattr(tool, "name", "?"),
        )

    return await tool.ainvoke(tool_params)


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

    输出层级（思考过程）：
    - 节点输出与工具名称输出位于同一层
    - 工具名称为当前层的 sub_step
    - 工具返回内容 / 错误摘要放在下一层 sub_step
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

    def _merge_ctx(base_ctx: HookContext, new_ctx: HookContext) -> HookContext:
        """Merge hook-returned ctx with base ctx to avoid losing required fields."""
        merged = dict(base_ctx)
        merged.update({k: v for k, v in new_ctx.items() if v is not None})
        return merged  # type: ignore[return-value]

    # 工具名作为第一层 sub_step，包裹整个执行过程（含 SDK 内部的 sub_step 嵌套在其中）
    # 工具名作为当前层 sub_step，包裹整个执行过程（含 SDK 内部的 sub_step 嵌套在其中）
    async def _run_tool() -> None:
        nonlocal ctx

        # --- before hook ---
        base_ctx = ctx
        ctx, before_decision = await hook_manager.run_before(ctx)
        ctx = _merge_ctx(base_ctx, ctx)
        if before_decision:
            action = str(before_decision.get("action") or "")
            if action == "short_circuit":
                result_payload = (before_decision.get("result") or {})
                ctx["tool_output"] = result_payload.get("tool_output", "（short_circuit）")
                ctx["tool_error"] = None
                return
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
                # 能通过 get_gateway_context() 获取到 context 并推送心跳日志（嵌套在当前 sub_step 下）
                try:
                    from datacloud_data_sdk.context import InvocationContext  # type: ignore
                    workspace_root = resolve_shared_workspace_dir(ctx.get("workspace_dir"))
                    _inv_ctx: Any = InvocationContext(
                        gateway_context=gateway_context,
                        workspace_dir=str(workspace_root) if workspace_root is not None else "",
                    )
                    _inv_ctx.__enter__()
                    try:
                        output = await _invoke_tool_with_runtime_context(
                            t,
                            ctx["tool_params"],
                            gateway_context=gateway_context,
                        )
                    finally:
                        _inv_ctx.__exit__(None, None, None)
                except ImportError:
                    output = await _invoke_tool_with_runtime_context(
                        t,
                        ctx["tool_params"],
                        gateway_context=gateway_context,
                    )
                ctx["tool_output"] = output
                ctx["tool_error"] = None
            except Exception as exc:  # noqa: BLE001
                logger.warning("dispatch_tool: tool='%s' raised: %s", tool_name, exc)
                ctx["tool_output"] = None
                ctx["tool_error"] = {"error_type": type(exc).__name__, "message": str(exc)}

        # --- after hook ---
        base_ctx = ctx
        ctx, after_decision = await hook_manager.run_after(ctx)
        ctx = _merge_ctx(base_ctx, ctx)
        if after_decision:
            action = str(after_decision.get("action") or "")
            if action == "recover":
                result_payload = (after_decision.get("result") or {})
                ctx["tool_output"] = result_payload.get("tool_output", ctx.get("tool_output"))
            if action == "fail":
                raise ToolHookError(after_decision)

    if gateway_context is not None:
        try:
            async with gateway_context.sub_step(tool_name):
                # 工具名称下级：调用原因
                if reason:
                    await _emit_child_think(gateway_context, reason)
                # 执行工具（SDK 内部的 sub_step 自动嵌套在此层下）
                delegate_parent_scope_factory = getattr(
                    gateway_context,
                    "delegate_parent_scope",
                    None,
                )
                delegate_parent_scope = nullcontext()
                if callable(delegate_parent_scope_factory):
                    delegate_parent_scope = delegate_parent_scope_factory(
                        gateway_context.message_id,
                    )
                with delegate_parent_scope:
                    await _run_tool()
                # 第三层：返回内容 / 错误摘要
                if ctx.get("tool_error"):
                    err_msg = ctx["tool_error"].get("message", "")
                    await _emit_tool_detail(
                        gateway_context,
                        "工具错误",
                        f"错误：{err_msg}",
                    )
                else:
                    await _emit_tool_detail(
                        gateway_context,
                        "工具返回",
                        ctx.get("tool_output"),
                    )
        except ToolHookError:
            raise
        except Exception as exc:
            logger.debug("dispatch_tool sub_step failed: %s", exc)
            # sub_step 失败时兜底执行工具（不推送进度）
            if not ctx.get("tool_output") and not ctx.get("tool_error"):
                await _run_tool()
    else:
        await _run_tool()

    final_output = ctx.get("tool_output")

    # --- 日志 ---
    if ctx.get("tool_error"):
        err_msg = ctx["tool_error"].get("message", "")
        logger.info("[tool_return] tool=%s error=%s", tool_name, err_msg)
    else:
        try:
            full_output_str = json.dumps(final_output, ensure_ascii=False, default=str)
        except Exception:
            full_output_str = repr(final_output)
        logger.info("[tool_return] tool=%s output=%s", tool_name, full_output_str)

        # --- data_query 结构识别：records+meta 或 file.file_url ---
        if isinstance(final_output, dict):
            data_block = final_output.get("data") if isinstance(final_output.get("data"), dict) else final_output
            if isinstance(data_block, dict):
                records = data_block.get("records")
                file_block = data_block.get("file") if isinstance(data_block.get("file"), dict) else None
                file_url = str(file_block.get("file_url", "") if file_block else "").strip()
                has_records_and_meta = (
                    isinstance(records, list) and "meta" in data_block
                )

                if has_records_and_meta and "_hint" not in final_output:
                    final_output = dict(final_output)
                    columns_raw = data_block.get("meta", {}).get("columns", []) if isinstance(data_block.get("meta"), dict) else []
                    col_names: list[str] = []
                    for col in columns_raw:
                        if isinstance(col, dict):
                            name = str(col.get("name") or col.get("label") or "")
                            if name:
                                col_names.append(name)
                        elif isinstance(col, str):
                            col_names.append(col)
                    columns_hint = ""
                    if col_names:
                        columns_hint = f"\u5305\u542b\u5b57\u6bb5: {', '.join(col_names[:8])}"
                    if file_url:
                        final_output["file_url"] = file_url
                        final_output["_hint"] = (
                            f"\u6570\u636e\u91cf\u8f83\u5927\uff0c\u5df2\u5b58\u5165\u6587\u4ef6 {file_url}\u3002"
                            f"{('\n' + columns_hint) if columns_hint else ''}"
                            "\u8bf7\u8c03\u7528 finish_react \u65f6\u4f7f\u7528 result_type=query_result\uff0c"
                            "\u7cfb\u7edf\u4f1a\u81ea\u52a8\u900f\u4f20\u5b8c\u6574\u7ed3\u6784\u3002"
                        )
                        logger.info("[tool_return] data_query file_url detected: %s", file_url)
                    else:
                        final_output["_hint"] = (
                            f"\u6570\u636e\u5df2\u8fd4\u56de {len(records)} \u6761 records\u3002"
                            f"{('\n' + columns_hint) if columns_hint else ''}"
                            "\u8bf7\u7acb\u5373\u8c03\u7528 finish_react\uff0c\u4f7f\u7528 result_type=query_result\uff0c"
                            "\u7cfb\u7edf\u4f1a\u81ea\u52a8\u900f\u4f20\u5b8c\u6574\u7684 records/pagination/meta \u7ed3\u6784\uff0c\u65e0\u9700\u624b\u52a8\u5e8f\u5217\u5316\u3002"
                        )
                        logger.info("[tool_return] data_query records detected: count=%d", len(records))

    return tool_call_id, final_output
