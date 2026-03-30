from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from datacloud_analysis.orchestration.clarification import clarification_node
from datacloud_analysis.orchestration.graph_builder import _make_route_after_clarification
from datacloud_analysis.orchestration.intent import intent_node


def test_route_after_clarification_with_remaining_ambiguity_goes_to_insight() -> None:
    route = _make_route_after_clarification(default_tools={})
    state: dict[str, Any] = {
        "query_mode": "analysis",
        "ambiguous_terms": [{"mention": "经营效益", "candidates": []}],
    }
    assert route(state) == "insight"


@pytest.mark.asyncio
async def test_clarification_empty_reply_keeps_current_term_until_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = ["", "利润率 > 20%", "", ""]

    def fake_interrupt(_prompt: str) -> str:
        if replies:
            return replies.pop(0)
        return ""

    monkeypatch.setattr("langgraph.types.interrupt", fake_interrupt)

    state: dict[str, Any] = {
        "ambiguous_terms": [
            {"mention": "高效能企业", "candidates": []},
            {"mention": "关键经营指标", "candidates": []},
        ],
        "confirmed_terms": [],
        "session_alias_map": {},
        "query_mode": "analysis",
        "target_tool": "",
    }

    out = await clarification_node(state, gateway_context=None)
    confirmed = out.get("confirmed_terms", [])
    assert any(item.get("mention") == "高效能企业" for item in confirmed)


@pytest.mark.asyncio
async def test_intent_clarify_needed_does_not_call_langgraph_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeKnowledgeTool:
        async def ainvoke(self, _payload: dict[str, Any]) -> str:
            return "mock-knowledge"

    class _FakeLLM:
        async def ainvoke(self, _messages: list[Any]) -> AIMessage:
            return AIMessage(
                content=(
                    '{"rewritten_intent":"请补充时间范围","clarify_needed":true,'
                    '"query_mode":"analysis","target_tool":"","tool_params":{},"concept_terms":[]}'
                )
            )

    def _should_not_be_called(_prompt: str) -> str:
        raise AssertionError("langgraph.types.interrupt should not be called in intent_node")

    monkeypatch.setattr("datacloud_analysis.orchestration.intent.search_knowledge", _FakeKnowledgeTool())
    monkeypatch.setattr("datacloud_analysis.orchestration.intent.init_chat_model", lambda **_: _FakeLLM())
    monkeypatch.setattr("langgraph.types.interrupt", _should_not_be_called)

    state: dict[str, Any] = {"messages": [HumanMessage(content="帮我分析销售趋势")]}
    out = await intent_node(state, gateway_context=None)
    assert out["clarify_needed"] is True
    assert out["intent"] == "请补充时间范围"


@pytest.mark.asyncio
async def test_intent_term_search_failure_marks_terms_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeKnowledgeTool:
        async def ainvoke(self, _payload: dict[str, Any]) -> str:
            return "mock-knowledge"

    class _FakeLLM:
        async def ainvoke(self, _messages: list[Any]) -> AIMessage:
            return AIMessage(
                content=(
                    '{"rewritten_intent":"查询企业","clarify_needed":false,'
                    '"query_mode":"analysis","target_tool":"","tool_params":{},'
                    '"concept_terms":["企业"]}'
                )
            )

    async def _raise_search_failure(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("datacloud_analysis.orchestration.intent.search_knowledge", _FakeKnowledgeTool())
    monkeypatch.setattr("datacloud_analysis.orchestration.intent.init_chat_model", lambda **_: _FakeLLM())
    monkeypatch.setattr("datacloud_analysis.tools.knowledge.search_all_candidates", _raise_search_failure)

    state: dict[str, Any] = {"messages": [HumanMessage(content="查询企业")]}
    out = await intent_node(state, gateway_context=None)

    assert out["confirmed_terms"] == []
    assert out["ambiguous_terms"][0]["mention"] == "企业"


@pytest.mark.asyncio
async def test_clarification_rewrites_intent_and_tool_params_with_confirmed_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("langgraph.types.interrupt", lambda _prompt: "1")

    state: dict[str, Any] = {
        "intent": "query corp profit",
        "tool_params": {"query": "corp profit"},
        "ambiguous_terms": [
            {
                "mention": "corp",
                "candidates": [
                    {
                        "term_id": "TERM_001",
                        "term_name": "enterprise",
                        "term_type_code": "ONTOLOGY_OBJ",
                    }
                ],
            }
        ],
        "confirmed_terms": [],
        "session_alias_map": {},
        "query_mode": "analysis",
        "target_tool": "",
    }

    out = await clarification_node(state, gateway_context=None)
    assert out.get("intent") == "query enterprise profit"
    assert out.get("tool_params", {}).get("query") == "enterprise profit"
