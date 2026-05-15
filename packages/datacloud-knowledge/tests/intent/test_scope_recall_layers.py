"""Tests for split-scope recall layers and joinkey-aware scope expansion.

Covers:
- ``build_scope_recall_layers`` returns per-type (field, value) layers
- ``_collect_joinkey_related_objects`` filters by joinkeys.sourceField
- ``unified_recall`` splits terms by ktype and uses different layers
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from datacloud_knowledge.retrieval.recall import ScopeRecallLayer

# ── Helpers ────────────────────────────────────────────────────────────────


def _extracted_term(raw_text: str, ktype: str, *, vector_only: bool = False):
    """Minimal ExtractedTerm builder."""
    from datacloud_knowledge.contracts.intent_types import ExtractedTerm

    return ExtractedTerm(
        raw_text=raw_text,
        ktype=ktype,
        path="test",
        source="main",
        condition_index=-1,
        search_enabled=True,
        vector_only=vector_only,
    )


def _make_confirmed(*field_codes: str):
    """Build a PreResolveResult with fake confirmed fields."""
    from datacloud_knowledge.contracts.intent_types import PreResolveResult
    from datacloud_knowledge.contracts.types import ResolvedField

    confirmed: dict[str, ResolvedField] = {}
    for i, code in enumerate(field_codes):
        key = f"filters.{i}.field:{code}"
        confirmed[key] = ResolvedField(term_code=code, term_name=code)
    return PreResolveResult(
        confirmed=confirmed, unresolved_terms=[], value_enum_map={}, provenance={}
    )


def _mock_db_rows(*rows: tuple[str, dict | None]) -> patch:
    """Return a get_session patch that produces the given fetchall rows."""
    mock_session = MagicMock()
    mock_session.__enter__.return_value.execute.return_value.fetchall.return_value = list(rows)
    return patch(
        "datacloud_knowledge.adapters.opengauss._db.connection.get_session",
        return_value=mock_session,
    )


# ── build_scope_recall_layers ──────────────────────────────────────────────


@pytest.mark.intent
class TestBuildScopeRecallLayers:
    """build_scope_recall_layers returns per-type scope stacks."""

    def test_returns_tuple_of_field_and_value_layers(self) -> None:
        from datacloud_knowledge.retrieval._recall import build_scope_recall_layers

        field_layers, value_layers = build_scope_recall_layers(
            "by_rd_task", _make_confirmed(), _make_confirmed()
        )
        assert isinstance(field_layers, list)
        assert isinstance(value_layers, list)

    def test_no_confirmed_fields_returns_base_only_for_both(self) -> None:
        from datacloud_knowledge.retrieval._recall import build_scope_recall_layers

        field_layers, value_layers = build_scope_recall_layers(
            "by_rd_task", _make_confirmed(), _make_confirmed()
        )
        b = [ScopeRecallLayer(scope_code="by_rd_task", weight=1.0, label="ontology")]
        assert field_layers == b
        assert value_layers == b

    @patch("datacloud_knowledge.retrieval._recall._collect_joinkey_related_objects")
    def test_field_layers_base_only(self, mock_collect: MagicMock) -> None:
        from datacloud_knowledge.retrieval._recall import build_scope_recall_layers

        mock_collect.return_value = ["po_users"]
        field_layers, _value = build_scope_recall_layers(
            "by_rd_task", _make_confirmed("handler_user_id"), _make_confirmed()
        )
        assert len(field_layers) == 1
        assert field_layers[0].scope_code == "by_rd_task"

    @patch("datacloud_knowledge.retrieval._recall._collect_joinkey_related_objects")
    def test_value_layers_include_joinkey_objects(self, mock_collect: MagicMock) -> None:
        from datacloud_knowledge.retrieval._recall import build_scope_recall_layers

        mock_collect.return_value = ["po_users"]
        _field, value_layers = build_scope_recall_layers(
            "by_rd_task", _make_confirmed("handler_user_id"), _make_confirmed()
        )
        assert len(value_layers) == 2
        assert value_layers[1].scope_code == "po_users"
        assert value_layers[1].weight == 0.7
        assert value_layers[1].label == "joinkey_object"

    @patch("datacloud_knowledge.retrieval._recall._collect_joinkey_related_objects")
    def test_joinkey_duplicate_scope_skipped(self, mock_collect: MagicMock) -> None:
        from datacloud_knowledge.retrieval._recall import build_scope_recall_layers

        mock_collect.return_value = ["by_rd_task", "po_users"]
        _field, value_layers = build_scope_recall_layers(
            "by_rd_task", _make_confirmed("handler_user_id"), _make_confirmed()
        )
        scopes = [layer.scope_code for layer in value_layers]
        assert scopes == ["by_rd_task", "po_users"]  # no duplicate by_rd_task

    @patch("datacloud_knowledge.retrieval._recall._collect_joinkey_related_objects")
    def test_no_joinkeys_value_layers_base_only(self, mock_collect: MagicMock) -> None:
        from datacloud_knowledge.retrieval._recall import build_scope_recall_layers

        mock_collect.return_value = []
        _field, value_layers = build_scope_recall_layers(
            "by_opportunity", _make_confirmed("opp_name"), _make_confirmed()
        )
        assert [(layer.scope_code, layer.label) for layer in value_layers] == [
            ("by_opportunity", "ontology"),
        ]


# ── _collect_joinkey_related_objects ───────────────────────────────────────


@pytest.mark.intent
class TestCollectJoinkeyRelatedObjects:
    """_collect_joinkey_related_objects filters by joinkeys.sourceField."""

    def test_empty_field_codes_returns_empty(self) -> None:
        from datacloud_knowledge.retrieval._recall import _collect_joinkey_related_objects

        assert _collect_joinkey_related_objects("by_rd_task", []) == []

    def test_matching_source_field_returns_target(self) -> None:
        from datacloud_knowledge.retrieval._recall import _collect_joinkey_related_objects

        with _mock_db_rows(
            (
                "po_users",
                {"joinkeys": [{"sourceField": "handler_user_id", "targetField": "user_id"}]},
            ),
        ):
            result = _collect_joinkey_related_objects("by_rd_task", ["handler_user_id"])
        assert result == ["po_users"]

    def test_non_matching_source_field_returns_empty(self) -> None:
        from datacloud_knowledge.retrieval._recall import _collect_joinkey_related_objects

        with _mock_db_rows(
            ("by_project", {"joinkeys": [{"sourceField": "id", "targetField": "opp_id"}]}),
        ):
            result = _collect_joinkey_related_objects(
                "by_opportunity", ["opp_name", "contract_amount"]
            )
        assert result == []

    def test_multiple_relations_only_one_matches(self) -> None:
        from datacloud_knowledge.retrieval._recall import _collect_joinkey_related_objects

        with _mock_db_rows(
            ("po_users", {"joinkeys": [{"sourceField": "initiator_user_id"}]}),
            ("po_users", {"joinkeys": [{"sourceField": "handler_user_id"}]}),
            ("po_org", {"joinkeys": [{"sourceField": "dept_id"}]}),
        ):
            result = _collect_joinkey_related_objects("by_rd_task", ["handler_user_id"])
        assert result == ["po_users"]

    def test_multiple_matching_objects(self) -> None:
        from datacloud_knowledge.retrieval._recall import _collect_joinkey_related_objects

        with _mock_db_rows(
            ("po_users", {"joinkeys": [{"sourceField": "handler_user_id"}]}),
            ("po_org", {"joinkeys": [{"sourceField": "handler_user_id"}]}),
        ):
            result = _collect_joinkey_related_objects("by_rd_task", ["handler_user_id"])
        assert sorted(result) == ["po_org", "po_users"]

    def test_none_ext_attrs_skipped(self) -> None:
        from datacloud_knowledge.retrieval._recall import _collect_joinkey_related_objects

        with _mock_db_rows(
            ("po_users", None),  # skipped — not a dict
            ("po_org", {"joinkeys": [{"sourceField": "handler_user_id"}]}),
        ):
            result = _collect_joinkey_related_objects("by_rd_task", ["handler_user_id"])
        assert result == ["po_org"]

    def test_db_exception_returns_empty(self) -> None:
        from datacloud_knowledge.retrieval._recall import _collect_joinkey_related_objects

        bad = MagicMock()
        bad.__enter__.side_effect = RuntimeError("db down")
        with patch(
            "datacloud_knowledge.adapters.opengauss._db.connection.get_session",
            return_value=bad,
        ):
            result = _collect_joinkey_related_objects("by_rd_task", ["handler_user_id"])
        assert result == []


# ── unified_recall split by ktype ──────────────────────────────────────────


@pytest.mark.intent
class TestUnifiedRecallSplitScope:
    """unified_recall sends whereValue to value_layers, others to field_layers."""

    def test_wherevalue_uses_value_layers(self) -> None:
        from datacloud_knowledge.retrieval._recall import unified_recall

        fl = [ScopeRecallLayer(scope_code="by_rd_task", weight=1.0, label="ontology")]
        vl = [
            ScopeRecallLayer(scope_code="by_rd_task", weight=1.0, label="ontology"),
            ScopeRecallLayer(scope_code="po_users", weight=0.7, label="joinkey_object"),
        ]

        with patch(
            "datacloud_knowledge.retrieval._recall.typed_multi_recall_with_session",
            return_value={},
        ) as mock_recall:
            unified_recall(
                [_extracted_term("黄总", "whereValue")],
                scope_code="by_rd_task",
                field_layers=fl,
                value_layers=vl,
            )

        assert mock_recall.call_count == 1
        layers = mock_recall.call_args.kwargs["scope_layers"]
        assert [layer.scope_code for layer in layers] == ["by_rd_task", "po_users"]

    def test_select_uses_field_layers(self) -> None:
        from datacloud_knowledge.retrieval._recall import unified_recall

        fl = [ScopeRecallLayer(scope_code="by_opportunity", weight=1.0, label="ontology")]
        vl = [
            ScopeRecallLayer(scope_code="by_opportunity", weight=1.0, label="ontology"),
            ScopeRecallLayer(scope_code="po_users", weight=0.7, label="joinkey_object"),
        ]

        with patch(
            "datacloud_knowledge.retrieval._recall.typed_multi_recall_with_session",
            return_value={},
        ) as mock_recall:
            unified_recall(
                [_extracted_term("商机贡献率", "select")],
                scope_code="by_opportunity",
                field_layers=fl,
                value_layers=vl,
            )

        assert mock_recall.call_count == 1
        layers = mock_recall.call_args.kwargs["scope_layers"]
        assert [layer.scope_code for layer in layers] == ["by_opportunity"]

    def test_mixed_terms_separate_layers(self) -> None:
        from datacloud_knowledge.retrieval._recall import unified_recall

        fl = [ScopeRecallLayer(scope_code="by_rd_task", weight=1.0)]
        vl = [fl[0], ScopeRecallLayer(scope_code="po_users", weight=0.7)]

        with patch(
            "datacloud_knowledge.retrieval._recall.typed_multi_recall_with_session",
            return_value={},
        ) as mock_recall:
            unified_recall(
                [
                    _extracted_term("handler_user_id", "whereKey"),
                    _extracted_term("黄总", "whereValue"),
                ],
                scope_code="by_rd_task",
                field_layers=fl,
                value_layers=vl,
            )

        assert mock_recall.call_count == 2
        # field call → field_layers
        assert mock_recall.call_args_list[0].kwargs["scope_layers"] == fl
        # value call → value_layers
        assert mock_recall.call_args_list[1].kwargs["scope_layers"] == vl

    def test_falls_back_to_scope_layers_when_field_value_none(self) -> None:
        from datacloud_knowledge.retrieval._recall import unified_recall

        legacy = [ScopeRecallLayer(scope_code="by_rd_task", weight=1.0)]

        with patch(
            "datacloud_knowledge.retrieval._recall.typed_multi_recall_with_session",
            return_value={},
        ) as mock_recall:
            unified_recall(
                [
                    _extracted_term("handler_user_id", "whereKey"),
                    _extracted_term("黄总", "whereValue"),
                ],
                scope_code="by_rd_task",
                scope_layers=legacy,
            )

        assert mock_recall.call_count == 2
        for call in mock_recall.call_args_list:
            assert call.kwargs["scope_layers"] == legacy

    def test_vector_only_terms_skip_typed_recall(self) -> None:
        from datacloud_knowledge.retrieval._recall import unified_recall

        terms = [_extracted_term("stat_date", "select", vector_only=True)]
        fl = [ScopeRecallLayer(scope_code="by_rd_task", weight=1.0)]

        with (
            patch(
                "datacloud_knowledge.retrieval._recall.typed_multi_recall_with_session",
                return_value={},
            ) as mock_recall,
            patch(
                "datacloud_knowledge.retrieval._recall._vector_only_recall",
                return_value={"select:stat_date": []},
            ) as mock_vector,
        ):
            unified_recall(terms, scope_code="by_rd_task", field_layers=fl)

        mock_recall.assert_not_called()
        mock_vector.assert_called_once()

    def test_duplicate_terms_deduped(self) -> None:
        from datacloud_knowledge.retrieval._recall import unified_recall

        fl = [ScopeRecallLayer(scope_code="by_rd_task", weight=1.0)]
        vl = [fl[0], ScopeRecallLayer(scope_code="po_users", weight=0.7)]

        with patch(
            "datacloud_knowledge.retrieval._recall.typed_multi_recall_with_session",
            return_value={},
        ) as mock_recall:
            unified_recall(
                [_extracted_term("黄总", "whereValue"), _extracted_term("黄总", "whereValue")],
                scope_code="by_rd_task",
                field_layers=fl,
                value_layers=vl,
            )

        assert mock_recall.call_count == 1
        items = mock_recall.call_args.args[0]
        assert len(items) == 1
