"""Built-in tool hook: 知识增强与查询澄清（层 B 注入）。"""

from __future__ import annotations

import json
import logging
from typing import Any

from datacloud_analysis.tool_hook_plugins.types import HookContext, HookDecision

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


async def _call_fallback_enhancer(user_query: str) -> Any:
    """兜底：当 knowledge_payload 缓存为空时重新调用知识增强 API。"""
    from datacloud_knowledge.intent import analyze_query_clarification  # type: ignore[import]
    return await analyze_query_clarification(user_query)


async def before_call_back(ctx: HookContext) -> HookDecision | None:
    """层 B 知识增强：在工具调用前注入 contextKnowledge 或触发追问中断。"""
    tool_name = ctx.get("tool_name", "")

    # 非数据工具不处理
    if not _is_data_tool(tool_name):
        return None

    # 从缓存获取 knowledge_payload（由 intend_node 写入 state，tool_wrapper 注入 ctx）
    payload: dict[str, Any] = ctx.get("knowledge_payload") or {}

    if not payload:
        # 兜底：缓存不存在时重新调用（正常流程不走此分支）
        try:
            result = await _call_fallback_enhancer(ctx.get("user_query", ""))
            payload = {
                "needs_clarification": result.needs_clarification,
                "form": result.form,
                "knowledge": result.knowledge,
                "query": getattr(result, "query", ctx.get("user_query", "")),
            }
        except Exception:
            logger.warning("[query_clarification_plugin] fallback enhancer failed, skipping")
            return None

    needs_clarification: bool = payload.get("needs_clarification", False)
    knowledge_str: str = payload.get("knowledge", "")

    if needs_clarification:
        # 追问中断（§6.7 层 B 追问逻辑）
        from langgraph.types import interrupt  # type: ignore[import]
        form_str = payload.get("form", "")
        try:
            paradigm_list = json.loads(form_str).get("paradigmList", [])
        except Exception:
            paradigm_list = []
        resume_value = interrupt({"paradigmList": paradigm_list})
        _apply_resume_to_params(ctx, tool_name, resume_value, payload)
        return {"action": "patch", "patch": {"tool_params": dict(ctx["tool_params"])}}

    # 层 B 知识注入：仅对 data_query_* 工具注入 contextKnowledge
    if knowledge_str and _is_data_query_tool(tool_name):
        return {"action": "patch", "patch": {"tool_params": {"contextKnowledge": knowledge_str}}}

    return None


def _apply_resume_to_params(
    ctx: HookContext,
    tool_name: str,
    resume_value: Any,
    payload: dict[str, Any],
) -> None:
    """按工具类型从用户选择的 paradigm 重建 tool_params。"""
    selected: list[dict[str, Any]] = []
    if isinstance(resume_value, dict):
        selected = resume_value.get("paradigmList", [])

    if _is_data_query_tool(tool_name):
        ctx["tool_params"] = {
            "query": payload.get("query") or ctx.get("user_query", ""),
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
