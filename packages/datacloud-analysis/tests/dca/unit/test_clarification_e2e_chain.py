"""Cross-node clarification chain contract test."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datacloud_analysis.orchestration.clarification.analyze_clarify_node import (
    analyze_clarify_node,
)
from datacloud_analysis.orchestration.clarification.user_clarify_node import (
    user_clarify_node,
)
from datacloud_analysis.orchestration.execution.react_loop import _serialize_messages
from datacloud_analysis.orchestration.execution.tool_dispatcher_node import (
    make_tool_dispatcher_node,
)
from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
    ClarificationNeededError,
    before_call_back,
)
from langchain_core.messages import AIMessage


class _FakeField:
    def __init__(self, code: str, name: str) -> None:
        self.field_code = code
        self.field_name = name
        self.aliases: list[str] = []


class _FakeOntology:
    def __init__(self) -> None:
        self.fields = [_FakeField("total_revenue", "企业总营收（万元）")]


class _FakeLoader:
    def get_ontology_class(self, scope_code: str) -> _FakeOntology:
        assert scope_code == "ads_enterprise"
        return _FakeOntology()


@pytest.mark.asyncio
async def test_clarification_chain_resume_refill_then_second_dispatch_success() -> None:
    """ambiguous -> ClarificationNeededError -> resume refill -> second dispatch success."""
    tool_call = {
        "name": "query_ads_enterprise",
        "args": {
            "query": "查询高营收企业",
            "filters": [{"field": "营收", "op": "gt", "value": 100}],
        },
        "id": "tc_chain_001",
    }
    ai_msg = AIMessage(content="", tool_calls=[tool_call])
    base_state: dict[str, Any] = {
        "react_messages_log": _serialize_messages([ai_msg]),
        "react_round_idx": 2,
    }

    node = make_tool_dispatcher_node(tools_list=[])
    exc_context = {
        "tool_name": "query_ads_enterprise",
        "query": "查询高营收企业",
        "scope_code": "ads_enterprise",
        "structured_input": {"filters": [{"field": "营收", "op": "gt", "value": 100}]},
        "is_compute": False,
        "resolved": {},
        "is_complex": False,
        "paradigm_list": [
            {
                "paradigmId": "p1",
                "paradigmName": "营收",
                "paradigmResult": [{"keyword": "营收", "choiceKeyword": "企业总营收（万元）"}],
            }
        ],
        "clarify_knowledge": "字段映射知识",
    }

    async def _raise_clarification(*args: Any, **kwargs: Any) -> None:
        raise ClarificationNeededError(exc_context)

    with patch(
        "datacloud_analysis.orchestration.execution.tool_dispatcher_node.dispatch_tool",
        _raise_clarification,
    ):
        step1 = await node(base_state, MagicMock())

    assert step1.get("execution_status") == "clarify_needed"

    state_after_need = {**base_state, **step1}
    step2 = await analyze_clarify_node(state_after_need, MagicMock())
    analyze_result = step2.get("clarification_analyze_result") or {}
    assert analyze_result.get("paradigm_list"), "analyze_clarify_node 应保留澄清候选"

    resume_payload = {
        "paradigmList": [
            {
                "paradigmList": [
                    {
                        "paradigmId": "p1",
                        "paradigmName": "营收",
                        "paradigmResult": [{"keyword": "营收", "choiceKeyword": "企业总营收（万元）"}],
                    }
                ]
            }
        ]
    }
    with (
        patch(
            "datacloud_analysis.orchestration.clarification.user_clarify_node.interrupt",
            return_value=resume_payload,
        ),
        patch(
            "datacloud_analysis.orchestration.clarification.user_clarify_node._format_clarification",
            return_value={"filters": [{"field": "企业总营收（万元）", "op": "gt", "value": 100}]},
        ),
    ):
        step3 = await user_clarify_node({**state_after_need, **step2}, MagicMock())

    assert (step3.get("clarification_formatted_params") or {}).get("params"), (
        "user_clarify_node 应写回 clarification_formatted_params"
    )

    plugin_state = {**state_after_need, **step2, **step3}
    hook_ctx: dict[str, Any] = {
        "tool_name": "query_ads_enterprise",
        "tool_params": {
            "query": "查询高营收企业",
            "filters": [{"field": "营收", "op": "gt", "value": 100}],
        },
        "metadata": {"state": plugin_state, "loader": _FakeLoader()},
    }
    decision = await before_call_back(hook_ctx)
    assert decision is not None and decision.get("action") == "patch"
    assert (hook_ctx["tool_params"]["filters"][0]).get("field") == "total_revenue"

    dispatch_success = AsyncMock(return_value=("tc_chain_001", {"records": [], "meta": {}}))
    with patch(
        "datacloud_analysis.orchestration.execution.tool_dispatcher_node.dispatch_tool",
        dispatch_success,
    ):
        step4 = await node({**base_state, **step3}, MagicMock())

    assert dispatch_success.call_count == 1
    assert step4.get("execution_status") is None
    assert step4.get("clarification_formatted_params") is None
