from __future__ import annotations

import json
import logging
from contextlib import nullcontext
from typing import Any, TypedDict

from datacloud_data_sdk.stream_text import coerce_stream_chunk_text
from langchain_core.tools import BaseTool

try:
    from langgraph.errors import GraphBubbleUp  # interrupt / GraphInterrupt base
except ImportError:  # langgraph not installed or older version
    GraphBubbleUp = type(None)  # type: ignore[assignment,misc]

from datacloud_analysis.tool_hook_plugins import get_tool_hook_plugin_manager
from datacloud_analysis.tool_hook_plugins.types import HookContext, HookSignalError
from datacloud_analysis.workspace.runtime import resolve_shared_workspace_dir

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset({"password", "token", "secret", "api_key", "apikey"})


class ToolErrorDict(TypedDict):
    """Fully-classified tool error passed back to the agent as ToolMessage content."""

    error_type: str
    message: str
    retryable: bool
    hint: str
    context: dict[str, Any]


def _resolve_gateway_user_id(gateway_context: Any) -> str:
    """从 gateway_context 中按多源回退提取用户标识。

    回退顺序：
    1. ``gateway_context.user_id``（动态路径 SimpleNamespace 直接挂的字段）
    2. ``gateway_context.current_command.header.user_code``（静态路径真实网关上下文）
    3. ``gateway_context.current_command.header.metadata["user_code"]``（兜底）
    所有源都缺失时返回空字符串。
    """
    if gateway_context is None:
        return ""

    direct = str(getattr(gateway_context, "user_id", "") or "").strip()
    if direct:
        return direct

    header = getattr(getattr(gateway_context, "current_command", None), "header", None)
    if header is None:
        return ""

    user_code = str(getattr(header, "user_code", "") or "").strip()
    if user_code:
        return user_code

    metadata = getattr(header, "metadata", None) or {}
    if isinstance(metadata, dict):
        meta_user_code = metadata.get("user_code")
        if isinstance(meta_user_code, str) and meta_user_code.strip():
            return meta_user_code.strip()

    return ""


def _append_local_sdk_src_for_tests() -> None:
    """Append the local datacloud-data src path for test/dev fallback imports."""
    import os
    import sys

    repo_root = os.path.abspath(__file__)
    for _ in range(7):
        repo_root = os.path.dirname(repo_root)
    sdk_src = os.path.join(repo_root, "packages", "datacloud-data", "src")
    if os.path.exists(sdk_src):
        sys.path.append(sdk_src)


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


def _build_tool_error(exc: Exception) -> ToolErrorDict:  # noqa: C901, PLR0912
    """Convert an exception to a structured ToolErrorDict with classification metadata."""
    from datacloud_data_sdk.exceptions import (  # noqa: PLC0415
        ActionNotConfiguredError,
        ActionNotFoundError,
        ApiExecutionError,
        CannotAnswerError,
        DataSourceUnavailableError,
        ObjectNotFoundError,
        PermissionDeniedError,
        ScriptExecutionError,
        SqlExecutionError,
        StepDependencyError,
        TermAmbiguousError,
        TermNotFoundError,
    )

    error_type = type(exc).__name__
    message = str(exc)
    context: dict[str, Any] = {}
    retryable = False
    hint = f"工具执行失败（{error_type}），请告知用户并联系技术支持。"

    if isinstance(exc, TermNotFoundError):
        retryable = True
        context = {"term_set": exc.term_set, "value": exc.value}
        if exc.available_entries:
            context["available_entries"] = exc.available_entries[:10]
        elif exc.available_values:
            context["available_values"] = exc.available_values[:10]
        hint = (
            f"术语集「{exc.term_set}」中不存在「{exc.value}」，"
            "请从 available_values/available_entries 中选择正确的值后重试。"
        )
    elif isinstance(exc, TermAmbiguousError):
        retryable = True
        context = {"term_set": exc.term_set, "value": exc.value, "matches": exc.matches[:10]}
        hint = f"「{exc.value}」匹配到多个术语，请从 matches 中明确指定其中一个后重试。"
    elif isinstance(exc, ObjectNotFoundError):
        context = {"object_code": exc.object_code}
        hint = f"对象「{exc.object_code}」不存在，请确认对象代码是否正确。"
    elif isinstance(exc, ActionNotFoundError):
        context = {"object_code": exc.object_code, "action_code": exc.action_code}
        hint = f"对象「{exc.object_code}」上不存在动作「{exc.action_code}」，请确认动作代码。"
    elif isinstance(exc, ActionNotConfiguredError):
        context = {"action_code": exc.action_code}
        hint = f"动作「{exc.action_code}」未配置脚本或 API，请联系管理员完成配置。"
    elif isinstance(exc, PermissionDeniedError):
        context = {"resource": exc.resource, "reason_code": exc.reason_code}
        hint = f"访问「{exc.resource}」被拒绝（{exc.reason_code}），请申请权限后重试。"
    elif isinstance(exc, ApiExecutionError):
        context = {"function_code": exc.function_code, "status_code": exc.status_code}
        if exc.status_code >= 500:
            retryable = True
            hint = f"API「{exc.function_code}」发生服务端错误（{exc.status_code}），可稍后重试。"
        else:
            hint = (
                f"API「{exc.function_code}」发生客户端错误（{exc.status_code}），请检查请求参数。"
            )
    elif isinstance(exc, SqlExecutionError):
        context = {"datasource_alias": exc.datasource_alias}
        hint = f"数据源「{exc.datasource_alias}」SQL 执行失败，请检查 SQL 语句或联系管理员。"
    elif isinstance(exc, ScriptExecutionError):
        context = {"action_code": exc.action_code}
        if exc.line_no is not None:
            context["line_no"] = exc.line_no
        hint = f"动作脚本「{exc.action_code}」执行失败，请联系管理员检查脚本逻辑。"
    elif isinstance(exc, DataSourceUnavailableError):
        retryable = True
        context = {"datasource_alias": exc.alias}
        hint = f"数据源「{exc.alias}」暂不可用，请稍后重试或联系管理员检查连接。"
    elif isinstance(exc, CannotAnswerError):
        hint = "当前问题无法直接回答，请尝试拆解为更小的子问题后重新提问。"
    elif isinstance(exc, StepDependencyError):
        context = {"step_id": exc.step_id, "depends_on": exc.depends_on}
        hint = f"步骤「{exc.step_id}」的依赖步骤「{exc.depends_on}」缺失，请检查执行计划。"
    else:
        try:
            from datacloud_knowledge.file_store.errors import (  # noqa: PLC0415
                BackendMisconfiguredError,
                FileNotFoundInStoreError,
                FileStoreError,
            )
            from datacloud_knowledge.query.search.vector_validation import (  # noqa: PLC0415
                TermVectorValidationError,
            )
        except ImportError:
            pass
        else:
            if isinstance(exc, TermVectorValidationError):
                hint = (
                    "术语向量知识库未就绪或校验失败，当前无法执行向量召回。"
                    "请告知用户知识库暂不可用，或联系管理员检查向量索引状态。"
                )
            elif isinstance(exc, FileNotFoundInStoreError):
                context = {"md5": exc.md5}
                hint = f"文件存储中未找到文件（md5={exc.md5}），请确认文件是否已上传。"
            elif isinstance(exc, BackendMisconfiguredError):
                hint = "文件存储后端配置错误（如缺少 S3 密钥），请联系管理员检查存储配置。"
            elif isinstance(exc, FileStoreError):
                hint = "文件存储操作失败，请联系管理员检查存储后端状态。"

    return ToolErrorDict(
        error_type=error_type,
        message=message,
        retryable=retryable,
        hint=hint,
        context=context,
    )


def _format_agent_error_message(tool_error: ToolErrorDict) -> str:
    """Format a ToolErrorDict into a multi-line, agent-readable error string."""
    error_type = tool_error.get("error_type", "UnknownError")
    message = tool_error.get("message", "未知错误")
    hint = tool_error.get("hint", "请告知用户并联系技术支持。")
    context = tool_error.get("context") or {}
    retryable = tool_error.get("retryable", False)

    lines: list[str] = [
        f"[工具调用失败: {error_type}]",
        f"错误详情：{message}",
    ]
    if "available_entries" in context:
        entries = context["available_entries"]
        entry_strs = [f"[{e['code']}] {e['label']}" for e in entries if isinstance(e, dict)]
        lines.append(f"可用条目：{', '.join(entry_strs)}")
    elif "available_values" in context:
        vals = context["available_values"]
        lines.append(f"可用值：{', '.join(str(v) for v in vals)}")
    if "matches" in context:
        matches = context["matches"]
        match_strs = [f"[{m['code']}] {m['label']}" for m in matches if isinstance(m, dict)]
        lines.append(f"候选术语：{', '.join(match_strs)}")
    if "status_code" in context:
        lines.append(f"HTTP 状态码：{context['status_code']}")
    lines.append(f"可重试：{'是' if retryable else '否'}")
    lines.append(f"建议：{hint}")
    return "\n".join(lines)


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
        gateway_context._datacloud_skip_delegate_resume_replay_output = False
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
        from langchain_core.callbacks import adispatch_custom_event  # noqa: PLC0415

        await adispatch_custom_event(
            "dc_stream_chunk",
            {
                "content": coerce_stream_chunk_text(text),
                "event_type": _THINK_EVENT_TYPE,
                "content_type": _THINK_CONTENT_TYPE,
            },
        )
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
    content = coerce_stream_chunk_text(text)
    emit_payload: dict[str, Any] = {
        "content": content,
        "event_type": _THINK_EVENT_TYPE,
        "content_type": _THINK_CONTENT_TYPE,
    }
    if child_message_id:
        emit_payload["message_id"] = child_message_id
    if child_parent_message_id:
        emit_payload["parent_message_id"] = child_parent_message_id
    try:
        from langchain_core.callbacks import adispatch_custom_event  # noqa: PLC0415

        await adispatch_custom_event("dc_stream_chunk", emit_payload)
    except Exception as exc:
        logger.debug("_emit_child_think failed: %s", exc)


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
    loader: Any = None,
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

    # --- 特殊工具：agent_delegate（内部调用 interrupt，必须跳过 hook 的 try/except）---
    t_delegate = tools_map.get(tool_name)
    is_delegate_flag = (
        getattr(t_delegate, "_is_agent_delegate", False) if t_delegate is not None else False
    )
    is_agent_delegate = isinstance(is_delegate_flag, bool) and is_delegate_flag
    if t_delegate is not None and is_agent_delegate:
        # 把 react checkpoint 注入到 gateway_context，delegate tool 可以访问
        react_checkpoint = state.get("react_checkpoint")
        if react_checkpoint and gateway_context is not None:
            gateway_context._react_checkpoint = react_checkpoint

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

    try:
        from datacloud_data_sdk.trace_context import current_trace_id as _tid

        _trace_id = _tid.get("????????")
    except Exception:
        _trace_id = "????????"
    logger.warning(
        "[%s] ──── tool=%s params=%s",
        _trace_id,
        tool_name,
        json.dumps(raw_params, ensure_ascii=False, default=str)[:2000],
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
        "knowledge_payload": dict(state.get("knowledge_payload") or {}),
        "metadata": {"loader": loader, "state": state, "gateway_context": gateway_context},
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
        # 将 hook 可能修改过的 knowledge_payload 同步回 state，
        # 确保同一轮 execution 中后续工具调用能读到更新后的值（例如 needs_clarification 被清除）
        if "knowledge_payload" in ctx:
            state["knowledge_payload"] = ctx["knowledge_payload"]
        if before_decision:
            action = str(before_decision.get("action") or "")
            if action == "short_circuit":
                result_payload = before_decision.get("result") or {}
                ctx["tool_output"] = result_payload.get("tool_output", "（short_circuit）")
                ctx["tool_error"] = None
                return
            if action == "fail":
                raise ToolHookError(before_decision)
            if action == "redirect":
                redirect_tool_name = str(before_decision.get("tool") or "")
                redirect_params = dict(before_decision.get("params") or {})
                redirect_t = tools_map.get(redirect_tool_name)
                if redirect_t is None:
                    logger.warning(
                        "dispatch_tool: redirect target '%s' not found in tools_map",
                        redirect_tool_name,
                    )
                    ctx["tool_output"] = None
                    ctx["tool_error"] = ToolErrorDict(
                        error_type="ToolNotFound",
                        message=f"Redirect target '{redirect_tool_name}' not found",
                        retryable=False,
                        hint=f"重定向目标工具「{redirect_tool_name}」不存在，请检查 hook 配置。",
                        context={},
                    )
                else:
                    try:
                        try:
                            from datacloud_data_sdk.context import InvocationContext  # type: ignore
                        except ImportError:
                            _append_local_sdk_src_for_tests()
                            from datacloud_data_sdk.context import InvocationContext  # type: ignore

                        workspace_root = resolve_shared_workspace_dir(ctx.get("workspace_dir"))
                        _gc_user_id = _resolve_gateway_user_id(gateway_context)
                        _gc_session_id = str(getattr(gateway_context, "session_id", "") or "")
                        _result_file_storage = getattr(loader, "result_file_storage", None)
                        _extras = getattr(gateway_context, "extras", None)
                        _inv_ctx_redirect: Any = InvocationContext(
                            user_id=_gc_user_id,
                            session_id=_gc_session_id,
                            gateway_context=gateway_context,
                            workspace_dir=str(workspace_root) if workspace_root is not None else "",
                            result_file_storage=_result_file_storage,
                            extras=_extras,
                        )
                        _inv_ctx_redirect.__enter__()
                        try:
                            output = await _invoke_tool_with_runtime_context(
                                redirect_t,
                                redirect_params,
                                gateway_context=gateway_context,
                            )
                        finally:
                            _inv_ctx_redirect.__exit__(None, None, None)
                        output = _normalize_mcp_output(output)
                        ctx["tool_output"] = output
                        ctx["tool_error"] = None
                    except GraphBubbleUp:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "dispatch_tool: redirect tool='%s' raised %s: %s",
                            redirect_tool_name,
                            type(exc).__name__,
                            exc,
                        )
                        ctx["tool_output"] = None
                        ctx["tool_error"] = _build_tool_error(exc)
                return

        # --- 实际工具调用 ---
        t = tools_map.get(tool_name)
        if t is None:
            logger.warning("dispatch_tool: tool '%s' not found in tools_map", tool_name)
            ctx["tool_output"] = None
            ctx["tool_error"] = ToolErrorDict(
                error_type="ToolNotFound",
                message=f"Tool '{tool_name}' not found",
                retryable=False,
                hint=f"工具「{tool_name}」不存在，请检查工具名称是否正确。",
                context={},
            )
        else:
            try:
                # 将 gateway_context 注入 InvocationContext，使 SDK 内的 GatewayProgressReporter
                # 能通过 get_gateway_context() 获取到 context 并推送心跳日志（嵌套在当前 sub_step 下）
                try:
                    from datacloud_data_sdk.context import InvocationContext  # type: ignore
                except ImportError:  # pragma: no cover - fallback for tests/dev env
                    _append_local_sdk_src_for_tests()
                    from datacloud_data_sdk.context import InvocationContext  # type: ignore

                workspace_root = resolve_shared_workspace_dir(ctx.get("workspace_dir"))
                # 从 gateway_context 提取 user_id / session_id，使 SDK 内可通过
                # get_current_context() 拿到正确的用户/会话标识。
                #
                # 两类 gateway_context 都要兼容：
                # - 动态路径：``OntologyAgent`` 用 ``SimpleNamespace(user_id=...)`` 直接挂字段
                # - 静态路径：``ByclawDataClarification`` 等真实网关上下文，user 信息在
                #   ``current_command.header.user_code`` 或 ``header.metadata["user_code"]`` 上
                _gc_user_id = _resolve_gateway_user_id(gateway_context)
                _gc_session_id = str(getattr(gateway_context, "session_id", "") or "")
                _result_file_storage = getattr(loader, "result_file_storage", None)
                _extras = getattr(gateway_context, "extras", None)
                _inv_ctx: Any = InvocationContext(
                    user_id=_gc_user_id,
                    session_id=_gc_session_id,
                    gateway_context=gateway_context,
                    workspace_dir=str(workspace_root) if workspace_root is not None else "",
                    result_file_storage=_result_file_storage,
                    extras=_extras,
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
            except HookSignalError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "dispatch_tool: tool='%s' raised %s: %s",
                    tool_name,
                    type(exc).__name__,
                    exc,
                )
                ctx["tool_output"] = None
                ctx["tool_error"] = _build_tool_error(exc)

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
                # 工具入参（before_hook 处理后的最终参数，在工具执行后才有完整值）
                if ctx.get("tool_params"):
                    try:
                        await _emit_tool_detail(
                            gateway_context,
                            "工具入参",
                            ctx.get("tool_params"),
                        )
                    except Exception as _emit_exc:
                        logger.debug("emit 工具入参 failed: %s", _emit_exc)
                # 工具返回内容 / 错误摘要
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
        except HookSignalError:
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
        tool_error: ToolErrorDict = ctx["tool_error"]  # type: ignore[assignment]
        logger.info(
            "[tool_return] tool=%s error_type=%s retryable=%s",
            tool_name,
            tool_error.get("error_type", ""),
            tool_error.get("retryable", False),
        )
        final_output = _format_agent_error_message(tool_error)
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
