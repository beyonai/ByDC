from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.messages import HumanMessage

from datacloud_analysis.orchestration.knowledge_enhance import knowledge_enhance_node
from datacloud_analysis.orchestration.knowledge_enhance import node as knowledge_enhance_module
from datacloud_analysis.orchestration.state import AgentState


@pytest.mark.asyncio
async def test_knowledge_enhance_filters_low_confidence_term_hints_and_keeps_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_ainvoke(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "term_matches": [
                {"term_name": "高置信术语A", "term_id": "T1", "match_score": 0.95},
                {"term_name": "低置信术语B", "term_id": "T2", "match_score": 0.4},
            ],
            "fuzzy_term_matches": [{"mention": "模糊术语", "candidates": [{"term_id": "F1"}]}],
            "term_subgraphs": [
                {
                    "tree": {
                        "term_id": "T1",
                        "knowledge": [
                            "高置信术语A用于测试知识摘要生成，主要用于企业经营分析与指标解释，"
                            "能够帮助规划节点理解术语语义并生成稳定任务。"
                        ],
                        "children": [],
                    }
                }
            ],
        }

    monkeypatch.setattr(
        knowledge_enhance_module,
        "search_knowledge",
        SimpleNamespace(ainvoke=_fake_ainvoke),
    )

    state = cast(AgentState, {"messages": [HumanMessage(content="查询一下")]})
    out = await knowledge_enhance_node(state)

    assert [hint["term_id"] for hint in out["term_hints"]] == ["T1"]
    first_snippet = out["knowledge_snippets"][0]
    assert first_snippet["source"] == "term_matches"
    assert first_snippet["char_len"] > 0
    evidence_ids = [row["term_id"] for row in first_snippet["data"]]
    assert evidence_ids == ["T1", "T2"]
    assert "补充知识：" in out["enriched_query"]
    assert out["enriched_query_source"] == "confirmed_terms"
    assert out["ambiguous_terms"][0]["mention"] == "模糊术语"
    assert out["ambiguous_terms"][0]["reason"] == "no_high_confidence_match"
    assert "knowledge_preview" not in out


@pytest.mark.asyncio
async def test_knowledge_enhance_respects_configurable_threshold_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_ainvoke(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "term_matches": [
                {"term_name": "绛変簬闃堝€?", "term_id": "T_EQ", "match_score": 0.7},
                {"term_name": "浣庝簬闃堝€?", "term_id": "T_LT", "match_score": 0.69},
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
            "messages": [HumanMessage(content="鏌ヨ")],
            "term_hint_confidence_threshold": 0.7,
        },
    )
    out = await knowledge_enhance_node(state)

    assert [hint["term_id"] for hint in out["term_hints"]] == ["T_EQ"]


@pytest.mark.asyncio
async def test_knowledge_enhance_fallback_when_no_knowledge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_ainvoke(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "term_matches": [{"term_name": "术语无知识", "term_id": "T1", "match_score": 0.95}],
            "fuzzy_term_matches": [],
            "term_subgraphs": [],
        }

    monkeypatch.setattr(
        knowledge_enhance_module,
        "search_knowledge",
        SimpleNamespace(ainvoke=_fake_ainvoke),
    )

    state = cast(AgentState, {"messages": [HumanMessage(content="查询一下")]})
    out = await knowledge_enhance_node(state)

    assert out["enriched_query"] == "查询一下"
    assert out["enriched_query_source"] == "fallback_user_query"


@pytest.mark.asyncio
async def test_knowledge_enhance_emits_non_blocking_thinking_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[str] = []

    class _GatewayContext:
        async def emit_chunk(self, event: Any, **_kwargs: Any) -> None:
            emitted.append(str(getattr(event, "content", event)))

    async def _fake_ainvoke(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "term_matches": [
                {
                    "term_name": "企业综合分析表",
                    "normalized_term": "企业综合分析表",
                    "term_id": "T1",
                    "match_score": 0.95,
                    "definition": (
                        "企业综合分析表用于分析企业经营情况和基础画像，覆盖企业规模、营收变化、"
                        "经营稳定性等维度，并支持横向对比和趋势追踪。"
                    ),
                }
            ],
            "fuzzy_term_matches": [
                {
                    "mention": "活跃用户",
                    "candidates": [
                        {"term_id": "A1", "term_name": "DAU", "term_type_code": "METRIC"},
                        {"term_id": "A2", "term_name": "MAU", "term_type_code": "METRIC"},
                    ],
                }
            ],
            "term_subgraphs": [],
        }

    monkeypatch.setattr(
        knowledge_enhance_module,
        "search_knowledge",
        SimpleNamespace(ainvoke=_fake_ainvoke),
    )

    state = cast(AgentState, {"messages": [HumanMessage(content="查询企业综合分析表和活跃用户")]})
    out = await knowledge_enhance_node(state, gateway_context=_GatewayContext())

    assert out["ambiguous_terms"][0]["mention"] == "活跃用户"
    assert any("存在歧义的术语：活跃用户" in chunk for chunk in emitted)
    assert any("已确权的术语：" in chunk and "企业综合分析表" in chunk for chunk in emitted)
    assert any("改写后的问题：" in chunk and "补充知识：" in chunk for chunk in emitted)
