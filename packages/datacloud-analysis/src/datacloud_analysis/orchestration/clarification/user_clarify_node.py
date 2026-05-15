"""user_clarify_node：interrupt 等待用户澄清，格式化后写入 clarification_formatted_params。"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from datacloud_knowledge.provider import finalize_query_clarification
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from datacloud_analysis.i18n.prompts import get_ui_text
from datacloud_analysis.orchestration.gateway_user import get_gateway_user_id
from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    _scope_code_from_tool,
)

logger = logging.getLogger(__name__)


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
                # 收集前端保留的 keyword 集合（前端提交条目无 kid，用 keyword 匹配）
                _remaining_kw = {
                    str(item.get("keyword"))
                    for paradigm in paradigm_list_from_resume
                    for item in (paradigm.get("paradigmResult") or [])
                    if item.get("keyword")
                }
                # 从 metadata.paradigmList（含 kid）反查对应的 kid
                _remaining_kids = {
                    str(item.get("kid"))
                    for paradigm in meta_paradigm_list
                    for item in (paradigm.get("paradigmResult") or [])
                    if item.get("kid") is not None and str(item.get("keyword")) in _remaining_kw
                }
                _filtered_pm = {k: v for k, v in _pm.items() if k in _remaining_kids}
                if _filtered_pm != _pm:
                    # 收集仍被引用的 select 索引，裁剪 structured_input.select
                    _keep_idx = set()
                    for _pv in _filtered_pm.values():
                        if _pv.startswith("select."):
                            with contextlib.suppress(IndexError, ValueError):
                                _keep_idx.add(int(_pv.split(".")[1]))
                    logger.info(
                        "[user_clarify] path_mapping pruned: before=%s after=%s"
                        " remaining_keywords=%s select_indices_to_keep=%s",
                        _pm,
                        _filtered_pm,
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
    finalized = finalize_query_clarification(
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
    formatted_params = finalized.structured_input
    if finalized.persisted_synonyms is not None:
        logger.info(
            "[user_clarify] persisted confirmed synonyms user_id=%s count=%d",
            user_id or "",
            len(finalized.persisted_synonyms.created_ids),
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
