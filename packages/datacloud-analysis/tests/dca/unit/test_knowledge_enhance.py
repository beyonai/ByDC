from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.messages import HumanMessage

from datacloud_analysis.orchestration import knowledge_enhance as knowledge_enhance_module
from datacloud_analysis.orchestration.knowledge_enhance import knowledge_enhance_node
from datacloud_analysis.orchestration.state import AgentState


@pytest.mark.asyncio
async def test_knowledge_enhance_filters_low_confidence_term_hints_and_keeps_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_ainvoke(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "term_matches": [
                {"term_name": "高置信术语", "term_id": "T1", "match_score": 0.95},
                {"term_name": "低置信术语", "term_id": "T2", "match_score": 0.4},
            ],
            "fuzzy_term_matches": [{"term_name": "模糊术语", "term_id": "F1", "match_score": 0.2}],
        }

    monkeypatch.setattr(
        knowledge_enhance_module,
        "search_knowledge",
        SimpleNamespace(ainvoke=_fake_ainvoke),
    )

    state = cast(AgentState, {"messages": [HumanMessage(content="查询")]})
    out = await knowledge_enhance_node(state)

    assert [hint["term_id"] for hint in out["term_hints"]] == ["T1"]
    assert out["knowledge_snippets"][0]["source"] == "term_matches"
    evidence_ids = [row["term_id"] for row in out["knowledge_snippets"][0]["data"]]
    assert evidence_ids == ["T1", "T2"]


@pytest.mark.asyncio
async def test_knowledge_enhance_respects_configurable_threshold_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_ainvoke(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "term_matches": [
                {"term_name": "等于阈值", "term_id": "T_EQ", "match_score": 0.7},
                {"term_name": "低于阈值", "term_id": "T_LT", "match_score": 0.69},
            ]
        }

    monkeypatch.setattr(
        knowledge_enhance_module,
        "search_knowledge",
        SimpleNamespace(ainvoke=_fake_ainvoke),
    )

    state = cast(
        AgentState,
        {
            "messages": [HumanMessage(content="查询")],
            "term_hint_confidence_threshold": 0.7,
        },
    )
    out = await knowledge_enhance_node(state)

    assert [hint["term_id"] for hint in out["term_hints"]] == ["T_EQ"]
