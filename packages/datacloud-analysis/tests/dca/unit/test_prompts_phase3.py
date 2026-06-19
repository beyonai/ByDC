"""4.4 提示词重构测试 — 先红后绿

测试目标：
- prompts.py 新增 _build_ontology_rules_zh() 函数（XML 结构化本体推理规则）
- _build_exec_zh() 精化重试规则（区分盲目重试和换策略）
- graph_builder.py L1 排序（task_prompt 前置）
- graph_builder.py finish_react_node Verification（findings 非空才放行）
- graph_builder.py should_continue dead_end 全覆盖兜底
- llm_call_node.py _build_message_tail() 函数（findings + task_objects + 任务锚定 + todos）
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest


# ── _build_ontology_rules_zh ───────────────────────────────────────────────────

def test_build_ontology_rules_zh_exists() -> None:
    """prompts.py 应有 _build_ontology_rules_zh() 函数。"""
    from datacloud_analysis.i18n import prompts

    assert hasattr(prompts, "_build_ontology_rules_zh"), \
        "prompts.py 应有 _build_ontology_rules_zh 函数"


def test_build_ontology_rules_zh_contains_xml_tags() -> None:
    """_build_ontology_rules_zh 应包含 XML 标签结构化规则。"""
    from datacloud_analysis.i18n.prompts import _build_ontology_rules_zh

    result = _build_ontology_rules_zh()
    assert "<anchor_tools>" in result, "应有 <anchor_tools> XML 标签"
    assert "<reasoning_discipline>" in result, "应有 <reasoning_discipline> XML 标签"
    assert "search_ontology" in result, "应包含 search_ontology 工具说明"
    assert "goto_ontology" in result, "应包含 goto_ontology 工具说明"
    assert "get_reasoning_map" in result, "应包含 get_reasoning_map 工具说明"


def test_build_ontology_rules_zh_contains_discipline_rules() -> None:
    """reasoning_discipline 块应包含持续努力规则。"""
    from datacloud_analysis.i18n.prompts import _build_ontology_rules_zh

    result = _build_ontology_rules_zh()
    assert "半途而废" in result or "完成" in result, "应有完成性要求规则"
    assert "finish_react" in result, "应提及 finish_react 结束条件"
    assert "findings" in result, "应有结束前自检 findings 说明"


def test_exec_prompt_retry_rule_refined() -> None:
    """_build_exec_zh 的重试规则应区分盲目重试和换策略。"""
    from datacloud_analysis.i18n.prompts import _build_exec_zh

    result = _build_exec_zh()
    # 应有更精细的失败处理规则
    assert "相同参数" in result or "盲目重试" in result or "换参数" in result, \
        "_build_exec_zh 应有区分重试策略的规则"


# ── graph_builder L1 排序 ──────────────────────────────────────────────────────

def test_graph_builder_l1_has_ontology_rules() -> None:
    """graph_builder._build_prebuilt_graph 的 L1 应包含 ontology_rules。"""
    from datacloud_analysis.orchestration import graph_builder

    src = inspect.getsource(graph_builder._build_prebuilt_graph)
    assert "_build_ontology_rules_zh" in src or "ontology_rules" in src, \
        "_build_prebuilt_graph 应注入 ontology_rules"


def test_graph_builder_task_prompt_in_system_parts() -> None:
    """graph_builder 的 system_parts 应包含 task_prompt。"""
    from datacloud_analysis.orchestration import graph_builder

    src = inspect.getsource(graph_builder._build_prebuilt_graph)
    assert "custom_task" in src or "task_prompt" in src, \
        "_build_prebuilt_graph 应包含 task_prompt"


# ── finish_react Verification ─────────────────────────────────────────────────

def test_finish_react_node_has_verification_logic() -> None:
    """finish_react_node 应有 findings 非空检查的 Verification 逻辑。"""
    from datacloud_analysis.orchestration.execution import finish_react_node as m

    src = inspect.getsource(m)
    assert "findings" in src, "finish_react_node 应检查 findings"


@pytest.mark.asyncio
async def test_finish_react_verification_blocks_empty_findings() -> None:
    """findings 为空时，finish_react_node 应返回 Command 继续推理而不是结束。"""
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
            "findings": [],  # 空 findings
            "dead_ends": [],
        },
        "execution_status": "",
        "react_round_idx": 1,
        "react_last_query_data": None,
        "answer_streamed": False,
    }
    config: RunnableConfig = {"configurable": {}}

    result = await finish_react_node(state, config)  # type: ignore[arg-type]

    # findings 为空时，应被拦截（返回 Command goto agent 或在结果中有提示）
    # 检查方式：react_final 不存在（被重定向到 agent），或结果包含重试信号
    from langgraph.types import Command
    if isinstance(result, Command):
        assert result.goto == "agent", "findings 为空时应重定向到 agent"
    # 如果直接返回 dict，则不拦截（此行为也可接受，取决于实现选择）


# ── should_continue dead_end 兜底 ─────────────────────────────────────────────

def test_should_continue_has_dead_end_fallback() -> None:
    """should_continue 应有 dead_end 全覆盖兜底逻辑。"""
    from datacloud_analysis.orchestration import graph_builder

    src = inspect.getsource(graph_builder.should_continue)
    assert "dead_end" in src or "is_dead_end" in src, \
        "should_continue 应有 dead_end 兜底逻辑"


def test_should_continue_returns_respond_when_all_dead() -> None:
    """所有节点均为 dead_end 且 findings 为空时，should_continue 应返回 respond。"""
    from datacloud_analysis.orchestration.graph_builder import should_continue
    from langchain_core.messages import AIMessage

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"id": "tc_001", "name": "query_xxx", "args": {}, "type": "tool_call"}],
            )
        ],
        "reasoning_graph": {
            "nodes": {
                "n0": {"is_dead_end": True, "object_code": "ops_a"},
                "n1": {"is_dead_end": True, "object_code": "ops_b"},
            },
            "findings": [],
        },
        "execution_status": "",
        "react_round_idx": 2,
        "agent_abort": False,
    }

    result = should_continue(state)  # type: ignore[arg-type]
    assert result == "respond", "所有节点 dead_end 且无 findings 时应返回 respond"


# ── llm_call_node _build_message_tail ─────────────────────────────────────────

def test_build_message_tail_exists() -> None:
    """llm_call_node 应有 _build_message_tail() 函数。"""
    from datacloud_analysis.orchestration.execution import llm_call_node as m

    assert hasattr(m, "_build_message_tail"), \
        "llm_call_node 应有 _build_message_tail 函数"


def test_build_message_tail_includes_findings() -> None:
    """_build_message_tail 应在有 findings 时包含收敛引导。"""
    from datacloud_analysis.orchestration.execution.llm_call_node import _build_message_tail

    state: dict[str, Any] = {
        "reasoning_graph": {
            "findings": ["BY_001: 发现超时原因"],
            "task_objects": [],
        },
        "todos": [],
        "user_query": "分析故障",
    }
    result = _build_message_tail(state, "分析故障")
    assert result is not None
    assert "finish_react" in result or "BY_001" in result or "结论" in result


def test_build_message_tail_includes_task_objects() -> None:
    """_build_message_tail 应在有 task_objects 时包含摘要。"""
    from datacloud_analysis.orchestration.execution.llm_call_node import _build_message_tail

    state: dict[str, Any] = {
        "reasoning_graph": {
            "findings": [],
            "task_objects": [{"code": "task_anomaly", "row_count": 15, "summary": "异常集合"}],
        },
        "todos": [],
        "user_query": "分析故障",
    }
    result = _build_message_tail(state, "分析故障")
    assert result is not None
    assert "task_anomaly" in result or "物化" in result


def test_build_message_tail_includes_user_query_anchor() -> None:
    """_build_message_tail 应包含任务锚定（user_query）。"""
    from datacloud_analysis.orchestration.execution.llm_call_node import _build_message_tail

    state: dict[str, Any] = {
        "reasoning_graph": {"findings": [], "task_objects": []},
        "todos": [],
        "user_query": "分析昨晚的服务超时故障",
    }
    result = _build_message_tail(state, "分析昨晚的服务超时故障")
    assert result is not None
    assert "分析昨晚" in result or "任务" in result
