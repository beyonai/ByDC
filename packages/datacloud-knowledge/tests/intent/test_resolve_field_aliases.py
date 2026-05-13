"""Tests for resolve_field_aliases with mocked DB session."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from datacloud_knowledge.api.types import (
    FieldResolutionResult,
)


class _FakeRow:
    """Simulates a SQLAlchemy Row with positional access."""

    def __init__(self, name_text: str, term_code: str, term_name: str, scope: dict[str, str]):
        self._data = ("field", name_text, term_code, term_name, scope)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._data)


def _make_rows(*tuples: tuple[str, str, str, dict[str, str]]) -> list[_FakeRow]:
    return [_FakeRow(*t) for t in tuples]


@pytest.fixture()
def _mock_session():  # type: ignore[no-untyped-def]
    """Patch get_session to return a controllable mock."""
    mock_session = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_session)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with patch(
        "datacloud_knowledge.search.term_search.get_session",
        return_value=mock_cm,
    ):
        yield mock_session


@pytest.mark.intent
class TestResolveFieldAliases:
    """resolve_field_aliases: resolved / ambiguous / unresolved classification."""

    def test_empty_terms_returns_empty(self) -> None:
        from datacloud_knowledge.search import resolve_field_aliases

        result = resolve_field_aliases(terms=[], scope_code="scene_enterprise_analysis")
        assert result == FieldResolutionResult(unresolved=[])

    def test_empty_scope_returns_all_unresolved(self) -> None:
        from datacloud_knowledge.search import resolve_field_aliases

        result = resolve_field_aliases(terms=["总营收"], scope_code="")
        assert result.unresolved == ["总营收"]
        assert result.resolved == {}

    def test_single_resolved(self, _mock_session: MagicMock) -> None:
        from datacloud_knowledge.search import resolve_field_aliases

        _mock_session.execute.return_value = MagicMock(
            all=MagicMock(
                return_value=_make_rows(
                    ("总营收（万元）", "total_revenue", "总营收", {"scope": "global"}),
                )
            )
        )
        result = resolve_field_aliases(
            terms=["总营收（万元）"],
            scope_code="scene_enterprise_analysis",
        )
        assert result.resolved == {"总营收（万元）": "total_revenue"}
        assert result.ambiguous == {}
        assert result.unresolved == []

    def test_ambiguous_multiple_codes(self, _mock_session: MagicMock) -> None:
        from datacloud_knowledge.search import resolve_field_aliases

        _mock_session.execute.return_value = MagicMock(
            all=MagicMock(
                return_value=_make_rows(
                    ("营收", "total_revenue", "总营收", {"scope": "global"}),
                    ("营收", "net_revenue", "净营收", {"scope": "global"}),
                )
            )
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

    def test_unresolved_no_match(self, _mock_session: MagicMock) -> None:
        from datacloud_knowledge.search import resolve_field_aliases

        _mock_session.execute.return_value = MagicMock(all=MagicMock(return_value=[]))
        result = resolve_field_aliases(
            terms=["不存在的字段"],
            scope_code="scene_enterprise_analysis",
        )
        assert result.resolved == {}
        assert result.unresolved == ["不存在的字段"]

    def test_mixed_resolved_and_unresolved(self, _mock_session: MagicMock) -> None:
        from datacloud_knowledge.search import resolve_field_aliases

        _mock_session.execute.return_value = MagicMock(
            all=MagicMock(
                return_value=_make_rows(
                    ("总营收（万元）", "total_revenue", "总营收", {"scope": "global"}),
                )
            )
        )
        result = resolve_field_aliases(
            terms=["总营收（万元）", "不存在"],
            scope_code="scene_enterprise_analysis",
        )
        assert result.resolved == {"总营收（万元）": "total_revenue"}
        assert result.unresolved == ["不存在"]

    def test_deduplicates_input_terms(self, _mock_session: MagicMock) -> None:
        from datacloud_knowledge.search import resolve_field_aliases

        _mock_session.execute.return_value = MagicMock(
            all=MagicMock(
                return_value=_make_rows(
                    ("总营收", "total_revenue", "总营收", {"scope": "global"}),
                )
            )
        )
        result = resolve_field_aliases(
            terms=["总营收", "总营收", "总营收"],
            scope_code="scene_enterprise_analysis",
        )
        assert result.resolved == {"总营收": "total_revenue"}
        assert result.unresolved == []

    def test_db_exception_propagates(self, _mock_session: MagicMock) -> None:
        from datacloud_knowledge.search import resolve_field_aliases

        _mock_session.execute.side_effect = RuntimeError("connection refused")
        with pytest.raises(RuntimeError, match="connection refused"):
            resolve_field_aliases(
                terms=["总营收"],
                scope_code="scene_enterprise_analysis",
            )
