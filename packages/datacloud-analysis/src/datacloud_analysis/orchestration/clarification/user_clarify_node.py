"""user_clarify_node：interrupt 等待用户澄清，格式化后写入 clarification_formatted_params。"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from datacloud_analysis.orchestration.state import AgentState
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    _format_clarification,
)

logger = logging.getLogger(__name__)


async def user_clarify_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """调用 interrupt() 暂停等待用户澄清，格式化回复后写入 clarification_formatted_params。"""
    ctx = dict(state.get("pending_clarification_context") or {})
    analyze_result = dict(state.get("clarification_analyze_result") or {})

    tool_name = str(ctx.get("tool_name") or analyze_result.get("tool_name") or "")
    query = str(ctx.get("query") or analyze_result.get("query") or "")
    structured_input = dict(
        ctx.get("structured_input") or analyze_result.get("structured_input") or {}
    )
    is_compute: bool = bool(ctx.get("is_compute") or analyze_result.get("is_complex"))
    clarify_knowledge = str(analyze_result.get("clarify_knowledge") or "")
    paradigm_list: list[dict[str, Any]] = list(analyze_result.get("paradigm_list") or [])

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
            "prompt": "查询条件存在歧义，请确认查询维度",
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
    # _format_clarification 期望：{"paradigmList": [...items...]}（一层展开）
    paradigm_list_from_resume: list[dict[str, Any]] = []
    if isinstance(resume_value, dict):
        outer = list(resume_value.get("paradigmList") or [])
        if outer and isinstance(outer[0], dict):
            paradigm_list_from_resume = list(outer[0].get("paradigmList") or [])
    form_str = json.dumps({"paradigmList": paradigm_list_from_resume}, ensure_ascii=False)

    formatted_params: dict[str, Any] = _format_clarification(
        query,
        structured_input,
        form_str,
        clarify_knowledge,
        is_compute=is_compute,
    )

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
