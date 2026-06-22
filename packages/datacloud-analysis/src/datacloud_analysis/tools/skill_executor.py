"""sub_agent 分身工具实现。

sub_agent 是主 Agent 的分身，以 StructuredTool 形式挂载。
分身有独立上下文，执行完毕只返回 findings，不污染主 Agent context。
分身不能再启动分身（is_sub_agent=True 排除自身，防递归）。
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool("sub_agent")
async def sub_agent(
    task: Annotated[str, "任务描述，如'执行 diagnose-fault，诊断 trace_id=xxx 的故障'"],
    context_summary: Annotated[str, "上下文摘要：trace_id、症状、已有 findings 等关键信息"],
    initial_tools: Annotated[
        list[str],
        "主 Agent 传入的已知工具名列表，写入分身初始 active_tools，跳过 search_ontology 冷启动",
    ] = [],  # noqa: B006
) -> str:
    """启动当前 Agent 的分身执行指定任务，返回结论摘要。

    分身有独立上下文，只返回 findings，不污染主 Agent context。
    分身不能再启动分身（无递归）。
    步骤多 / 并发调查多个维度时使用。
    """
    try:
        from datacloud_data_sdk.context import get_current_context  # noqa: PLC0415

        ctx = get_current_context()
        extras: dict[str, Any] = getattr(ctx, "extras", None) or {}
    except Exception:  # noqa: BLE001
        extras = {}

    try:
        from datacloud_analysis.tools.tool_pool import _get_shared_loader  # noqa: PLC0415

        tools_dict: dict[str, Any] = extras.get("tools_dict") or {}
        loader = _get_shared_loader()
        llm_config: dict[str, Any] | None = extras.get("llm_config")

        from datacloud_analysis.orchestration.graph_builder import (  # noqa: PLC0415
            build_analysis_graph,
        )

        sub_graph = build_analysis_graph(
            tools=tools_dict,
            loader=loader,
            is_sub_agent=True,
        ).compile()

        _thread_id = uuid.uuid4().hex
        _gw_ctx = getattr(ctx, "gateway_context", None) if "ctx" in dir() else None

        run_config: dict[str, Any] = {
            "configurable": {
                "thread_id": _thread_id,
                "gateway_context": _gw_ctx,
                "llm_config": llm_config,
            },
            "recursion_limit": 50,
        }

        initial_state: dict[str, Any] = {
            "user_query": f"{task}\n\n{context_summary}",
            "active_tools": list(initial_tools),
        }

        result = await sub_graph.ainvoke(initial_state, config=run_config)
        findings = str(result.get("execution_summary") or result.get("react_final") or "")
        logger.info("[sub_agent] task=%r findings_len=%d", task[:80], len(findings))
        return findings or f"[sub_agent 完成，task={task[:80]}，无结论输出]"

    except Exception as exc:  # noqa: BLE001
        logger.warning("[sub_agent] failed task=%r: %s", task[:80], exc)
        return f"[sub_agent 执行失败：{exc}]"
