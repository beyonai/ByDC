from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from datacloud_knowledge.intent.types import ClarificationResult
from datacloud_knowledge.knowledge_search.types import FieldResolutionResult, SearchTermsResult
from datacloud_knowledge.provider import (
    ClarificationAnalysis,
    FinalizedClarification,
    FunctionKnowledgeProvider,
    PersistedSynonyms,
    finalize_query_clarification,
    get_provider,
    prepare_query_clarification,
    reset_provider,
    resolve_field_aliases,
    search_terms_by_type,
)


@pytest.fixture(autouse=True)
def _reset_provider() -> Iterator[None]:
    reset_provider(None)
    yield
    reset_provider(None)


def test_get_provider_uses_lazy_singleton() -> None:
    first = get_provider()
    second = get_provider()

    assert isinstance(first, FunctionKnowledgeProvider)
    assert first is second


def test_reset_provider_accepts_custom_instance() -> None:
    custom = FunctionKnowledgeProvider()

    reset_provider(custom)

    assert get_provider() is custom


def test_resolve_field_aliases_facade_delegates() -> None:
    expected = FieldResolutionResult(resolved={"销售额": "sales_amount"})
    with patch(
        "datacloud_knowledge.provider._resolve_field_aliases",
        return_value=expected,
    ) as mock_resolve:
        result = resolve_field_aliases(
            terms=("销售额",),
            scope_code="sales",
            value_terms=("华东",),
        )

    assert result == expected
    mock_resolve.assert_called_once_with(
        terms=["销售额"],
        scope_code="sales",
        library_id=None,
        user_id=None,
        resolve_values=False,
        value_terms=["华东"],
    )


def test_search_terms_by_type_facade_delegates() -> None:
    expected = SearchTermsResult(total=0, items=[])
    with patch(
        "datacloud_knowledge.provider._search_terms_by_type",
        return_value=expected,
    ) as mock_search:
        result = search_terms_by_type(term_type_code="metric", keyword="销售额")

    assert result == expected
    mock_search.assert_called_once_with(
        term_type_code="metric",
        term_codes=None,
        keyword="销售额",
        tags=None,
        limit=20,
        offset=0,
        order_by="relevance",
    )


def test_prepare_query_clarification_facade_delegates() -> None:
    legacy_result = ClarificationResult(
        query="q",
        needs_clarification=True,
        form='{"paradigmList": []}',
        knowledge='{"path_mapping": {}}',
    )
    with patch(
        "datacloud_knowledge.provider._analyze_query_clarification",
        return_value=legacy_result,
    ) as mock_prepare:
        result = prepare_query_clarification(
            query="q",
            ontology_code="sales",
            structured_input={"select": ["销售额"]},
            mode="query",
        )

    assert result == ClarificationAnalysis(
        needs_clarification=True,
        form='{"paradigmList": []}',
        metadata='{"path_mapping": {}}',
    )
    assert result.knowledge == result.metadata
    mock_prepare.assert_called_once_with(
        query="q",
        ontology_code="sales",
        structured_input={"select": ["销售额"]},
        mode="query",
    )


def test_finalize_query_clarification_without_clarification_normalizes() -> None:
    normalized = {"select": ["sales_amount"]}
    with (
        patch(
            "datacloud_knowledge.provider._normalize_clarification_params",
            return_value=normalized,
        ) as mock_normalize,
        patch(
            "datacloud_knowledge.provider._persist_confirmed_synonyms",
            return_value=[],
        ) as mock_persist,
    ):
        result = finalize_query_clarification(
            query="q",
            ontology_code="sales",
            structured_input={"select": ["销售额"]},
            mode="query",
            needs_clarification=False,
        )

    assert result == FinalizedClarification(
        structured_input=normalized,
        changed_paths=["select[0]"],
    )
    mock_normalize.assert_called_once_with(
        {"select": ["销售额"]},
        ontology_code="sales",
        user_id=None,
    )
    mock_persist.assert_not_called()


def test_finalize_query_clarification_applies_form_and_persists() -> None:
    formatted = {"select": ["销售额"]}
    normalized = {"select": ["sales_amount"]}
    with (
        patch(
            "datacloud_knowledge.provider._format_clarification_query",
            return_value=formatted,
        ) as mock_format,
        patch(
            "datacloud_knowledge.provider._normalize_clarification_params",
            return_value=normalized,
        ) as mock_normalize,
        patch(
            "datacloud_knowledge.provider._persist_confirmed_synonyms",
            return_value=["name-1"],
        ) as mock_persist,
    ):
        result = finalize_query_clarification(
            query="q",
            ontology_code="sales",
            structured_input={"select": ["销售额"]},
            mode="query",
            needs_clarification=True,
            form={"paradigmList": [{"keyword": "销售额"}]},
            metadata={"path_mapping": {"0": "select.0"}},
            user_id="u-1",
        )

    assert result == FinalizedClarification(
        structured_input=normalized,
        changed_paths=["select[0]"],
        persisted_synonyms=PersistedSynonyms(created_ids=["name-1"]),
    )
    mock_format.assert_called_once_with(
        "q",
        {"select": ["销售额"]},
        '{"paradigmList": [{"keyword": "销售额"}]}',
        '{"path_mapping": {"0": "select.0"}}',
    )
    mock_normalize.assert_called_once_with(
        formatted,
        ontology_code="sales",
        user_id="u-1",
    )
    mock_persist.assert_called_once_with(
        paradigm_list=[{"keyword": "销售额"}],
        ontology_code="sales",
        user_id="u-1",
    )


def test_finalize_query_clarification_requires_payloads_when_needed() -> None:
    with pytest.raises(ValueError, match="form and metadata are required"):
        finalize_query_clarification(
            query="q",
            ontology_code="sales",
            structured_input={"select": ["销售额"]},
            mode="query",
            needs_clarification=True,
        )
