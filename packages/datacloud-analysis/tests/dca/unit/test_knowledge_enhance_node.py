from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.messages import HumanMessage

from datacloud_analysis.orchestration.knowledge_enhance import node as ke_module
from datacloud_analysis.orchestration.knowledge_enhance import knowledge_enhance_node
from datacloud_analysis.orchestration.state import AgentState


@pytest.fixture(autouse=True)
def _mock_knowledge_service(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeKnowledgeService:
        def query(self, text: str, *, n_hops: int, include_knowledge: bool) -> dict[str, Any]:
            assert n_hops == 0
            assert include_knowledge is True
            term_id = "T100" if "enterprise" in text else "TERM_FAKE"
            return {
                "results": [
                    {
                        "center_entity": {"node_id": term_id},
                        "tree": {
                            "id": term_id,
                            "name": text,
                            "node_type": "VIEW",
                            "properties": {"knowledge": [f"{text} definition"]},
                            "children": [],
                        },
                    }
                ]
            }

    monkeypatch.setattr(ke_module, "get_singleton_service", lambda **_kwargs: _FakeKnowledgeService())


@pytest.mark.asyncio
async def test_knowledge_enhance_rewrites_enriched_query_with_confirmed_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_candidates(terms: list[str], *args: Any, **kwargs: Any) -> dict[str, Any]:
        assert terms
        return {
            terms[0]: [
                {
                    "term_id": "T100",
                    "term_name": "enterprise comprehensive report",
                    "term_type_code": "VIEW",
                    "match_type": "standard_name",
                    "confidence": 0.95,
                    "score": 0.95,
                    "name_id": "",
                    "mention": terms[0],
                }
            ]
        }

    async def _fake_disambiguate(
        candidates_map: dict[str, list[dict[str, Any]]],
        original_question: str,
        *,
        llm: Any,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        _ = candidates_map, original_question, llm
        return (
            [
                {
                    "mention": "enterprise report",
                    "term_id": "T100",
                    "term_name": "enterprise comprehensive report",
                    "term_type_code": "VIEW",
                    "confidence": 0.95,
                }
            ],
            [],
        )

    monkeypatch.setattr(ke_module, "search_all_candidates", _fake_candidates)
    monkeypatch.setattr(ke_module, "disambiguate_candidates", _fake_disambiguate)
    monkeypatch.setattr(ke_module, "search_knowledge", SimpleNamespace(ainvoke=lambda *_a, **_k: {}))
    monkeypatch.setattr(ke_module, "_init_reasoning_llm", lambda: None)

    state = cast(
        AgentState,
        {"messages": [HumanMessage(content="查询【enterprise report】的盈利情况")]},
    )
    out = await knowledge_enhance_node(state)

    assert out["user_query"] == "查询【enterprise report】的盈利情况"
    assert "enterprise report(enterprise comprehensive report)" in out["enriched_query"]
    assert out["enriched_query_source"] == "knowledge_rewrite"
    assert out["enriched_query_confidence"] == pytest.approx(0.95)
    assert out["knowledge_payload"]["terms"][0]["definition"] == "enterprise comprehensive report definition"


@pytest.mark.asyncio
async def test_knowledge_enhance_fallbacks_when_candidates_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_candidates(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    async def _fake_search(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "term_matches": [
                {"term_name": "yesterday sales", "term_id": "T2", "term_type_code": "METRIC", "match_score": 0.8}
            ]
        }

    monkeypatch.setattr(ke_module, "search_all_candidates", _raise_candidates)
    monkeypatch.setattr(ke_module, "search_knowledge", SimpleNamespace(ainvoke=_fake_search))
    monkeypatch.setattr(ke_module, "_init_reasoning_llm", lambda: None)

    state = cast(AgentState, {"messages": [HumanMessage(content="请查询【昨日销售】数据")]})
    out = await knowledge_enhance_node(state)

    assert out["user_query"] == "请查询【昨日销售】数据"
    assert out["knowledge_mode"] == "fallback"
    assert out["term_hints"][0]["term"] == "yesterday sales"

