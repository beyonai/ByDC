"""Built-in tool hook: 知识增强与查询澄清（层 B 注入）。

v2 改造：读取 LLM 填写的 ambiguous_params 元字段，按需触发知识增强/追问，
不再依赖 intend_node 预注入的 knowledge_payload。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from datacloud_analysis.tool_hook_plugins.types import HookContext, HookDecision

# 模块级别别名，方便测试 patch；运行时由 before_call_back 内部延迟导入覆盖
try:
    from langgraph.types import interrupt  # type: ignore[import]
except ImportError:  # pragma: no cover
    interrupt = None  # type: ignore[assignment]

PLUGIN_ID = "builtin.query_clarification"
PRIORITY = 100  # 低于 semantic_param_enhancer(200)，优先执行
ENABLED = True

logger = logging.getLogger(__name__)

_DATA_TOOL_PREFIXES: frozenset[str] = frozenset({"query_", "data_query_", "compute_"})


def _is_data_tool(tool_name: str) -> bool:
    """判断是否为数据类工具（query_/data_query_/compute_ 前缀）。"""
    return any(tool_name.startswith(p) for p in _DATA_TOOL_PREFIXES)


def _is_data_query_tool(tool_name: str) -> bool:
    """判断是否为 data_query_* 自然语言查询工具（支持 contextKnowledge 参数）。"""
    return tool_name.startswith("data_query_")


def _format_knowledge_for_prompt(knowledge_json: str) -> str:
    """将 knowledge JSON 转为人类可读字段映射文本。"""
    try:
        data = json.loads(knowledge_json)
        items = data.get("paradigmList", [])
        lines = []
        for item in items:
            name = item.get("name") or item.get("termName") or ""
            desc = item.get("fieldName") or item.get("description") or ""
            if name and desc:
                lines.append(f"{name} → {desc}")
        return "\n".join(lines) if lines else knowledge_json
    except Exception:
        return knowledge_json


async def _call_query_clarification(
    user_query: str,
    ambiguous_params: list[str],
    tool_name: str,
    tool_params: dict[str, Any],
) -> Any:
    """调用知识增强/澄清接口，返回结构化结果。

    返回对象应含：
    - needs_clarification: bool
    - form: str（JSON 格式的追问表单，needs_clarification=True 时有效）
    - knowledge: str（知识摘要，needs_clarification=False 时有效）
    """
    from datacloud_knowledge.intent import analyze_query_clarification  # type: ignore[import]
    return await analyze_query_clarification(
        user_query,
        ambiguous_params=ambiguous_params,
        tool_name=tool_name,
        tool_params=tool_params,
    )



async def before_call_back(ctx: HookContext) -> HookDecision | None:
    """层 B 知识增强：读取 LLM 填写的 ambiguous_params，按需触发知识增强或追问中断。

    流程：
    1. 非数据工具 → 直接跳过（返回 None）
    2. 从 tool_params 剥除三个元字段（intent_reason / extraction_confidence / ambiguous_params）
    3. 记录运营日志（含 tool_params 参数提取信息）
    4. ambiguous_params=[] → 直接返回 None（无需知识增强）
    5. ambiguous_params 非空 → 调用 _call_query_clarification
       a. needs_clarification=False → 注入 contextKnowledge（仅 data_query_* 工具）
       b. needs_clarification=True  → interrupt 追问，恢复后重建 tool_params
    """
    tool_name = ctx.get("tool_name", "")

    # 非数据工具不处理
    if not _is_data_tool(tool_name):
        return None

    # ── 剥除三个元字段（LLM 填写，hook 层消费后不透传给底层实现）─────────────────
    tool_params: dict[str, Any] = ctx.get("tool_params") or {}
    intent_reason: str = str(tool_params.pop("intent_reason", "") or "")
    extraction_confidence: float = float(tool_params.pop("extraction_confidence", 1.0) or 1.0)
    ambiguous_params: list[str] = list(tool_params.pop("ambiguous_params", None) or [])

    # ── 运营日志：记录参数提取情况 ───────────────────────────────────────────────
    logger.info(
        "[tool_intent] tool=%s | confidence=%.2f | ambiguous=%s | triggered=%s\n"
        "  intent : %s\n"
        "  params : %s",
        tool_name,
        extraction_confidence,
        ambiguous_params,
        bool(ambiguous_params),
        intent_reason,
        tool_params,
    )

    # ── 无歧义：直接跳过知识增强 ─────────────────────────────────────────────────
    if not ambiguous_params:
        return None

    # ── 有歧义：调用知识增强/澄清接口 ────────────────────────────────────────────
    try:
        result = await _call_query_clarification(
            user_query=ctx.get("user_query", ""),
            ambiguous_params=ambiguous_params,
            tool_name=tool_name,
            tool_params=tool_params,
        )
    except Exception as exc:
        logger.warning("[query_clarification_plugin] _call_query_clarification failed: %s", exc)
        return None

    needs_clarification: bool = getattr(result, "needs_clarification", False)
    knowledge_str: str = getattr(result, "knowledge", "") or ""
    form_str: str = getattr(result, "form", "") or ""

    if needs_clarification:
        # 追问中断（§6.7 层 B 追问逻辑）
        try:
            paradigm_list = json.loads(form_str).get("paradigmList", [])
        except Exception:
            paradigm_list = []
        resume_value = interrupt({
            "prompt": "查询条件存在歧义，请确认查询维度",
            "reason_code": "PARADIGM_CLARIFICATION",
            "ask_user_payload": {
                "paradigmList": paradigm_list,
            },
        })
        # interrupt 恢复后：重建 tool_params，避免死循环
        _apply_resume_to_params(ctx, tool_name, resume_value, ctx.get("user_query", ""))
        return {"action": "patch", "patch": {"tool_params": dict(ctx["tool_params"])}}

    # 层 B 知识注入：仅对 data_query_* 工具注入 contextKnowledge
    if knowledge_str and _is_data_query_tool(tool_name):
        patched_params = dict(tool_params)
        patched_params["contextKnowledge"] = knowledge_str
        ctx["tool_params"] = patched_params
        return {"action": "patch", "patch": {"tool_params": patched_params}}

    return None


def _apply_resume_to_params(
    ctx: HookContext,
    tool_name: str,
    resume_value: Any,
    user_query_or_payload: Any,
) -> None:
    """按工具类型从用户选择的 paradigm 重建 tool_params。

    user_query_or_payload 兼容两种形式：
    - str：直接作为 user_query 使用（新接口）
    - dict：取 payload["query"] 或 payload.get("query") 或 ctx["user_query"]（旧接口，保持向后兼容）
    """
    selected: list[dict[str, Any]] = []
    if isinstance(resume_value, dict):
        selected = resume_value.get("paradigmList", [])

    # 兼容旧 payload dict 和新 user_query str
    if isinstance(user_query_or_payload, dict):
        payload = user_query_or_payload
        user_query = payload.get("query") or ctx.get("user_query", "")
    else:
        user_query = str(user_query_or_payload or "") or ctx.get("user_query", "")

    if _is_data_query_tool(tool_name):
        ctx["tool_params"] = {
            "query": user_query,
            "contextKnowledge": _extract_knowledge_from_paradigm(selected),
        }
    elif tool_name.startswith("query_"):
        ctx["tool_params"] = _build_oql_params_from_paradigm(selected)
    elif tool_name.startswith("compute_"):
        ctx["tool_params"] = _build_compute_params_from_paradigm(selected)


def _extract_knowledge_from_paradigm(selected: list[dict[str, Any]]) -> str:
    lines = []
    for item in selected:
        name = item.get("name") or item.get("termName") or ""
        field = item.get("fieldName") or item.get("description") or ""
        if name and field:
            lines.append(f"{name} → {field}")
    return "\n".join(lines)


def _build_oql_params_from_paradigm(selected: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "select": [i.get("fieldName", "") for i in selected if i.get("fieldName")],
        "where": [],
        "group_by": [],
        "order_by": [],
    }


def _build_compute_params_from_paradigm(selected: list[dict[str, Any]]) -> dict[str, Any]:
    dims = [{"field": i["dimensionName"]} for i in selected if i.get("dimensionName")]
    metrics = [
        {"field": i["metricName"], "agg": i.get("agg", "sum")}
        for i in selected
        if i.get("metricName")
    ]
    return {"dimensions": dims, "metrics": metrics}
