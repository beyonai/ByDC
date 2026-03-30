from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from datacloud_analysis.orchestration.clarification import clarification_node
from datacloud_analysis.orchestration.graph_builder import build_analysis_graph
from datacloud_analysis.orchestration.intent import _merge_concept_terms, intent_node


def test_build_graph_uses_five_node_pipeline_without_intent_replan() -> None:
    graph = build_analysis_graph()
    assert "intent_replan" not in graph.nodes
    assert "planning" in graph.nodes
    assert "execution" in graph.nodes


def test_merge_concept_terms_prefers_longer_phrase_over_km_subterm() -> None:
    merged = _merge_concept_terms(
        llm_terms=["企业综合分析表"],
        km_terms=["企业"],
    )
    assert merged == ["企业综合分析表"]


def test_merge_concept_terms_deduplicates_and_keeps_longest_overlap() -> None:
    merged = _merge_concept_terms(
        llm_terms=["企业"],
        km_terms=["企业综合分析表", "企业", "综合分析表"],
    )
    assert merged == ["企业综合分析表"]


@pytest.mark.asyncio
async def test_clarification_empty_reply_keeps_current_term_until_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = ["", "profit > 20%", "", ""]

    def fake_interrupt(_prompt: str) -> str:
        if replies:
            return replies.pop(0)
        return ""

    monkeypatch.setattr("langgraph.types.interrupt", fake_interrupt)

    state: dict[str, Any] = {
        "ambiguous_terms": [
            {"mention": "high_eff_enterprise", "candidates": []},
            {"mention": "key_metric", "candidates": []},
        ],
        "confirmed_terms": [],
        "session_alias_map": {},
        "query_mode": "analysis",
        "target_tool": "",
    }

    out = await clarification_node(state, gateway_context=None)
    confirmed = out.get("confirmed_terms", [])
    assert any(item.get("mention") == "high_eff_enterprise" for item in confirmed)


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


@pytest.mark.asyncio
async def test_intent_numeric_or_symbol_only_input_forces_chitchat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NeverKnowledge:
        async def ainvoke(self, _payload: dict[str, Any]) -> str:
            raise AssertionError("search_knowledge should not be called")

    def _never_init_chat_model(**_kwargs: Any) -> Any:
        raise AssertionError("init_chat_model should not be called")

    monkeypatch.setattr("datacloud_analysis.orchestration.intent.search_knowledge", _NeverKnowledge())
    monkeypatch.setattr(
        "datacloud_analysis.orchestration.intent.init_chat_model",
        _never_init_chat_model,
    )

    state: dict[str, Any] = {"messages": [HumanMessage(content="1111!!!")]}
    out = await intent_node(state, gateway_context=None)

    assert out["query_mode"] == "chitchat"
    assert out["chitchat_reply"] == out["intent"]
    assert out["target_tool"] == ""
    assert out["tool_params"] == {}
    assert out["concept_terms"] == []
    assert out["ambiguous_terms"] == []
    assert "请告诉我你想查询的对象、指标和时间范围" in out["intent"]


@pytest.mark.asyncio
async def test_intent_node_uses_query_override_for_replan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_query: dict[str, str] = {}

    class _FakeKnowledgeTool:
        async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured_query["value"] = str(payload.get("query", ""))
            return {"query": payload.get("query", ""), "term_matches": []}

    class _FakeLLM:
        async def ainvoke(self, _messages: list[Any]) -> AIMessage:
            return AIMessage(
                content=(
                    '{"rewritten_intent":"重算后的意图","clarify_needed":false,'
                    '"query_mode":"analysis","target_tool":"","tool_params":{},'
                    '"concept_terms":[]}'
                )
            )

    monkeypatch.setattr("datacloud_analysis.orchestration.intent.search_knowledge", _FakeKnowledgeTool())
    monkeypatch.setattr("datacloud_analysis.orchestration.intent.init_chat_model", lambda **_: _FakeLLM())

    state: dict[str, Any] = {"messages": [HumanMessage(content="原始问题")]}
    out = await intent_node(state, gateway_context=None, query_override="澄清后问题")

    assert captured_query["value"] == "澄清后问题"
    assert out["intent"] == "重算后的意图"
