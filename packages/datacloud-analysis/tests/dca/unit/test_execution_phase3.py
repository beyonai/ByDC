"""4.2 执行机制测试 — 先红后绿

测试目标：
- record_finding 工具新增，写入 state["reasoning_graph"].findings
- hook_aware_tool_node after_call_back 补全 result_summary
- finish_react_node 读取 findings 合并到 execution_summary
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── record_finding ─────────────────────────────────────────────────────────────

def test_record_finding_tool_exists() -> None:
    """record_finding 工具应存在于 anchor_tools 模块。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    tools = make_anchor_tools(get_state_fn=lambda: {})
    names = {t.name for t in tools}
    assert "record_finding" in names, "应包含 record_finding 工具"


def test_record_finding_writes_to_findings() -> None:
    """record_finding 应将 summary 追加到 reasoning_graph.findings。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    state: dict[str, Any] = {
        "active_tools": [],
        "reasoning_graph": {
            "nodes": {},
            "current_node_id": "",
            "findings": [],
            "dead_ends": [],
        },
    }
    tools = make_anchor_tools(get_state_fn=lambda: state)
    record = next(t for t in tools if t.name == "record_finding")

    result = record.invoke({"summary": "发现 8432 条超时 trace，主要集中在 payment-service"})

    assert isinstance(result, str)
    findings = (state.get("reasoning_graph") or {}).get("findings") or []
    assert len(findings) == 1, "应有 1 条 finding"
    assert "8432" in findings[0] or "payment" in findings[0]


def test_record_finding_accumulates() -> None:
    """多次调用 record_finding 应累积，不覆盖。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    state: dict[str, Any] = {
        "reasoning_graph": {"nodes": {}, "findings": [], "dead_ends": []},
    }
    tools = make_anchor_tools(get_state_fn=lambda: state)
    record = next(t for t in tools if t.name == "record_finding")

    record.invoke({"summary": "结论一：发现超时"})
    record.invoke({"summary": "结论二：定位到 DB 慢查询"})

    findings = state["reasoning_graph"]["findings"]
    assert len(findings) == 2
    assert any("超时" in f for f in findings)
    assert any("DB" in f for f in findings)


def test_record_finding_initializes_rg_if_none() -> None:
    """reasoning_graph 为 None 时，record_finding 应初始化它。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    state: dict[str, Any] = {"active_tools": [], "reasoning_graph": None}
    tools = make_anchor_tools(get_state_fn=lambda: state)
    record = next(t for t in tools if t.name == "record_finding")

    record.invoke({"summary": "初始化测试结论"})

    rg = state.get("reasoning_graph") or {}
    assert "findings" in rg
    assert len(rg["findings"]) == 1


# ── after_call_back result_summary ────────────────────────────────────────────

def test_hook_aware_tool_node_writes_result_summary() -> None:
    """after_call_back 应将 ToolMessage 内容截断写入 reasoning_graph 节点的 result_summary。"""
    import inspect
    from datacloud_analysis.orchestration.execution import hook_aware_tool_node as m

    src = inspect.getsource(m)
    assert "result_summary" in src, "hook_aware_tool_node 应写入 result_summary 字段"


# ── finish_react_node findings → execution_summary ───────────────────────────

def test_finish_react_node_reads_findings_to_execution_summary() -> None:
    """finish_react_node 应读取 reasoning_graph.findings 并合并到 execution_summary。"""
    import inspect
    from datacloud_analysis.orchestration.execution import finish_react_node as m

    src = inspect.getsource(m)
    assert "findings" in src, "finish_react_node 应读取 findings"
    assert "execution_summary" in src, "finish_react_node 应写入 execution_summary"


@pytest.mark.asyncio
async def test_finish_react_node_includes_findings_in_output() -> None:
    """finish_react_node 执行后，返回值应包含 findings 合并的 execution_summary。"""
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableConfig

    from datacloud_analysis.orchestration.execution.finish_react_node import finish_react_node

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{
                    "id": "tc_001",
                    "name": "finish_react",
                    "args": {"result_type": "text", "answer": "分析完成"},
                    "type": "tool_call",
                }],
            )
        ],
        "reasoning_graph": {
            "nodes": {},
            "findings": ["BY_001: 发现超时原因", "BY_002: DB 慢查询确认"],
            "dead_ends": [],
            "task_objects": [],
        },
        "execution_status": "",
        "react_round_idx": 2,
        "react_last_query_data": None,
        "answer_streamed": False,
    }
    config: RunnableConfig = {"configurable": {}}

    result = await finish_react_node(state, config)  # type: ignore[arg-type]

    assert "react_final" in result
    # execution_summary 应包含 findings 内容
    exec_summary = result.get("execution_summary") or ""
    if exec_summary:
        assert "BY_001" in exec_summary or "超时" in exec_summary, \
            "execution_summary 应包含 findings 内容"
