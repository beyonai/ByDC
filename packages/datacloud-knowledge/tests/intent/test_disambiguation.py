from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


def _get_disambiguation_module() -> Any:
    return import_module("datacloud_knowledge.intent.disambiguation")


def _get_types_module() -> Any:
    return import_module("datacloud_knowledge.intent.types")


def _candidate(
    term_id: str,
    term_name: str,
    confidence: float,
    score: float,
) -> Any:
    types_module = _get_types_module()
    match_candidate = types_module.MatchCandidate

    return match_candidate(
        term_id=term_id,
        term_name=term_name,
        term_type_code="OBJECT",
        match_type="exact",
        confidence=confidence,
        score=score,
    )


@pytest.mark.intent
def test_disambiguate_single_high_confidence_candidate_is_confirmed() -> None:
    disambiguation_module = _get_disambiguation_module()
    types_module = _get_types_module()
    disambiguate = disambiguation_module.disambiguate
    match_result_type = types_module.MatchResult

    candidate = _candidate("TERM_001", "企业", 0.98, 0.2)
    match_result = match_result_type(exact={"企业": (candidate,)}, fuzzy={})

    result = disambiguate(match_result=match_result, session=None)

    assert result.confirmed == {"企业": candidate}
    assert result.ambiguous == {}


@pytest.mark.intent
def test_disambiguate_multiple_candidates_prefers_top_score_gap() -> None:
    disambiguation_module = _get_disambiguation_module()
    types_module = _get_types_module()
    disambiguate = disambiguation_module.disambiguate
    match_result_type = types_module.MatchResult

    top_candidate = _candidate("TERM_001", "企业", 0.92, 0.5)
    runner_up = _candidate("TERM_002", "企业", 0.88, 0.0)
    match_result = match_result_type(exact={"企业": (top_candidate, runner_up)}, fuzzy={})

    result = disambiguate(match_result=match_result, session=None)

    assert result.confirmed == {"企业": top_candidate}
    assert result.ambiguous == {}


@pytest.mark.intent
def test_disambiguate_empty_match_result_returns_empty_result() -> None:
    disambiguation_module = _get_disambiguation_module()
    types_module = _get_types_module()
    disambiguate = disambiguation_module.disambiguate
    match_result_type = types_module.MatchResult

    result = disambiguate(match_result=match_result_type(exact={}, fuzzy={}), session=None)

    assert result.confirmed == {}
    assert result.ambiguous == {}
