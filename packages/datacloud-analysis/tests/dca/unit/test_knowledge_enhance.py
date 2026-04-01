from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.messages import HumanMessage

from datacloud_analysis.orchestration.knowledge_enhance import node as knowledge_enhance_module
from datacloud_analysis.orchestration.knowledge_enhance.node import knowledge_enhance_node
from datacloud_analysis.orchestration.state import AgentState


@pytest.fixture(autouse=True)
def _mock_knowledge_service(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeKnowledgeService:
        def query(self, text: str, *, n_hops: int, include_knowledge: bool) -> dict[str, Any]:
            assert n_hops == 0
            assert include_knowledge is True
            term_id = "T-confirmed" if "浼佷笟缁煎悎鍒嗘瀽琛?" in text else "TERM_FAKE"
            return {
                "results": [
                    {
                        "center_entity": {"node_id": term_id},
                        "tree": {
                            "id": term_id,
                            "name": text,
                            "node_type": "VIEW",
                            "properties": {"knowledge": [f"{text} 定义"]},
                            "children": [],
                        },
                    }
                ]
            }

    monkeypatch.setattr(
        knowledge_enhance_module,
        "get_singleton_service",
        lambda **_kwargs: _FakeKnowledgeService(),
    )


@pytest.mark.asyncio
async def test_knowledge_enhance_fallbacks_when_candidate_search_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_candidates(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    async def _fake_search(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "term_matches": [
                {"term_name": "企业综合分析表", "term_id": "T1", "term_type_code": "VIEW", "match_score": 0.95}
            ]
        }

    monkeypatch.setattr(knowledge_enhance_module, "search_all_candidates", _raise_candidates)
    monkeypatch.setattr(knowledge_enhance_module, "search_knowledge", SimpleNamespace(ainvoke=_fake_search))
    monkeypatch.setattr(knowledge_enhance_module, "_init_reasoning_llm", lambda: None)

    state = cast(AgentState, {"messages": [HumanMessage(content="请查询【企业综合分析表】 100条数据。")]})
    out = await knowledge_enhance_node(state)

    assert out["knowledge_mode"] == "fallback"
    assert out["term_hints"][0]["term"] == "企业综合分析表"


@pytest.mark.asyncio
async def test_knowledge_enhance_builds_confirmed_terms_when_candidates_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_candidates(terms: list[str], *args: Any, **kwargs: Any) -> dict[str, Any]:
        assert terms
        return {
            terms[0]: [
                {
                    "term_id": "T-confirmed",
                    "term_name": "企业综合分析表",
                    "term_type_code": "VIEW",
                    "match_type": "standard_name",
                    "confidence": 0.99,
                    "score": 0.99,
                    "name_id": "N1",
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
                    "mention": "企业综合分析表",
                    "term_id": "T-confirmed",
                    "term_name": "企业综合分析表",
                    "term_type_code": "VIEW",
                    "confidence": 0.98,
                }
            ],
            [],
        )

    monkeypatch.setattr(knowledge_enhance_module, "search_all_candidates", _fake_candidates)
    monkeypatch.setattr(knowledge_enhance_module, "disambiguate_candidates", _fake_disambiguate)
    monkeypatch.setattr(knowledge_enhance_module, "search_knowledge", SimpleNamespace(ainvoke=lambda *_a, **_k: {}))
    monkeypatch.setattr(knowledge_enhance_module, "_init_reasoning_llm", lambda: None)

    state = cast(AgentState, {"messages": [HumanMessage(content="请查询【企业综合分析表】 100条数据。")]})
    out = await knowledge_enhance_node(state)

    assert out["knowledge_mode"] == "fresh"
    assert out["concept_terms"] == ["企业综合分析表"]
    assert out["confirmed_terms"][0]["term_id"] == "T-confirmed"
    assert out["term_hints"][0]["source"] == "confirmed"
    assert out["knowledge_payload"]["terms"][0]["definition"] is not None
