"""user_clarify_node：interrupt 等待用户澄清，格式化后写入 clarification_formatted_params。"""

from __future__ import annotations

import contextlib
import json
import logging
from types import SimpleNamespace
from typing import Any

from datacloud_data_sdk.executor.kb_cascade_delete.models import CascadeDeleteContext
from datacloud_data_sdk.executor.kb_cascade_delete.selection import (
    CascadeSelectionError,
    build_signed_cascade_execution,
    extract_cascade_selections,
)
from datacloud_platform import get_platform
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from datacloud_analysis.i18n.prompts import get_ui_text
from datacloud_analysis.orchestration.gateway_user import get_gateway_user_id
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tool_hook_plugins.builtin.operation_confirmation_plugin import (
    find_operation_action,
    restore_action_params,
)
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    _scope_code_from_tool,
)

_base_id = get_platform()._default_base_id()  # fixme: pass base_id explicitly

logger = logging.getLogger(__name__)

_OPERATION_FORM_INTERRUPT_TYPE = "operation_form"


def _make_pm_key(paradigm_id: str, kid: int | str) -> str:
    """Build path_mapping key from paradigm_id and kid.

    Must match the key formats used by build_paradigm_list
    in ``datacloud_knowledge.intent.clarification.cartesian._paradigm``:

    - paradigmId="1" (select):   ``str(kid)``                  → "1", "2", ...
    - paradigmId="2" (groupBy):  ``f"g{i+1}"``                 → "g1", "g2", ...
    - paradigmId="4" (orderBy):  ``f"o{i+1}"``                 → "o1", "o2", ...
    """
    kid_str = str(kid)
    if paradigm_id == "1":
        return kid_str
    if paradigm_id == "2":
        return f"g{kid_str}"
    if paradigm_id == "4":
        return f"o{kid_str}"
    return kid_str  # fallback


def _get_gateway_user_id(config: RunnableConfig) -> str | None:
    """从 gateway_context 获取用户 ID；缺失时不做降级。"""
    configurable = config.get("configurable") or {}
    if not isinstance(configurable, dict):
        logger.info(
            "[user_clarify] user_id lookup: configurable is not dict type=%s",
            type(configurable).__name__,
        )
        return None
    # SDK 直调模式：user_code 直接写入 configurable，无 gateway_context
    direct_user_code = str(configurable.get("user_code") or "").strip()
    if direct_user_code and not configurable.get("gateway_context"):
        return direct_user_code

    gateway_context = configurable.get("gateway_context")
    logger.info(
        "[user_clarify] user_id lookup: configurable_keys=%s gateway_context_type=%s "
        "gateway_user_id=%r header_type=%s header_user_id=%r header_user_code=%r "
        "command_header_type=%s command_user_id=%r command_user_code=%r",
        sorted(str(key) for key in configurable),
        type(gateway_context).__name__ if gateway_context is not None else None,
        getattr(gateway_context, "user_id", None),
        type(getattr(gateway_context, "header", None)).__name__
        if getattr(gateway_context, "header", None) is not None
        else None,
        getattr(getattr(gateway_context, "header", None), "user_id", None),
        getattr(getattr(gateway_context, "header", None), "user_code", None),
        type(getattr(getattr(gateway_context, "current_command", None), "header", None)).__name__
        if getattr(getattr(gateway_context, "current_command", None), "header", None) is not None
        else None,
        getattr(
            getattr(getattr(gateway_context, "current_command", None), "header", None),
            "user_id",
            None,
        ),
        getattr(
            getattr(getattr(gateway_context, "current_command", None), "header", None),
            "user_code",
            None,
        ),
    )
    return get_gateway_user_id(gateway_context)


def _is_operation_form_context(ctx: dict[str, Any], analyze_result: dict[str, Any]) -> bool:
    return (
        str(ctx.get("interrupt_type") or "") == _OPERATION_FORM_INTERRUPT_TYPE
        or str(analyze_result.get("interrupt_type") or "") == _OPERATION_FORM_INTERRUPT_TYPE
    )


def _operation_form_from_context(
    ctx: dict[str, Any],
    analyze_result: dict[str, Any],
) -> dict[str, Any]:
    form = ctx.get("operation_form") or analyze_result.get("operation_form") or {}
    return dict(form) if isinstance(form, dict) else {}


def _operation_contexts_from_state(
    ctx: dict[str, Any],
    analyze_result: dict[str, Any],
) -> list[dict[str, Any]]:
    contexts = ctx.get("operation_form_contexts") or analyze_result.get("operation_form_contexts")
    if isinstance(contexts, list):
        return [dict(item) for item in contexts if isinstance(item, dict)]
    return []


def _normalize_operation_form(
    operation_form: dict[str, Any],
    *,
    tool_name: str,
    tool_call_id: str,
) -> dict[str, Any]:
    """Normalize legacy single-action form into the batch actions[] protocol."""
    actions_raw = operation_form.get("actions")
    if isinstance(actions_raw, list):
        actions = [dict(item) for item in actions_raw if isinstance(item, dict)]
        return {
            **operation_form,
            "actions": [_normalize_operation_action_for_frontend(action) for action in actions],
        }

    action = {
        "toolCallId": tool_call_id,
        "toolName": tool_name,
        "actionCode": str(operation_form.get("actionCode") or tool_name),
        "actionName": str(
            operation_form.get("actionName") or operation_form.get("actionCode") or tool_name
        ),
        "title": str(operation_form.get("title") or ""),
        "description": str(operation_form.get("description") or ""),
        "rule": list(operation_form.get("rule") or []),
    }
    return {
        "schemaVersion": str(operation_form.get("schemaVersion") or "1.0"),
        "formId": str(operation_form.get("formId") or ""),
        "title": str(operation_form.get("title") or ""),
        "description": str(operation_form.get("description") or ""),
        "actions": [action],
    }


def _normalize_operation_resume(
    resume_value: Any,
    operation_form: dict[str, Any],
) -> dict[str, Any]:
    """Normalize frontend resume payload.

    New clients return the whole batch form with actions[].confirmed and edited fieldValue values.
    Legacy clients may return top-level confirmed/rule for a single pending action.
    """
    payload = dict(resume_value) if isinstance(resume_value, dict) else {}
    actions = payload.get("actions")
    if isinstance(actions, list):
        return {
            **operation_form,
            **payload,
            "actions": [dict(a) for a in actions if isinstance(a, dict)],
        }

    pending_actions = list(operation_form.get("actions") or [])
    if len(pending_actions) == 1 and isinstance(pending_actions[0], dict):
        action = dict(pending_actions[0])
        action["confirmed"] = bool(payload.get("confirmed"))
        if payload.get("reason"):
            action["reason"] = str(payload.get("reason") or "")
        if isinstance(payload.get("rule"), list):
            action["rule"] = payload["rule"]
        return {**operation_form, "actions": [action]}

    return {**operation_form, "actions": []}


def _same_operation_form(existing: dict[str, Any] | None, operation_form: dict[str, Any]) -> bool:
    return (
        isinstance(existing, dict)
        and str(existing.get("interrupt_type") or "") == _OPERATION_FORM_INTERRUPT_TYPE
        and str(existing.get("formId") or "") == str(operation_form.get("formId") or "")
    )


def _operation_action_tool_call_id(action: dict[str, Any]) -> str:
    return str(action.get("tool_call_id") or action.get("toolCallId") or "")


def _operation_action_tool_name(action: dict[str, Any]) -> str:
    return str(action.get("tool_name") or action.get("toolName") or "")


def _normalize_operation_action_for_frontend(action: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(action)
    normalized["toolCallId"] = _operation_action_tool_call_id(normalized)
    normalized["toolName"] = _operation_action_tool_name(normalized)
    normalized.pop("tool_call_id", None)
    normalized.pop("tool_name", None)
    return normalized


def _find_operation_action(config: RunnableConfig, tool_name: str) -> Any | None:
    configurable = config.get("configurable") or {}
    if not isinstance(configurable, dict):
        configurable = {}
    loader = configurable.get("loader")
    if loader is None:
        gateway_context = configurable.get("gateway_context")
        loader = getattr(gateway_context, "loader", None)
    if loader is None:
        return None
    return find_operation_action(loader, tool_name)


def _operation_action_meta_from_context(context: dict[str, Any]) -> Any | None:
    confirm_context = context.get("operation_confirm_context")
    if not isinstance(confirm_context, dict):
        return None
    action_family = str(confirm_context.get("actionFamily") or "").strip().lower()
    if action_family == "insert":
        return SimpleNamespace(action_family=action_family)
    structured_input = context.get("structured_input")
    if (
        action_family == "write"
        and isinstance(structured_input, dict)
        and isinstance(structured_input.get("records"), list)
    ):
        return SimpleNamespace(action_family=action_family)
    if action_family:
        logger.debug(
            "[user_clarify] skip thin action meta fallback for non-record operation family=%s",
            action_family,
        )
        return None
    return None


async def _handle_operation_form_clarify(
    *,
    ctx: dict[str, Any],
    analyze_result: dict[str, Any],
    tool_name: str,
    config: RunnableConfig,
    language: str,
) -> dict[str, Any]:
    raw_form = _operation_form_from_context(ctx, analyze_result)
    operation_form = _normalize_operation_form(
        raw_form,
        tool_name=tool_name,
        tool_call_id=str(ctx.get("tool_call_id") or analyze_result.get("tool_call_id") or ""),
    )
    operation_contexts = _operation_contexts_from_state(ctx, analyze_result)
    context_by_id = {
        str(item.get("tool_call_id") or ""): item
        for item in operation_contexts
        if str(item.get("tool_call_id") or "")
    }
    logger.info(
        "[user_clarify] operation_form suspend tool=%s form_id=%s actions=%d",
        tool_name,
        operation_form.get("formId"),
        len(operation_form.get("actions") or []),
    )
    resume_value = interrupt(
        {
            "prompt": get_ui_text("operation_form_interrupt_prompt", language),
            "reason_code": "OPERATION_FORM_CONFIRMATION",
            "interrupt_type": _OPERATION_FORM_INTERRUPT_TYPE,
            "operation_form": operation_form,
        }
    )
    payload = _normalize_operation_resume(resume_value, operation_form)
    form_id = str(payload.get("formId") or operation_form.get("formId") or "")
    if form_id != str(operation_form.get("formId") or ""):
        raise CascadeSelectionError("CASCADE_ITEM_TAMPERED: formId 不匹配")
    pending_actions = [dict(a) for a in operation_form.get("actions") or [] if isinstance(a, dict)]
    resume_action_list = [dict(a) for a in payload.get("actions") or [] if isinstance(a, dict)]
    resume_actions = {
        _operation_action_tool_call_id(action): action
        for action in resume_action_list
        if _operation_action_tool_call_id(action)
    }
    formatted_actions: list[dict[str, Any]] = []
    params_by_tool_call_id: dict[str, dict[str, Any]] = {}

    for index, pending_action in enumerate(pending_actions):
        current_tool_call_id = _operation_action_tool_call_id(pending_action)
        current_tool_name = _operation_action_tool_name(pending_action) or tool_name
        resume_action = resume_actions.get(current_tool_call_id)
        action_returned = resume_action is not None
        if resume_action is None and index < len(resume_action_list):
            candidate_action = resume_action_list[index]
            candidate_tool_call_id = _operation_action_tool_call_id(candidate_action)
            if (
                not candidate_tool_call_id
                or candidate_tool_call_id == current_tool_call_id
                or len(resume_action_list) == len(pending_actions)
            ):
                resume_action = candidate_action
                action_returned = True
        if resume_action is None:
            resume_action = {}
        context = context_by_id.get(current_tool_call_id, {})
        cascade_mode = (
            pending_action.get("formMode") == "cascade_delete"
            or isinstance(context.get("cascade_context"), dict)
        )
        if cascade_mode:
            confirmed = (
                resume_action.get("confirmed") is True
                if type(resume_action.get("confirmed")) is bool
                else False
            )
        else:
            confirmed = (
                bool(resume_action.get("confirmed"))
                if "confirmed" in resume_action
                else action_returned
            )
        rule_raw = resume_action.get("rule")
        if not isinstance(rule_raw, list):
            rule_raw = pending_action.get("rule") or []
        rule = list(rule_raw) if isinstance(rule_raw, list) else []
        reason = str(
            resume_action.get("reason") or get_ui_text("operation_cancelled_reason", language)
        )

        action_result: dict[str, Any] = {
            "tool_call_id": current_tool_call_id,
            "tool_name": current_tool_name,
            "formId": form_id,
            "confirmed": confirmed,
            "reason": "" if confirmed else reason,
            "rule": rule,
            "params": {},
        }
        if confirmed:
            action_meta = _find_operation_action(config, current_tool_name)
            if action_meta is None:
                action_meta = _operation_action_meta_from_context(context)
            original_params = dict(
                context.get("structured_input")
                or analyze_result.get("structured_input")
                or ctx.get("structured_input")
                or {}
            )
            if cascade_mode:
                raw_cascade_context = context.get("cascade_context")
                if not isinstance(raw_cascade_context, dict):
                    raise CascadeSelectionError("CASCADE_CONTEXT_NOT_FOUND")
                cascade_context = CascadeDeleteContext.from_dict(raw_cascade_context)
                selections = extract_cascade_selections(rule)
                params = original_params
                params["_cascadeDelete"] = build_signed_cascade_execution(
                    context=cascade_context,
                    selections=selections,
                    form_id=form_id,
                    tool_call_id=current_tool_call_id,
                )
            else:
                params = restore_action_params(
                    rule,
                    action=action_meta,
                    original_params=original_params,
                )
            params["userConfirmed"] = True
            params["_operationConfirm"] = {
                "formId": form_id,
                "toolCallId": current_tool_call_id,
                "confirmed": True,
            }
            action_result["params"] = params
        formatted_actions.append(action_result)
        if current_tool_call_id:
            params_by_tool_call_id[current_tool_call_id] = action_result

    first_action = formatted_actions[0] if formatted_actions else {}
    logger.info(
        "[user_clarify] operation_form resumed form_id=%s actions=%d confirmed=%d",
        form_id,
        len(formatted_actions),
        sum(1 for action in formatted_actions if action.get("confirmed")),
    )
    return {
        "clarification_formatted_params": {
            "interrupt_type": _OPERATION_FORM_INTERRUPT_TYPE,
            "formId": form_id,
            "actions": formatted_actions,
            "params_by_tool_call_id": params_by_tool_call_id,
            # Legacy single-action compatibility.
            "tool_name": first_action.get("tool_name", tool_name),
            "confirmed": bool(first_action.get("confirmed")),
            "reason": str(first_action.get("reason") or ""),
            "rule": first_action.get("rule") or [],
            "params": first_action.get("params") or {},
        },
        "clarify_abort": False,
    }


async def user_clarify_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """调用 interrupt() 暂停等待用户澄清，格式化回复后写入 clarification_formatted_params。"""
    ctx = dict(state.get("pending_clarification_context") or {})
    analyze_result = dict(state.get("clarification_analyze_result") or {})

    tool_name = str(ctx.get("tool_name") or analyze_result.get("tool_name") or "")
    query = str(ctx.get("query") or analyze_result.get("query") or "")
    structured_input = dict(
        ctx.get("structured_input") or analyze_result.get("structured_input") or {}
    )
    is_compute: bool = bool(ctx.get("is_compute") or tool_name.startswith("compute_"))
    clarify_knowledge = str(analyze_result.get("clarify_knowledge") or "")
    paradigm_list: list[dict[str, Any]] = list(analyze_result.get("paradigm_list") or [])

    # 提取 language（从 configurable.locale，格式为 zh_CN / en_US）
    _configurable_cl = config.get("configurable") or {}
    language = str(_configurable_cl.get("locale") or "zh_CN")

    # DIAG: 记录 paradigm 结构（首个条目）以核查 choiceKeyword/recall 格式
    if paradigm_list:
        _sample = paradigm_list[0]
        _results = list(_sample.get("paradigmResult") or [])
        logger.info(
            "[user_clarify] DIAG paradigm[0]: paradigmId=%s paradigmName=%s result_count=%d "
            "first_result=%s",
            _sample.get("paradigmId"),
            _sample.get("paradigmName"),
            len(_results),
            _results[0] if _results else None,
        )

    if _is_operation_form_context(ctx, analyze_result):
        raw_form = _operation_form_from_context(ctx, analyze_result)
        operation_form = _normalize_operation_form(
            raw_form,
            tool_name=tool_name,
            tool_call_id=str(ctx.get("tool_call_id") or analyze_result.get("tool_call_id") or ""),
        )
        existing = state.get("clarification_formatted_params")
        if _same_operation_form(existing, operation_form):
            logger.warning(
                "[user_clarify] DUPLICATE GUARD: same operation form already formatted"
                " → aborting duplicate path form_id=%s",
                operation_form.get("formId"),
            )
            return {"clarify_abort": True}
        return await _handle_operation_form_clarify(
            ctx=ctx,
            analyze_result=analyze_result,
            tool_name=tool_name,
            config=config,
            language=language,
        )

    # ── 重复路径中止守卫 ──────────────────────────────────────────────────────────────────────────
    # 当 OpenGauss checkpoint blob 丢失时，tools 节点被错误激活 → ClarificationNeededError →
    # analyze_clarify → user_clarify，走到这里时 clarification_formatted_params 已由并发恢复路径写入。
    # 若此时再调用 interrupt()，会产生第二条完整 graph 路径（duplicate respond 推送）。
    # 检测到 clarification_formatted_params 已设置 → 说明是重复路径，直接 Command(goto=END) 中止。
    _existing_clarify_fp: dict[str, Any] | None = state.get("clarification_formatted_params")
    if _existing_clarify_fp:
        logger.warning(
            "[user_clarify] DUPLICATE GUARD: clarification_formatted_params already set"
            " → aborting duplicate path to prevent double respond tool=%s",
            tool_name,
        )
        return {"clarify_abort": True}

    if not paradigm_list:
        # _route_after_analyze 已将空 paradigm_list 路由到 tool_dispatcher；
        # 此分支仅为安全兜底，使用 pre_filled_params 直接返回。
        pre_filled: dict[str, Any] = dict(
            analyze_result.get("pre_filled_params") or structured_input
        )
        logger.info(
            "[user_clarify] paradigm_list empty, using pre_filled_params tool=%s", tool_name
        )
        return {
            "clarification_formatted_params": {
                "tool_name": tool_name,
                "is_complex": is_compute,
                "params": pre_filled,
            },
            "pending_clarification_context": None,
            "clarification_analyze_result": None,
            "clarify_abort": False,
        }

    logger.info(
        "[user_clarify] SUSPEND POINT: about to interrupt tool=%s paradigm_count=%d"
        " — graph will pause here until user submits clarification",
        tool_name,
        len(paradigm_list),
    )
    resume_value: Any = interrupt(
        {
            "prompt": get_ui_text("clarify_interrupt_prompt", language),
            "reason_code": "PARADIGM_CLARIFICATION",
            "ask_user_payload": {"paradigmList": paradigm_list, "query": query},
            "_clarify_knowledge": clarify_knowledge,
        }
    )
    # ── 恢复点：interrupt() 返回说明 ResumeCommand 已送达，以下代码仅在 resume 时执行 ──
    logger.info(
        "[user_clarify] RESUME POINT: interrupt returned tool=%s is_compute=%s"
        " resume_value_type=%s resume_value=%s",
        tool_name,
        is_compute,
        type(resume_value).__name__,
        json.dumps(resume_value, ensure_ascii=False, default=str)[:500]
        if resume_value is not None
        else "None",
    )

    # resume_value 结构：{"paradigmList": [{"paradigmList": [...items...], ...}]}
    # 这里展开为 provider.finalize_query_clarification 需要的顶层 paradigmList
    paradigm_list_from_resume: list[dict[str, Any]] = []
    meta_paradigm_list: list[dict[str, Any]] = []
    if isinstance(resume_value, dict):
        outer = list(resume_value.get("paradigmList") or [])
        if outer and isinstance(outer[0], dict):
            paradigm_list_from_resume = list(outer[0].get("paradigmList") or [])
        _meta = resume_value.get("metadata") or {}
        meta_paradigm_list = list(_meta.get("paradigmList") or [])
    # meta_paradigm_list 优先从 resume_value.metadata 取；动态路径不含 clarify_knowledge，
    # 从 state 的 analyze_result 兜底补充
    if not meta_paradigm_list:
        meta_paradigm_list = list(analyze_result.get("paradigm_list") or [])
    form_str = json.dumps({"paradigmList": paradigm_list_from_resume}, ensure_ascii=False)

    # 以恢复表单为准：根据前端保留的 keyword 重建 path_mapping，并裁剪 structured_input.select。
    # SDK 的 _apply_selections 先 deep_copy(structured_input) 再按 path_mapping 覆写，
    # 未被覆写的位置会原样保留，因此两者必须同步裁剪，否则已删除字段会残留在查询结果中。
    _effective_knowledge = clarify_knowledge
    _effective_structured_input = dict(structured_input)
    if _effective_knowledge and paradigm_list_from_resume:
        try:
            _kd = json.loads(_effective_knowledge)
            _pm = _kd.get("path_mapping") or {}
            if _pm:
                # 收集前端保留的 keyword 集合。
                # paradigm_list_from_resume 来自 resume_value.paradigmList[0].paradigmList，
                # 结构与原始 paradigm_list 一致：每个 group 内的 paradigmResult 子项才携带 keyword。
                _remaining_kw: set[str] = set()
                for group in paradigm_list_from_resume:
                    if not isinstance(group, dict):
                        continue
                    for item in group.get("paradigmResult") or []:
                        kw = item.get("keyword") if isinstance(item, dict) else None
                        if kw:
                            _remaining_kw.add(str(kw))
                # 从 metadata.paradigmList（含 paradigmId + kid）构造应保留的
                # path_mapping 键。不同 paradigm 使用不同键格式：
                #   select(1): "1"/"2"/...  groupBy(2): "g1"/"g2"/...  orderBy(4): "o1"/"o2"/...
                _kept_pm_keys: set[str] = set()
                for paradigm in meta_paradigm_list:
                    pid = str(paradigm.get("paradigmId", ""))
                    for item in paradigm.get("paradigmResult") or []:
                        kid = item.get("kid")
                        kw = str(item.get("keyword", ""))
                        if kid is not None and kw in _remaining_kw:
                            _kept_pm_keys.add(_make_pm_key(pid, kid))
                _filtered_pm = {k: v for k, v in _pm.items() if k in _kept_pm_keys}
                if _filtered_pm != _pm:
                    # 收集仍被引用的 select 索引，裁剪 structured_input.select
                    _keep_idx = set()
                    for _pv in _filtered_pm.values():
                        if _pv.startswith("select."):
                            with contextlib.suppress(IndexError, ValueError):
                                _keep_idx.add(int(_pv.split(".")[1]))
                    logger.info(
                        "[user_clarify] path_mapping pruned: before=%s after=%s"
                        " kept_keys=%s remaining_keywords=%s select_indices_to_keep=%s",
                        _pm,
                        _filtered_pm,
                        sorted(_kept_pm_keys),
                        _remaining_kw,
                        _keep_idx,
                    )
                    _kd["path_mapping"] = _filtered_pm
                    _effective_knowledge = json.dumps(_kd, ensure_ascii=False)
                    if _keep_idx:
                        _orig_sel = list(_effective_structured_input.get("select") or [])
                        _effective_structured_input["select"] = [
                            v for i, v in enumerate(_orig_sel) if i in _keep_idx
                        ]
        except (ValueError, TypeError):
            pass

    scope_code = _scope_code_from_tool(tool_name)
    user_id = _get_gateway_user_id(config)
    result = get_platform().finalize_clarification(
        base_id=_base_id,
        query=query,
        ontology_code=scope_code,
        structured_input=_effective_structured_input,
        mode="compute" if is_compute else "query",
        needs_clarification=True,
        form=form_str,
        metadata=_effective_knowledge,
        user_id=user_id,
        persist_confirmed_synonyms=True,
        language=language,
    )
    formatted_params = result.structured_input
    persisted_synonyms = result.persisted_synonyms
    if persisted_synonyms is not None:
        created_ids = persisted_synonyms.get("created_ids", [])
        logger.info(
            "[user_clarify] persisted confirmed synonyms user_id=%s count=%d",
            user_id or "",
            len(created_ids),
        )
    elif not user_id:
        logger.info("[user_clarify] skip synonym persistence: gateway user_id is empty")

    logger.info("[user_clarify] formatted params keys=%s", sorted(formatted_params.keys()))

    return {
        "clarification_formatted_params": {
            "tool_name": tool_name,
            "is_complex": is_compute,
            "params": formatted_params,
            # paradigm_list 保存供 V0.3 早返回做 keyword→choiceKeyword→fieldCode 两步翻译
            "paradigm_list": paradigm_list,
        },
        "clarify_abort": False,
        # pending_clarification_context 不在此处清空：
        # HookAwareToolNode 返回 Command(goto="analyze_clarify") 时，Command.update 会在
        # 同一个 pregel tick 内写入 pending_clarification_context，若此处同时写 None，
        # LangGraph 的 LastValue channel 会抛 InvalidUpdateError（同 tick 多次写同一 key）。
        # analyze_clarify_node 每次被触发时均从 Command.update 读到最新值，无需在此清空。
        # clarification_analyze_result 同样保留（不清空）：
        # before_call_back 在旧版 user_clarify_node 不写 paradigm_list 时需要兜底读取；
        # analyze_clarify_node 下次运行时会覆盖。
    }
