"""TC-06 ~ TC-07: execution_node 知识增强注入 system_prompt（层 A）测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage


def _make_state(knowledge_snippets: list | None = None) -> dict:
    return {
        "messages": [HumanMessage(content="查询营收")],
        "agent_id": "test-agent",
        "workspace_dir": None,
        "user_query": "查询营收",
        "knowledge_payload": None,
        "knowledge_snippets": knowledge_snippets,
        "confirmed_terms": None,
        "react_rounds": None,
        "react_checkpoint": None,
        "react_final": None,
        "execution_status": "execution",
    }


def _make_config() -> dict:
    return {"configurable": {}}


# ---------------------------------------------------------------------------
# TC-06: knowledge_snippets 非空 → system_prompt 含可读字段映射段落，不含原始 JSON
# ---------------------------------------------------------------------------
async def test_tc06_knowledge_snippets_injected_as_readable_text() -> None:
    snippets = ["营收 → 企业总营收（万元）", "利润 → 企业总利润（万元）"]
    state = _make_state(knowledge_snippets=snippets)

    captured_prompts: list[str] = []

    async def mock_react_loop(state, tools_list, system_prompt, max_rounds, gateway_context=None):
        captured_prompts.append(system_prompt)
        return {"react_rounds": 0, "react_final": {}, "messages": [], "results": []}

    with patch(
        "datacloud_analysis.orchestration.execution.node.run_react_loop",
        side_effect=mock_react_loop,
    ):
        from datacloud_analysis.orchestration.execution.node import execution_node
        await execution_node(state, _make_config())

    assert captured_prompts, "run_react_loop 应被调用"
    prompt = captured_prompts[0]
    assert "数据查询知识增强" in prompt, "system_prompt 应包含知识增强段落标题"
    assert "营收 → 企业总营收（万元）" in prompt, "system_prompt 应包含可读字段映射"
    assert "利润 → 企业总利润（万元）" in prompt
    assert "paradigmList" not in prompt, "system_prompt 不应包含原始 JSON 结构"


# ---------------------------------------------------------------------------
# TC-07: knowledge_snippets 为空 → system_prompt 与无增强时完全一致
# ---------------------------------------------------------------------------
async def test_tc07_empty_snippets_system_prompt_unchanged() -> None:
    state_with = _make_state(knowledge_snippets=["营收 → 企业总营收（万元）"])
    state_without = _make_state(knowledge_snippets=None)

    captured: list[str] = []

    async def mock_react_loop(state, tools_list, system_prompt, max_rounds, gateway_context=None):
        captured.append(system_prompt)
        return {"react_rounds": 0, "react_final": {}, "messages": [], "results": []}

    with patch(
        "datacloud_analysis.orchestration.execution.node.run_react_loop",
        side_effect=mock_react_loop,
    ):
        from datacloud_analysis.orchestration.execution.node import execution_node
        await execution_node(state_with, _make_config())
        await execution_node(state_without, _make_config())

    assert len(captured) == 2
    prompt_with, prompt_without = captured
    assert "数据查询知识增强" in prompt_with
    assert "数据查询知识增强" not in prompt_without, "无 snippets 时不应有增强段落"
    # base prompt 应完全相同（知识段落只是附加）
    assert prompt_without in prompt_with, "无增强的 prompt 应是有增强 prompt 的前缀"
