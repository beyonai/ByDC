"""Knowledge tool unit tests."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("datacloud_analysis.tools.knowledge")

from datacloud_analysis.tools.knowledge import search_knowledge, update_term_scores


@pytest.mark.asyncio
async def test_search_knowledge_returns_structured_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeQueryService:
        def query(
            self,
            _query: str,
            *,
            n_hops: int,
            include_knowledge: bool,
        ) -> dict[str, Any]:
            assert n_hops == 3
            assert include_knowledge is True
            return {
                "query": "企业经营情况",
                "entities_found": [
                    {
                        "name": "企业",
                        "node_id": "TERM_001",
                        "node_type": "ONTOLOGY_OBJ",
                        "match_type": "standard_name",
                        "match_score": 0.99,
                    }
                ],
                "fuzzy_suggestions": [
                    {
                        "original": "经营",
                        "matches": [
                            {
                                "term": "经营效益",
                                "term_id": "TERM_002",
                                "term_type": "ONTOLOGY_PROP",
                                "similarity": 0.88,
                                "edit_distance": 1,
                            }
                        ],
                    }
                ],
                "results": [
                    {
                        "center_entity": {
                            "name": "企业",
                            "node_id": "TERM_001",
                            "node_type": "ONTOLOGY_OBJ",
                            "match_type": "standard_name",
                        },
                        "hops": 2,
                        "node_count": 2,
                        "edge_count": 1,
                        "tree": {
                            "id": "TERM_001",
                            "name": "企业",
                            "node_type": "ONTOLOGY_OBJ",
                            "relation": None,
                            "properties": {},
                            "children": [
                                {
                                    "id": "TERM_003",
                                    "name": "营收",
                                    "node_type": "ONTOLOGY_PROP",
                                    "relation": "企业_拥有_营收",
                                    "properties": {"knowledge": ["指标描述"]},
                                    "children": [],
                                }
                            ],
                        },
                    }
                ],
            }

    monkeypatch.setattr(
        "datacloud_knowledge.query.get_singleton_service",
        lambda **_kwargs: _FakeQueryService(),
    )
    result = await search_knowledge.ainvoke({"query": "企业经营情况", "n_hops": 3})

    assert result["query"] == "企业经营情况"
    assert result["term_matches"][0]["term_id"] == "TERM_001"
    assert result["fuzzy_term_matches"][0]["candidates"][0]["term_id"] == "TERM_002"
    assert result["term_subgraphs"][0]["center_term"]["term_id"] == "TERM_001"


@pytest.mark.asyncio
async def test_search_knowledge_returns_error_payload_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("service unavailable")

    monkeypatch.setattr("datacloud_knowledge.query.get_singleton_service", _raise)
    result = await search_knowledge.ainvoke({"query": "企业"})

    assert result["query"] == "企业"
    assert result["term_matches"] == []
    assert "service unavailable" in result["error"]


@pytest.mark.asyncio
async def test_update_term_scores_dispatches_async_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeContext:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def call_agent(self, **kwargs: Any) -> dict[str, Any]:
            self.calls.append(kwargs)
            return {"status": "queued"}

    context = _FakeContext()
    monkeypatch.setenv("DATACLOUD_GATEWAY_WORKER_ID", "datacloud")

    await update_term_scores(
        [
            {"name_id": "name-1", "success": True},
            {"name_id": "name-2", "success": False},
            {"name_id": "", "success": True},
        ],
        gateway_context=context,
    )

    assert len(context.calls) == 1
    call = context.calls[0]
    assert call["target_agent_type"] == "datacloud"
    assert call["wait_for_reply"] is False
    assert call["payload"]["ext_params"]["command"] == "updateTermsName"
    assert call["payload"]["ext_params"]["silent"] is True
    assert call["payload"]["ext_params"]["score_records"] == [
        {"name_id": "name-1", "success": True},
        {"name_id": "name-2", "success": False},
    ]

