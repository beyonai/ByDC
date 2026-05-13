"""Tests for resolve_field_aliases with mocked reader adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from datacloud_knowledge.contracts.types import (
    AmbiguousCandidate,
    FieldResolutionResult,
)


def _make_resolved_result(
    resolved: dict[str, str] | None = None,
    ambiguous: dict[str, list[AmbiguousCandidate]] | None = None,
    unresolved: list[str] | None = None,
) -> FieldResolutionResult:
    return FieldResolutionResult(
        resolved=resolved or {},
        ambiguous=ambiguous or {},
        unresolved=unresolved or [],
    )


@pytest.fixture()
def _mock_reader() -> MagicMock:
    """Patch create_reader to return a controllable mock reader."""
    mock_reader = MagicMock()
    with patch(
        "datacloud_knowledge.retrieval.term_search.create_reader",
        return_value=mock_reader,
    ):
        yield mock_reader


@pytest.mark.intent
class TestResolveFieldAliases:
    """resolve_field_aliases: resolved / ambiguous / unresolved classification."""

    def test_empty_terms_returns_empty(self) -> None:
        from datacloud_knowledge.retrieval import resolve_field_aliases

        result = resolve_field_aliases(terms=[], scope_code="scene_enterprise_analysis")
        assert result == FieldResolutionResult(unresolved=[])

    def test_empty_scope_returns_all_unresolved(self) -> None:
        from datacloud_knowledge.retrieval import resolve_field_aliases

        result = resolve_field_aliases(terms=["总营收"], scope_code="")
        assert result.unresolved == ["总营收"]
        assert result.resolved == {}

    def test_single_resolved(self, _mock_reader: MagicMock) -> None:
        from datacloud_knowledge.retrieval import resolve_field_aliases

        _mock_reader.resolve_field_aliases.return_value = _make_resolved_result(
            resolved={"总营收（万元）": "total_revenue"},
        )
        result = resolve_field_aliases(
            terms=["总营收（万元）"],
            scope_code="scene_enterprise_analysis",
        )
        assert result.resolved == {"总营收（万元）": "total_revenue"}
        assert result.ambiguous == {}
        assert result.unresolved == []

    def test_ambiguous_multiple_codes(self, _mock_reader: MagicMock) -> None:
        from datacloud_knowledge.retrieval import resolve_field_aliases

        _mock_reader.resolve_field_aliases.return_value = _make_resolved_result(
            ambiguous={
                "营收": [
                    AmbiguousCandidate(
                        term_code="total_revenue",
                        term_name="总营收",
                        matched_alias="营收",
                    ),
                    AmbiguousCandidate(
                        term_code="net_revenue",
                        term_name="净营收",
                        matched_alias="营收",
                    ),
                ]
            },
        )
        result = resolve_field_aliases(
            terms=["营收"],
            scope_code="scene_enterprise_analysis",
        )
        assert result.resolved == {}
        assert "营收" in result.ambiguous
        assert len(result.ambiguous["营收"]) == 2
        codes = {c.term_code for c in result.ambiguous["营收"]}
        assert codes == {"total_revenue", "net_revenue"}

    def test_unresolved_no_match(self, _mock_reader: MagicMock) -> None:
        from datacloud_knowledge.retrieval import resolve_field_aliases

        _mock_reader.resolve_field_aliases.return_value = _make_resolved_result(
            unresolved=["不存在的字段"],
        )
        result = resolve_field_aliases(
            terms=["不存在的字段"],
            scope_code="scene_enterprise_analysis",
        )
        assert result.resolved == {}
        assert result.unresolved == ["不存在的字段"]

    def test_mixed_resolved_and_unresolved(self, _mock_reader: MagicMock) -> None:
        from datacloud_knowledge.retrieval import resolve_field_aliases

        _mock_reader.resolve_field_aliases.return_value = _make_resolved_result(
            resolved={"总营收（万元）": "total_revenue"},
            unresolved=["不存在"],
        )
        result = resolve_field_aliases(
            terms=["总营收（万元）", "不存在"],
            scope_code="scene_enterprise_analysis",
        )
        assert result.resolved == {"总营收（万元）": "total_revenue"}
        assert result.unresolved == ["不存在"]

    def test_deduplicates_input_terms(self, _mock_reader: MagicMock) -> None:
        from datacloud_knowledge.retrieval import resolve_field_aliases

        _mock_reader.resolve_field_aliases.return_value = _make_resolved_result(
            resolved={"总营收": "total_revenue"},
        )
        result = resolve_field_aliases(
            terms=["总营收", "总营收", "总营收"],
            scope_code="scene_enterprise_analysis",
        )
        assert result.resolved == {"总营收": "total_revenue"}
        assert result.unresolved == []

    def test_db_exception_propagates(self, _mock_reader: MagicMock) -> None:
        from datacloud_knowledge.retrieval import resolve_field_aliases

        _mock_reader.resolve_field_aliases.side_effect = RuntimeError("connection refused")
        with pytest.raises(RuntimeError, match="connection refused"):
            resolve_field_aliases(
                terms=["总营收"],
                scope_code="scene_enterprise_analysis",
            )
