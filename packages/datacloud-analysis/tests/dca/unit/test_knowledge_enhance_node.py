from __future__ import annotations

from typing import Any, cast

import pytest
from langchain_core.messages import HumanMessage

from datacloud_analysis.orchestration.knowledge_enhance import knowledge_enhance_node
from datacloud_analysis.orchestration.knowledge_enhance import node as ke_module
from datacloud_analysis.orchestration.state import AgentState


@pytest.mark.asyncio
async def test_knowledge_enhance_rewrites_enriched_query_with_high_confidence_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeTool:
        async def ainvoke(self, _payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "term_matches": [
                    {
                        "term_name": "enterprise report",
                        "normalized_term": "enterprise comprehensive report",
                        "term_id": "T100",
                        "match_score": 0.95,
                        "definition": (
                            "enterprise comprehensive report contains profitability metrics, "
                            "operational indicators, ownership profile, and historical trend details "
                            "to support downstream planning decisions."
                        ),
                    }
                ]
            }

    monkeypatch.setattr(ke_module, "search_knowledge", _FakeTool())

    state = cast(
        AgentState,
        {"messages": [HumanMessage(content="query enterprise report profitability")]},
    )
    out = await knowledge_enhance_node(state)

    assert out["user_query"] == "query enterprise report profitability"
    assert "原始问题：" in out["enriched_query"]
    assert "补充知识：" in out["enriched_query"]
    assert "enterprise comprehensive report" in out["enriched_query"]
    assert out["enriched_query_source"] == "confirmed_terms"
    assert out["enriched_query_confidence"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_knowledge_enhance_fallbacks_when_knowledge_search_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeTool:
        async def ainvoke(self, _payload: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("boom")

    monkeypatch.setattr(ke_module, "search_knowledge", _FakeTool())

    state = cast(AgentState, {"messages": [HumanMessage(content="query yesterday sales")]})
    out = await knowledge_enhance_node(state)

    assert out["user_query"] == "query yesterday sales"
    assert out["enriched_query"] == "query yesterday sales"
    assert out["enriched_query_source"] == "fallback_user_query"
    assert out["enriched_query_confidence"] == pytest.approx(0.0)

