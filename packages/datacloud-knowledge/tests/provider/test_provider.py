"""Provider 集成测试。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from datacloud_knowledge.contracts.types import FieldResolutionResult, SearchTermsResult
from datacloud_knowledge.intent.types import ClarificationResult
from datacloud_knowledge.provider import (
    ClarificationAnalysis,
    FinalizedClarification,
    PersistedSynonyms,
    finalize_query_clarification,
    prepare_query_clarification,
    resolve_field_aliases,
    search_terms_by_type,
)


def test_resolve_field_aliases_delegates_to_reader() -> None:
    """字段别名解析委托给 PostgresTermReader。"""
    expected = FieldResolutionResult(resolved={"销售额": "sales_amount"})
    with patch(
        "datacloud_knowledge.adapters.opengauss.reader.PostgresTermReader.resolve_field_aliases",
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
        resolve_values=False,
        value_terms=["华东"],
    )


def test_search_terms_by_type_delegates_to_reader() -> None:
    """术语检索委托给 PostgresTermReader。"""
    expected = SearchTermsResult(total=0, items=[])
    with patch(
        "datacloud_knowledge.adapters.opengauss.reader.PostgresTermReader.search_terms",
        return_value=expected,
    ) as mock_search:
        result = search_terms_by_type(term_type_code="metric", keyword="销售额")

    assert result == expected
    mock_search.assert_called_once_with(
        term_type_code="metric",
        keyword="销售额",
        tags=None,
        limit=20,
        offset=0,
        order_by="relevance",
    )


def test_prepare_query_clarification_facade_delegates() -> None:
    """查询澄清分析委托给 intent 模块。"""
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
        language="zh_CN",
    )


def test_finalize_query_clarification_without_clarification_normalizes() -> None:
    """不需要澄清时仍执行标准化。"""
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
    """需要澄清时应用表单并持久化同义词。"""
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
    """需要澄清时缺少表单或元数据则抛异常。"""
    with pytest.raises(ValueError, match="form and metadata are required"):
        finalize_query_clarification(
            query="q",
            ontology_code="sales",
            structured_input={"select": ["销售额"]},
            mode="query",
            needs_clarification=True,
        )
