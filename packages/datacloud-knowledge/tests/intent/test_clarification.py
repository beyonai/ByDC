from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _get_intent_module() -> Any:
    return import_module("datacloud_knowledge.intent")


def _get_types_module() -> Any:
    return import_module("datacloud_knowledge.intent.types")


@pytest.mark.intent
def test_analyze_query_clarification_returns_form_for_industry_chain_query() -> None:
    intent_module = _get_intent_module()
    clarification_result = _get_types_module().ClarificationResult
    result = intent_module.analyze_query_clarification(
        "信息技术、汽车各链的上游、下游的龙头、骨干企业数"
    )

    assert isinstance(result, clarification_result)
    assert result.needs_clarification is True
    assert result.knowledge == ""
    form_payload = json.loads(result.form)
    assert form_payload["paradigmList"][0]["paradigmName"] == "查询值"
    assert result.query.startswith("信息技术链的上游龙头企业数")


@pytest.mark.intent
def test_analyze_query_clarification_returns_knowledge_for_grid_benefit_query() -> None:
    result = _get_intent_module().analyze_query_clarification(
        "高效益、中效益、低效益网格的营收、利润、亩产"
    )

    assert result.needs_clarification is False
    assert result.form == ""
    knowledge_payload = json.loads(result.knowledge)
    assert knowledge_payload["paradigmList"][1]["paradigmName"] == "分组条件"
    assert "高效益网格的营收" in result.query


@pytest.mark.intent
def test_analyze_query_clarification_passthrough_for_unknown_query() -> None:
    query = "查询所有客户"

    clarification_result = _get_types_module().ClarificationResult
    result = _get_intent_module().analyze_query_clarification(query)

    assert result == clarification_result(query=query)


@pytest.mark.intent
def test_clarification_result_legacy_mapping() -> None:
    clarification_result = _get_types_module().ClarificationResult
    result = clarification_result(query="q", needs_clarification=True, form="f", knowledge="k")

    assert result.to_legacy_dict() == {
        "query": "q",
        "complex_ask_user": True,
        "form": "f",
        "knowledge": "k",
    }
