from __future__ import annotations

import json
import logging
from contextlib import nullcontext
from typing import Any

from datacloud_data_sdk.stream_text import coerce_stream_chunk_text
from langchain_core.tools import BaseTool

try:
    from langgraph.errors import GraphBubbleUp  # interrupt / GraphInterrupt base
except ImportError:  # langgraph not installed or older version
    GraphBubbleUp = type(None)  # type: ignore[assignment,misc]

from datacloud_analysis.tool_hook_plugins import get_tool_hook_plugin_manager
from datacloud_analysis.tool_hook_plugins.types import HookContext
from datacloud_analysis.workspace.runtime import resolve_shared_workspace_dir

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset({"password", "token", "secret", "api_key", "apikey"})


def _sanitize(params: dict[str, Any]) -> str:
    sanitized = {
        k: "***" if any(s in k.lower() for s in _SENSITIVE_KEYS) else v for k, v in params.items()
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

        # 以原 schema 为基类新增 reason 字段，保留原 schema 的所有 validator（含 _CoerceBase）
        NewSchema = create_model(
            f"{original_schema.__name__}WithReason",
            __base__=original_schema,
            reason=(str, Field(default="", description="选择本工具的理由")),
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

_DELEGATE_PARENT_MESSAGE_ID_KEY = "delegate_parent_message_id"


class ToolHookError(Exception):
    def __init__(self, decision: dict[str, Any]) -> None:
        self.decision = decision
        super().__init__(str(decision))


def is_delegate_wait_resume_command(command: Any) -> bool:
    """Return True when current command is a ResumeCommand for AGENT_DELEGATE_WAIT."""
    if command is None or command.__class__.__name__ != "ResumeCommand":
        return False
    header = getattr(command, "header", None)
    metadata = getattr(header, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    if str(metadata.get("interrupt_reason") or "").strip() == "AGENT_DELEGATE_WAIT":
        return True
    parent_resume_target = metadata.get("parent_resume_target")
    if isinstance(parent_resume_target, dict):
        return (
            str(parent_resume_target.get("interrupt_reason") or "").strip() == "AGENT_DELEGATE_WAIT"
        )
    return False


def _consume_delegate_resume_replay_suppression(gateway_context: Any) -> bool:
    """Consume one-shot suppression flag for replayed delegate tool output."""
    if gateway_context is None:
        return False
    should_skip = bool(
        getattr(
            gateway_context,
            "_datacloud_skip_delegate_resume_replay_output",
            False,
        )
    )
    if should_skip:
        setattr(gateway_context, "_datacloud_skip_delegate_resume_replay_output", False)
    return should_skip


def _reasoning_emit_kwargs(
    *,
    message_id: str = "",
    parent_message_id: str = "",
) -> dict[str, str]:
    kwargs = {
        "event_type": _THINK_EVENT_TYPE,
        "content_type": _THINK_CONTENT_TYPE,
    }
    if message_id:
        kwargs["message_id"] = message_id
    if parent_message_id:
        kwargs["parent_message_id"] = parent_message_id
    return kwargs


def _new_message_id(gateway_context: Any) -> str:
    generate_message_id = getattr(gateway_context, "generate_message_id", None)
    if callable(generate_message_id):
        try:
            return str(generate_message_id() or "")
        except Exception:
            logger.debug("generate_message_id failed in tool_wrapper", exc_info=True)
    return ""


def _current_command_metadata(gateway_context: Any) -> dict[str, Any]:
    current_command = getattr(gateway_context, "current_command", None)
    header = getattr(current_command, "header", None)
    metadata = getattr(header, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    return {}


def _delegate_resume_parent_message_id(gateway_context: Any) -> str:
    metadata = _current_command_metadata(gateway_context)
    direct = str(metadata.get(_DELEGATE_PARENT_MESSAGE_ID_KEY) or "").strip()
    if direct:
        return direct
    parent_resume_target = metadata.get("parent_resume_target")
    if isinstance(parent_resume_target, dict):
        return str(parent_resume_target.get(_DELEGATE_PARENT_MESSAGE_ID_KEY) or "").strip()
    return ""


async def _emit_think(gateway_context: Any, text: str) -> None:
    """在 sub_step 内推送 think_text 内容。"""
    try:
        from by_framework import StreamChunkEvent  # type: ignore

        chunk = StreamChunkEvent(content=coerce_stream_chunk_text(text))
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
    *,
    parent_message_id: str | None = None,
) -> None:
    """Emit a child reasoning chunk under the current reasoning node."""
    child_message_id = _new_message_id(gateway_context)
    child_parent_message_id = str(
        parent_message_id
        if parent_message_id is not None
        else getattr(gateway_context, "message_id", "") or ""
    )
    # Gateway history join() requires str; tool outputs are often dict/list.
    content = coerce_stream_chunk_text(text)
    try:
        from by_framework import StreamChunkEvent  # type: ignore

        child_chunk: Any = StreamChunkEvent(content=content)
    except ImportError:
        child_chunk = content

    emit_kwargs: dict[str, Any] = _reasoning_emit_kwargs(
        message_id=child_message_id,
        parent_message_id=child_parent_message_id,
    )
    await gateway_context.emit_chunk(child_chunk, **emit_kwargs)


async def _emit_tool_detail_under_parent(
    gateway_context: Any,
    title: str,
    detail: Any,
    *,
    parent_message_id: str,
) -> bool:
    """Emit a reasoning title + child content under an explicit parent node."""
    emit_state = getattr(gateway_context, "emit_state", None)
    if not callable(emit_state):
        return False

    title_message_id = _new_message_id(gateway_context)
    if not title_message_id:
        return False

    await emit_state(
        title,
        **_reasoning_emit_kwargs(
            message_id=title_message_id,
            parent_message_id=parent_message_id,
        ),
    )
    await _emit_child_think(
        gateway_context,
        detail,
        parent_message_id=title_message_id,
    )
    return True


async def _emit_tool_detail(
    gateway_context: Any,
    title: str,
    detail: Any,
    *,
    parent_message_id: str = "",
) -> None:
    """Emit a third-level reasoning node under the current tool step."""
    if parent_message_id:
        emitted = await _emit_tool_detail_under_parent(
            gateway_context,
            title,
            detail,
            parent_message_id=parent_message_id,
        )
        if emitted:
            return
    async with gateway_context.sub_step(title):
        await _emit_child_think(gateway_context, detail)


async def _invoke_tool_with_runtime_context(
    tool: BaseTool,
    tool_params: dict[str, Any],
    *,
    gateway_context: Any = None,
) -> Any:
    """Inject gateway runtime context into tools that explicitly declare it."""
    runtime_context_param = str(getattr(tool, "_datacloud_runtime_context_param", "") or "").strip()
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


def _normalize_mcp_output(output: Any) -> Any:
    """将 MCP 协议格式 {"content": [...], "isError": false} 归一化为内层 JSON dict。

    MCP 工具返回格式：{"content": [{"type": "text", "text": "json_string"}], "isError": false}
    归一化为：{"code": 0, "message": "success", "data": {...}} 等内层 dict，
    使后续 data_block 检测（records+meta）能正常工作。
    """
    if not isinstance(output, dict):
        return output
    if "content" not in output or "isError" not in output:
        return output
    content = output.get("content") or []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            try:
                parsed = json.loads(item.get("text", ""))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:  # noqa: BLE001
                pass
    return output


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
    - agent_delegate：直接调用，不走 hook（内部调用 interrupt，必须跳过 try/except）

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

    # --- 特殊工具：agent_delegate（内部调用 interrupt，必须跳过 hook 的 try/except）---
    t_delegate = tools_map.get(tool_name)
    is_delegate_flag = getattr(t_delegate, "_is_agent_delegate", False) if t_delegate is not None else False
    is_agent_delegate = isinstance(is_delegate_flag, bool) and is_delegate_flag
    if t_delegate is not None and is_agent_delegate:
        # 把 react checkpoint 注入到 gateway_context，delegate tool 可以访问
        react_checkpoint = state.get("react_checkpoint")
        if react_checkpoint and gateway_context is not None:
            setattr(gateway_context, "_react_checkpoint", react_checkpoint)

        if _consume_delegate_resume_replay_suppression(gateway_context):
            result = await _invoke_tool_with_runtime_context(
                t_delegate,
                raw_params,
                gateway_context=gateway_context,
            )
            if gateway_context is not None:
                await _emit_tool_detail(
                    gateway_context,
                    "工具返回",
                    result,
                    parent_message_id=_delegate_resume_parent_message_id(gateway_context),
                )
            return tool_call_id, result
        if gateway_context is not None:
            async with gateway_context.sub_step(tool_name):
                if reason:
                    await _emit_child_think(gateway_context, reason)
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
                    result = await _invoke_tool_with_runtime_context(
                        t_delegate,
                        raw_params,
                        gateway_context=gateway_context,
                    )
                # interrupt 首次挂起时不会走到这里；恢复后若拿到子 agent 结果，则补发工具返回。
                await _emit_tool_detail(
                    gateway_context,
                    "工具返回",
                    result,
                )
                return tool_call_id, result
        result = await _invoke_tool_with_runtime_context(
            t_delegate, raw_params, gateway_context=gateway_context
        )
        return tool_call_id, result

    # --- 解包嵌套参数（兜底）：如果 LLM 产生了 {"params": {...}} 嵌套结构，展开它 ---
    if len(raw_params) == 1 and "params" in raw_params and isinstance(raw_params["params"], dict):
        raw_params = raw_params["params"]

    logger.info(
        "[tool_call] tool=%s reason=%s params=%s",
        tool_name,
        reason,
        _sanitize(raw_params),
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
                result_payload = before_decision.get("result") or {}
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
            ctx["tool_error"] = {
                "error_type": "ToolNotFound",
                "message": f"Tool '{tool_name}' not found",
            }
        else:
            try:
                # 将 gateway_context 注入 InvocationContext，使 SDK 内的 GatewayProgressReporter
                # 能通过 get_gateway_context() 获取到 context 并推送心跳日志（嵌套在当前 sub_step 下）
                try:
                    from datacloud_data_sdk.context import InvocationContext  # type: ignore
                except ImportError:  # pragma: no cover - fallback for tests/dev env
                    import sys
                    from pathlib import Path

                    repo_root = Path(__file__).resolve().parents[6]
                    sdk_src = repo_root / "packages" / "datacloud-data" / "src"
                    if sdk_src.exists():
                        sys.path.append(str(sdk_src))
                    from datacloud_data_sdk.context import InvocationContext  # type: ignore

                workspace_root = resolve_shared_workspace_dir(ctx.get("workspace_dir"))
                # 从 gateway_context 提取 user_id / session_id，使 SDK 内可通过
                # get_current_context() 拿到正确的用户/会话标识
                _gc_user_id = str(getattr(gateway_context, "user_id", "") or "")
                _gc_session_id = str(getattr(gateway_context, "session_id", "") or "")
                _inv_ctx: Any = InvocationContext(
                    user_id=_gc_user_id,
                    session_id=_gc_session_id,
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
                output = _normalize_mcp_output(output)  # 归一化 MCP 格式，使 data_block 检测可识别
                ctx["tool_output"] = output
                ctx["tool_error"] = None
            except GraphBubbleUp:
                raise
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
                result_payload = after_decision.get("result") or {}
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
        except GraphBubbleUp:
            raise
        except Exception as exc:
            logger.debug("dispatch_tool sub_step failed: %s", exc)
            # sub_step 失败时兜底执行工具（不推送进度）
            if not ctx.get("tool_output") and not ctx.get("tool_error"):
                await _run_tool()
    else:
        await _run_tool()

    final_output = ctx.get("tool_output")

    # --- 日志 & 错误返回 ---
    if ctx.get("tool_error"):
        err_msg = ctx["tool_error"].get("message", "未知错误")
        logger.info("[tool_return] tool=%s error=%s", tool_name, err_msg)
        # 将错误信息作为 ToolMessage 内容返回给 LLM，使其能理解错误并修正参数重试
        final_output = f"[工具调用失败] {err_msg}\n请分析以上错误，修正参数后重新调用该工具。"
    else:
        try:
            full_output_str = json.dumps(final_output, ensure_ascii=False, default=str)
        except Exception:
            full_output_str = repr(final_output)
        logger.info("[tool_return] tool=%s output=%s", tool_name, full_output_str)

        # --- data_query 结构识别：records+meta 或 file.file_url ---
        if isinstance(final_output, dict):
            data_block = (
                final_output.get("data")
                if isinstance(final_output.get("data"), dict)
                else final_output
            )
            if isinstance(data_block, dict):
                records = data_block.get("records")
                file_block = (
                    data_block.get("file") if isinstance(data_block.get("file"), dict) else None
                )
                file_url = str(file_block.get("file_url", "") if file_block else "").strip()
                has_records_and_meta = isinstance(records, list) and "meta" in data_block

                if has_records_and_meta and "_hint" not in final_output:
                    final_output = dict(final_output)
                    columns_raw = (
                        data_block.get("meta", {}).get("columns", [])
                        if isinstance(data_block.get("meta"), dict)
                        else []
                    )
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
                    columns_hint_suffix = f"\n{columns_hint}" if columns_hint else ""
                    if file_url:
                        final_output["file_url"] = file_url
                        final_output["_hint"] = (
                            f"\u6570\u636e\u91cf\u8f83\u5927\uff0c\u5df2\u5b58\u5165\u6587\u4ef6 {file_url}\u3002"
                            f"{columns_hint_suffix}"
                            "\u8bf7\u8c03\u7528 finish_react \u65f6\u4f7f\u7528 result_type=query_result\uff0c"
                            "\u7cfb\u7edf\u4f1a\u81ea\u52a8\u900f\u4f20\u5b8c\u6574\u7ed3\u6784\u3002"
                        )
                        logger.info(
                            "[tool_return] data_query hint columns=%s file_url=%s",
                            ",".join(col_names[:8]),
                            file_url,
                        )
                        logger.info("[tool_return] data_query file_url detected: %s", file_url)
                    else:
                        # 小结果集（≤5行）直接带上实际数据，避免 LLM 把「行数」当「字段值」
                        # 典型场景：聚合/计数查询返回 1 行，行数=1，字段值=真正的统计结果
                        if len(records) <= 5:
                            records_json = json.dumps(records, ensure_ascii=False, default=str)
                            final_output["_hint"] = (
                                f"数据已返回 {len(records)} 条 records: {records_json}。"
                                f"{columns_hint_suffix}"
                                "请立即调用 finish_react，使用 result_type=query_result，"
                                "系统会自动透传完整的 records/pagination/meta 结构，无需手动序列化。"
                            )
                        else:
                            final_output["_hint"] = (
                                f"数据已返回 {len(records)} 条 records。"
                                f"{columns_hint_suffix}"
                                "请立即调用 finish_react，使用 result_type=query_result，"
                                "系统会自动透传完整的 records/pagination/meta 结构，无需手动序列化。"
                            )
                        logger.info(
                            "[tool_return] data_query hint columns=%s records=%d",
                            ",".join(col_names[:8]),
                            len(records),
                        )
                        logger.info(
                            "[tool_return] data_query records detected: count=%d", len(records)
                        )

    return tool_call_id, final_output
