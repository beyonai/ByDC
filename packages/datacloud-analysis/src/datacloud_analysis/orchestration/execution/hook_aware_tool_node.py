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
from datacloud_analysis.tool_hook_plugins.builtin.operation_confirmation_plugin import (
    build_batch_operation_form,
)
from datacloud_analysis.tool_hook_plugins.types import ClarificationNeededError, HookContext

logger = logging.getLogger(__name__)


def _get_db_engine() -> Any:
    """获取数据库连接（供测试 mock）。"""
    try:
        from datacloud_analysis.infrastructure.db import get_engine  # noqa: PLC0415
        return get_engine()
    except Exception:  # noqa: BLE001
        return None


def _get_next_objects_from_term(
    source_obj_code: str,
    allowed_scope: list,
) -> list[str]:
    """查询 term_relation 表，取 source_obj_code 一跳可达且在授权范围内的对象列表。

    Returns:
        list[str]: object_code 列表（可能为空）
    """
    if not allowed_scope:
        return []

    object_codes = [e.code for e in allowed_scope if e.scope_type == "OBJECT"]
    scene_codes = [e.code for e in allowed_scope if e.scope_type == "SCENE"]
    library_ids = [e.code for e in allowed_scope if e.scope_type == "ONTOLOGY_BASE"]

    try:
        engine = _get_db_engine()
        if engine is None:
            return []

        placeholders_obj = ",".join(f":oc{i}" for i in range(len(object_codes))) if object_codes else "NULL"
        placeholders_sc = ",".join(f":sc{i}" for i in range(len(scene_codes))) if scene_codes else "NULL"
        placeholders_lib = ",".join(f":lib{i}" for i in range(len(library_ids))) if library_ids else "NULL"

        sql = f"""
            SELECT target.term_code AS object_code
            FROM byai.term_relation tr
            JOIN byai.term source ON tr.source_term_id = source.term_id
            JOIN byai.term target ON tr.target_term_id = target.term_id
            WHERE source.term_code = :source_obj_code
              AND target.term_type_code IN ('object', 'view')
              AND (
                  target.term_code IN ({placeholders_obj})
               OR target.domain_id IN ({placeholders_sc})
               OR target.library_id IN ({placeholders_lib})
              )
        """
        params: dict[str, Any] = {"source_obj_code": source_obj_code}
        for i, c in enumerate(object_codes):
            params[f"oc{i}"] = c
        for i, c in enumerate(scene_codes):
            params[f"sc{i}"] = c
        for i, c in enumerate(library_ids):
            params[f"lib{i}"] = c

        result = engine.execute(sql, params)
        return [row["object_code"] for row in result.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def _get_tool_display_label(tool_name: str, tools_map: dict[str, Any]) -> str:
    """返回工具的友好显示名称，优先使用 metadata.title，回退到 tool_name。"""
    tool = tools_map.get(tool_name)
    if tool is not None:
        meta = getattr(tool, "metadata", None) or {}
        title = str(meta.get("title") or "").strip()
        if title and title != tool_name:
            return title
    return tool_name


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
        operation_contexts: list[dict[str, Any]] = []
        prebuilt_tool_messages: list[ToolMessage] = []

        # before_call_back 会消费 complex_conditions（路由元字段），提前从原始 args 中保存，
        # 供后续推送"工具入参"时还原展示，不影响实际执行参数。
        original_complex_conditions_map: dict[str, list[str]] = {
            str(tc.get("id") or ""): list((tc.get("args") or {}).get("complex_conditions") or [])
            for tc in last_ai.tool_calls
        }

        for tc in last_ai.tool_calls:
            tool_call_id = str(tc.get("id") or "")
            tool_name = str(tc.get("name") or "")
            ctx: HookContext = {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_params": dict(tc.get("args") or {}),
                "session_id": str(state_dict.get("agent_id") or ""),
                "user_query": str(state_dict.get("user_query") or ""),
                "knowledge_snippets": list(state_dict.get("knowledge_snippets") or []),
                "knowledge_payload": dict(state_dict.get("knowledge_payload") or {}),
                "term_context": list(state_dict.get("confirmed_terms") or []),
                "metadata": {
                    "loader": self._loader,
                    "state": state_dict,
                    "gateway_context": _gw_ctx,
                    "configurable": (config or {}).get("configurable") or {},
                },
            }

            try:
                ctx, _before_decision = await hook_manager.run_before(ctx)
            except ClarificationNeededError as exc:
                if str(exc.context.get("interrupt_type") or "") == "operation_form":
                    operation_contexts.append(
                        {
                            **exc.context,
                            "tool_call_id": str(exc.context.get("tool_call_id") or tool_call_id),
                            "tool_name": tool_name,
                            "react_round_idx": int(state_dict.get("react_round_idx") or 0),
                        }
                    )
                    logger.info(
                        "[HookAwareToolNode] collected operation_form tool=%s tool_call_id=%s",
                        tool_name,
                        tool_call_id,
                    )
                    continue
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
                            "tool_call_id": tool_call_id,
                            "tool_name": tool_name,
                            "react_round_idx": int(state_dict.get("react_round_idx") or 0),
                        },
                    },
                    goto="analyze_clarify",
                )

            # 处理 before hook 返回的 fail 决策：将 tool_error 转为 ToolMessage 直接返回
            if _before_decision and str(_before_decision.get("action") or "") == "fail":
                result_payload = _before_decision.get("result") or {}
                tool_error = result_payload.get("tool_error")
                if tool_error:
                    from datacloud_analysis.orchestration.execution.tool_wrapper import (  # noqa: PLC0415
                        _format_agent_error_message,
                    )

                    error_type = tool_error.get("error_type", "ToolHookError")
                    error_msg = _format_agent_error_message(tool_error)
                    logger.warning(
                        "[HookAwareToolNode] before hook returned fail action,"
                        " short-circuiting tool=%s error=%s",
                        tool_name,
                        error_type,
                    )
                    if error_type == "OperationCancelled":
                        prebuilt_tool_messages.append(
                            ToolMessage(
                                content=error_msg,
                                name=tool_name,
                                tool_call_id=tool_call_id,
                            )
                        )
                        logger.info(
                            "[HookAwareToolNode] operation cancelled tool=%s tool_call_id=%s",
                            tool_name,
                            tool_call_id,
                        )
                        continue
                    return {
                        "messages": [
                            ToolMessage(
                                content=error_msg,
                                name=tool_name,
                                tool_call_id=tool_call_id,
                            )
                        ]
                    }

            if _before_decision and str(_before_decision.get("action") or "") == "redirect":
                redirect_tool_name = str(_before_decision.get("tool") or "")
                redirect_params = dict(_before_decision.get("params") or {})
                logger.info(
                    "[HookAwareToolNode] before hook redirected tool=%s -> %s params_keys=%s",
                    tool_name,
                    redirect_tool_name,
                    sorted(redirect_params.keys()),
                )
                patched_calls.append(
                    {
                        **tc,
                        "name": redirect_tool_name,
                        "args": redirect_params,
                    }
                )
                continue

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

        if operation_contexts:
            locale = str(((config or {}).get("configurable") or {}).get("locale") or "zh_CN")
            batch_form = build_batch_operation_form(operation_contexts, locale=locale)
            logger.info(
                "[HookAwareToolNode] operation_form batch interrupt actions=%d form_id=%s",
                len(batch_form.get("actions") or []),
                batch_form.get("formId"),
            )
            return Command(
                update={
                    "execution_status": "clarify_needed",
                    "pending_clarification_context": {
                        "interrupt_type": "operation_form",
                        "operation_form": batch_form,
                        "operation_form_contexts": operation_contexts,
                        "react_round_idx": int(state_dict.get("react_round_idx") or 0),
                    },
                },
                goto="analyze_clarify",
            )

        if prebuilt_tool_messages and not patched_calls:
            result_dict = {"messages": prebuilt_tool_messages}
            if _is_operation_formatted_params(state_dict.get("clarification_formatted_params")):
                result_dict["clarification_formatted_params"] = None
                result_dict["clarification_analyze_result"] = None
                result_dict["pending_clarification_context"] = None
            return result_dict

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
        # 注入 InvocationContext，使 SDK 内的 result_file_storage 等能通过
        # get_current_context() 获取 user_id / session_id，与 tool_wrapper.dispatch_tool 对齐。
        _inv_ctx: Any = None
        if _gw_ctx is not None:
            try:
                from datacloud_data_sdk.context import InvocationContext  # type: ignore[import]

                from datacloud_analysis.orchestration.execution.tool_wrapper import (  # noqa: PLC0415
                    _resolve_gateway_user_id,
                )
                from datacloud_analysis.workspace.runtime import (  # noqa: PLC0415
                    resolve_shared_workspace_dir,
                )
            except ImportError:
                pass
            else:
                _gc_user_id = _resolve_gateway_user_id(_gw_ctx)
                _gc_session_id = str(getattr(_gw_ctx, "session_id", "") or "")
                _result_file_storage = getattr(self._loader, "result_file_storage", None)
                # extras 优先从 config["configurable"]["extras"] 读取（worker.py 写入 skill_catalog 等），
                # 回退到 gateway_context.extras（动态路径 OntologyAgent 直接挂在 ctx 上的情况）。
                _config_extras: dict | None = ((config or {}).get("configurable") or {}).get(
                    "extras"
                )
                _extras = (
                    _config_extras
                    if _config_extras is not None
                    else getattr(_gw_ctx, "extras", None)
                )
                _locale = str(((config or {}).get("configurable") or {}).get("locale") or "zh_CN")
                _workspace_dir = str(
                    state_dict.get("workspace_dir")
                    or ((config or {}).get("configurable") or {}).get("workspace_dir")
                    or ""
                )
                _workspace_root = (
                    resolve_shared_workspace_dir(_workspace_dir) if _workspace_dir else None
                )
                _inv_ctx_token = str(
                    getattr(_gw_ctx, "beyond_token", "")
                    or (_extras or {}).get("beyond_token", "")
                    or ""
                )
                _inv_ctx_token_masked = (
                    f"{_inv_ctx_token[:4]}...{_inv_ctx_token[-4:]}"
                    if len(_inv_ctx_token) > 8
                    else ("***" if _inv_ctx_token else "<empty>")
                )
                logger.info(
                    "[invocation-ctx] HookAwareToolNode session=%s user=%s beyond_token=%s",
                    _gc_session_id,
                    _gc_user_id,
                    _inv_ctx_token_masked,
                )
                _inv_ctx = InvocationContext(
                    user_id=_gc_user_id,
                    session_id=_gc_session_id,
                    token=_inv_ctx_token,
                    gateway_context=_gw_ctx,
                    workspace_dir=str(_workspace_root)
                    if _workspace_root is not None
                    else _workspace_dir,
                    result_file_storage=_result_file_storage,
                    extras=_extras,
                    language=_locale,
                )
                _inv_ctx.__enter__()
        try:
            result = await super().ainvoke(patched_state, config, **kwargs)
        finally:
            if _inv_ctx is not None:
                _inv_ctx.__exit__(None, None, None)

        result_dict: dict[str, Any] = dict(result) if isinstance(result, dict) else {"messages": []}
        if prebuilt_tool_messages:
            result_dict["messages"] = [
                *prebuilt_tool_messages,
                *list(result_dict.get("messages") or []),
            ]
        if _is_operation_formatted_params(state_dict.get("clarification_formatted_params")):
            result_dict["clarification_formatted_params"] = None
            result_dict["clarification_analyze_result"] = None
            result_dict["pending_clarification_context"] = None

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
            from datacloud_analysis.i18n.prompts import get_ui_text as _get_ui_text  # noqa: PLC0415
            from datacloud_analysis.orchestration.execution.tool_wrapper import (  # noqa: PLC0415
                _emit_tool_detail,
            )

            _locale = str(((config or {}).get("configurable") or {}).get("locale") or "zh_CN")
            logger.debug(
                "[i18n-diag] hook_aware_tool_node: config.configurable.locale=%r → _locale=%r",
                ((config or {}).get("configurable") or {}).get("locale"),
                _locale,
            )

            _tools_map: dict[str, Any] = dict(self.tools_by_name)  # type: ignore[attr-defined]
            for msg in result_dict.get("messages") or []:
                if not isinstance(msg, ToolMessage) or (msg.name or "") == "finish_react":
                    continue
                params = call_params_map.get(str(msg.tool_call_id or ""), {})
                _tool_name = msg.name or "tool"
                _tool_label = _get_tool_display_label(_tool_name, _tools_map)
                try:
                    async with _gw_ctx.sub_step(_tool_label):
                        if params:
                            await _emit_tool_detail(
                                _gw_ctx, _get_ui_text("tool_input", _locale), params
                            )
                        # 将 msg.content（可能是 Python repr 字符串）解析回 dict，
                        # 保证 coerce_stream_chunk_text 走 dump_json 而非原样透传。
                        _raw = str(msg.content or "")
                        _parsed = _try_parse_to_dict(_raw) if _raw else None
                        _tool_out: Any = _parsed if _parsed is not None else _raw
                        await _emit_tool_detail(
                            _gw_ctx, _get_ui_text("tool_output", _locale), _tool_out
                        )
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

        # ★ 附05 3.2.3：工具解锁 + 推理图谱写入
        _extra_state: dict[str, Any] = {}
        try:
            import contextlib as _ctx  # noqa: PLC0415
            import json as _json  # noqa: PLC0415

            _tool_ctx = (config.get("configurable") or {}).get("tool_context") if config else None

            from datacloud_analysis.tools.tool_pool import (  # noqa: PLC0415
                _get_object_code_by_tool,
            )

            for _msg in result_dict.get("messages") or []:
                if not isinstance(_msg, ToolMessage):
                    continue
                if (_msg.name or "") == "finish_react":
                    continue

                _tool_name = _msg.name or ""
                _raw_content = str(_msg.content or "")
                _result: dict[str, Any] = {}
                with _ctx.suppress(Exception):
                    _result = _json.loads(_raw_content) if _raw_content else {}

                # 1. 查 term_relation 表取下一跳建议（替代 OntologyRelationGraph）
                _source_obj = (
                    next(
                        (obj for obj, tools in _tool_ctx.object_to_tools.items()
                         if _tool_name in tools),
                        None,
                    )
                    if _tool_ctx is not None
                    else _get_object_code_by_tool(_tool_name)
                )
                _suggestions = []
                if _source_obj:
                    _suggestions = _get_next_objects_from_term(
                        _source_obj,
                        allowed_scope=_tool_ctx.allowed_scope if _tool_ctx else [],
                    )

                # 2. 去重过滤（_suggestions 现在是 object_code 字符串列表）
                _existing = set(state_dict.get("active_tools") or [])
                _to_add_objs = list(_suggestions)
                _new_names: list[str] = []
                for _obj_code in _to_add_objs:
                    _obj_tools = (
                        _tool_ctx.object_to_tools.get(_obj_code, [])
                        if _tool_ctx else []
                    )
                    _new_names.extend([t for t in _obj_tools if t not in _existing])
                _to_add = _new_names  # for _update_reasoning_graph compatibility

                # 合并 ParamLinkGraph 的工具级解锁建议（请求级实例）
                try:
                    _plg = _tool_ctx.param_link_graph if _tool_ctx else None
                    if _plg is not None:
                        _param_nexts = _plg.get_next_tools(_tool_name)
                        _param_new = [
                            t
                            for t in _param_nexts
                            if t not in _existing
                            and t not in set(_new_names)
                            and t in (_tool_ctx.tools_map if _tool_ctx else {})
                        ]
                        _new_names = _new_names + _param_new
                except Exception:  # noqa: BLE001
                    pass

                # 3. 统一写入（两路合并后只写一次，避免覆盖）
                if _new_names:
                    if _tool_ctx is not None:
                        self.tools_by_name.update({
                            name: _tool_ctx.tools_map[name]
                            for name in _new_names
                            if name in _tool_ctx.tools_map
                        })
                    _extra_state["active_tools"] = list(_existing) + _new_names

                # 4. 更新 reasoning_graph
                _update_reasoning_graph(state_dict, _tool_name, _result, _to_add, _extra_state)

                # 5. 锚点激活时注入全量工具链路图到 state["messages"]
                try:
                    from datacloud_analysis.tools.param_link_graph import (  # noqa: PLC0415
                        _build_anchor_chain_hint_update,
                    )

                    _plg2 = _tool_ctx.param_link_graph if _tool_ctx else None
                    _anchor_update = _build_anchor_chain_hint_update(
                        tool_name=_tool_name,
                        tool_result=_result or _raw_content,
                        current_anchor=state_dict.get("chain_hint_anchor"),
                        plg=_plg2,
                    )
                    if _anchor_update:
                        _extra_state.update(_anchor_update)
                        logger.info(
                            "[ChainHint] anchor injected: tool=%s anchor=%s "
                            "hint_msgs=%d (plg=%s)",
                            _tool_name,
                            _anchor_update.get("chain_hint_anchor"),
                            len(_anchor_update.get("messages") or []),
                            "ready" if _plg2 is not None else "None",
                        )
                    else:
                        logger.info(
                            "[ChainHint] anchor skipped: tool=%s plg=%s "
                            "current_anchor=%s (not a trigger tool, no new anchor, "
                            "or plg unavailable)",
                            _tool_name,
                            "ready" if _plg2 is not None else "None",
                            state_dict.get("chain_hint_anchor"),
                        )
                except Exception:  # noqa: BLE001
                    logger.warning("[ChainHint] anchor injection failed", exc_info=True)

                # 6. 更新 prev_active_tools 快照（供 llm_call_node 计算 delta）
                #    必须记录"本轮解锁前"的 active_tools，而非解锁后的值，
                #    否则下一轮 delta = active_tools - prev_active_tools 恒为空，
                #    导致串联提示永不注入。用 setdefault 只在本次 after_hook
                #    第一条工具消息时定基线（多条消息共享同一解锁前快照）。
                _extra_state.setdefault(
                    "prev_active_tools",
                    list(state_dict.get("active_tools") or []),
                )

        except Exception:  # noqa: BLE001
            logger.debug("[HookAwareToolNode] tool_pool unlock failed", exc_info=True)

        result_dict.update(_extra_state)
        return result_dict


# ── 辅助函数 ───────────────────────────────────────────────────────────────────


def _update_reasoning_graph(
    state_dict: dict[str, Any],
    tool_name: str,
    result: dict[str, Any],
    suggestions: list[Any],  # list[NextObjectSuggestion]
    extra_updates: dict[str, Any],
) -> None:
    """工具调用完成后，追加一个推理节点到 reasoning_graph（附05 3.2.5-B）。

    Args:
        state_dict: 当前 AgentState 字典。
        tool_name: 刚执行完的工具名。
        result: 工具返回结果（已解析的 dict）。
        suggestions: OntologyRelationGraph.get_next_objects() 返回的建议列表。
        extra_updates: 待写回 result_dict 的更新字典，函数直接修改此字典。
    """
    try:
        from datacloud_analysis.tools.tool_pool import _get_object_code_by_tool  # noqa: PLC0415

        graph: dict[str, Any] = dict(
            state_dict.get("reasoning_graph")
            or {"nodes": {}, "current_node_id": "", "findings": []}
        )
        nodes: dict[str, Any] = dict(graph.get("nodes") or {})
        node_id = f"n{len(nodes)}"

        # 结果摘要
        records = result.get("records") or []
        result_summary = f"{len(records)}条记录"
        if len(records) == 1 and records[0].get("text"):
            result_summary = str(records[0]["text"])[:80]

        # 解锁工具及原因（来自 OWL description）
        unlocked_tools = [s.tool for s in suggestions]
        unlock_reasons = {s.tool: f"{s.relation_type}: {s.reason}" for s in suggestions}
        unlock_hints = {s.tool: s.hint for s in suggestions if s.hint}

        # 当前全部工具快照
        active = list(state_dict.get("active_tools") or [])
        always_on = {
            "get_spans",
            "find_error_spans",
            "get_agent_diag",
            "search_by_tags",
            "match_by_symptom",
            "get_reasoning_map",
            "add_finding",
            "finish_react",
        }
        snapshot = sorted(always_on | set(active) | set(unlocked_tools))

        nodes[node_id] = {
            "id": node_id,
            "object_code": _get_object_code_by_tool(tool_name) or "",
            "action": tool_name,
            "params": {},
            "result_summary": result_summary,
            "unlocked_tools": unlocked_tools,
            "unlock_reasons": unlock_reasons,
            "unlock_hints": unlock_hints,
            "enabled_tools_snapshot": snapshot,
            "status": "done",
        }
        graph["nodes"] = nodes
        graph["current_node_id"] = node_id
        extra_updates["reasoning_graph"] = graph

    except Exception:  # noqa: BLE001
        logger.debug("[_update_reasoning_graph] failed", exc_info=True)


def _is_operation_formatted_params(value: Any) -> bool:
    return isinstance(value, dict) and str(value.get("interrupt_type") or "") == "operation_form"


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


# ── Skill Level1/2 preconditions ────────────────────────────────────────────


def _apply_skill_preconditions_from_message(
    msg: Any,
    state_dict: dict[str, Any],
    extra_state: dict[str, Any],
) -> None:
    """解析 search_ontology ToolMessage 的 hits_json，对 skill 命中执行 Level1/2 preconditions。

    通过 context_has + keyword_match 的 skill wrapper 写入 extra_state["active_tools"]。
    调用方（after_hook）负责将 extra_state 的变更写回 state_dict 和 tools_by_name。

    Args:
        msg: search_ontology 的 ToolMessage。
        state_dict: 当前 AgentState dict（有真实 user_query / trace_id 等字段）。
        extra_state: 待写回的 state 更新 dict。
    """
    import json as _json  # noqa: PLC0415
    import re as _re  # noqa: PLC0415

    content = str(getattr(msg, "content", "") or "")
    m = _re.search(r"<!-- hits_json:(.*?) -->", content, _re.DOTALL)
    if not m:
        return

    try:
        hits: list[dict[str, Any]] = _json.loads(m.group(1))
    except Exception:  # noqa: BLE001
        logger.debug("[skill-preconditions] hits_json parse failed, content=%r", content[:200])
        return

    user_query = str(state_dict.get("user_query") or "")
    existing = set(extra_state.get("active_tools") or state_dict.get("active_tools") or [])

    try:
        from datacloud_analysis.tools.tool_pool import (  # noqa: PLC0415
            TOOL_POOL,
            _parse_skill_frontmatter_cached,
        )
    except ImportError:
        return

    for hit in hits:
        if hit.get("resultType") != "skill":
            continue
        skill_path = hit.get("skillPath") or ""
        if not skill_path:
            continue

        fm = _parse_skill_frontmatter_cached(skill_path)
        if not fm:
            continue

        # Level1: context_has
        if not _check_context_has(fm, state_dict):
            logger.debug("[skill-preconditions] context_has failed for skill_path=%s", skill_path)
            continue

        # Level2: keyword_match
        if not _check_keyword_match(fm, user_query):
            logger.debug(
                "[skill-preconditions] keyword_match failed for skill_path=%s query=%r",
                skill_path,
                user_query,
            )
            continue

        wrapper_name = f"activate_skill_{fm['name'].replace('-', '_')}"
        if wrapper_name in TOOL_POOL and wrapper_name not in existing:
            existing.add(wrapper_name)
            if "active_tools" not in extra_state:
                extra_state["active_tools"] = list(state_dict.get("active_tools") or [])
            extra_state["active_tools"].append(wrapper_name)
            logger.debug("[skill-preconditions] unlocked wrapper %s", wrapper_name)


def _check_context_has(fm: dict[str, Any], state_dict: dict[str, Any]) -> bool:
    """执行 preconditions 中所有 context_has 规则，全部通过返回 True。"""
    for rule in fm.get("preconditions") or []:
        if rule.get("type") != "context_has":
            continue
        field = rule.get("field", "")
        if not state_dict.get(field):
            return False
    return True


def _check_keyword_match(fm: dict[str, Any], user_query: str) -> bool:
    """执行 preconditions 中所有 keyword_match 规则，全部通过返回 True。

    每条 keyword_match 规则：关键词列表中任一匹配即该条规则通过。
    """
    for rule in fm.get("preconditions") or []:
        if rule.get("type") != "keyword_match":
            continue
        keywords: list[str] = rule.get("keywords") or []
        if not any(kw in user_query for kw in keywords):
            return False
    return True
