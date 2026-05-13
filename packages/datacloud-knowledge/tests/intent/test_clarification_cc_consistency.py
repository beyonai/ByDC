from __future__ import annotations

import pytest
from datacloud_knowledge.contracts.types import (
    FieldResolutionResultWithNames,
    ResolvedField,
)
from datacloud_knowledge.intent.clarification import _merge, _pre_resolve
from datacloud_knowledge.intent.clarification.models import (
    CCConfirmResult,
    CCTermConfirmation,
    CCTermMeta,
    ConditionTermMapping,
    ExtractedTerm,
)


@pytest.mark.intent
def test_pre_resolve_supports_complex_condition_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_resolve_field_aliases_with_names(
        self,
        *,
        terms: list[str],
        scope_code: str,
    ) -> FieldResolutionResultWithNames:
        assert terms == ["亩产效益"]
        assert scope_code == "scene_enterprise_analysis"
        return FieldResolutionResultWithNames(
            resolved={"亩产效益": ResolvedField(term_code="yield_eff", term_name="亩产效益")},
        )

    monkeypatch.setattr(
        "datacloud_knowledge.adapters.opengauss.reader.PostgresTermReader.resolve_field_aliases_with_names",
        _fake_resolve_field_aliases_with_names,
    )
    monkeypatch.setattr(
        "datacloud_knowledge.adapters.opengauss.reader.PostgresTermReader.get_prop_enum_values",
        lambda self, **_: {},
    )

    term = ExtractedTerm(
        raw_text="亩产效益",
        ktype="whereKey",
        path="complex_conditions.0.where.0.field",
        source="complex_condition",
        condition_index=0,
    )

    result = _pre_resolve.pre_resolve_terms([term], scope_code="scene_enterprise_analysis")

    assert result.confirmed[_pre_resolve.term_key(term)].term_name == "亩产效益"
    assert result.unresolved_terms == []


@pytest.mark.intent
def test_cc_reuses_main_confirmation_when_confirmed_value_is_candidate() -> None:
    hints = {
        ("whereKey", "亩产效益"): _merge._TermResolutionHint(
            confirmed="亩产效益",
            candidates=("亩产效益", "亩均税收"),
        )
    }
    registry = {
        1: CCTermMeta(
            raw_text="亩产效益",
            ktype="whereKey",
            start=0,
            end=4,
            condition_index=0,
        )
    }
    result = CCConfirmResult(
        confirmations=[
            CCTermConfirmation(
                term_id=1,
                confirmed=None,
                candidates=["亩均税收", "亩产效益"],
            )
        ]
    )

    normalized = _merge.normalize_cc_result_with_hints(result, registry, hints, recall_map={})

    assert normalized is not None
    assert normalized.confirmations[0].confirmed == "亩产效益"
    assert normalized.confirmations[0].candidates == []


@pytest.mark.intent
def test_cc_merges_candidates_with_rrf_when_prior_confirmed_value_is_absent() -> None:
    hints = {
        ("whereKey", "亩产效益"): _merge._TermResolutionHint(
            confirmed="亩产效益",
            candidates=("亩产效益", "亩均税收"),
        )
    }
    registry = {
        1: CCTermMeta(
            raw_text="亩产效益",
            ktype="whereKey",
            start=0,
            end=4,
            condition_index=0,
        )
    }
    result = CCConfirmResult(
        confirmations=[
            CCTermConfirmation(
                term_id=1,
                confirmed=None,
                candidates=["企业营收", "企业利润"],
            )
        ]
    )

    normalized = _merge.normalize_cc_result_with_hints(result, registry, hints, recall_map={})

    assert normalized is not None
    confirmation = normalized.confirmations[0]
    assert confirmation.confirmed is None
    assert confirmation.candidates[0] == "企业营收"
    assert "企业利润" in confirmation.candidates
    assert "亩产效益" in confirmation.candidates
    assert len(confirmation.candidates) == len(set(confirmation.candidates))


@pytest.mark.intent
def test_cc_terms_reuse_previous_cc_confirmation_in_order() -> None:
    hints: dict[tuple[str, str], _merge._TermResolutionHint] = {}
    registry = {
        1: CCTermMeta(
            raw_text="亩产效益",
            ktype="whereKey",
            start=0,
            end=4,
            condition_index=0,
        )
    }
    first_result = CCConfirmResult(
        confirmations=[CCTermConfirmation(term_id=1, confirmed="亩产效益", candidates=[])]
    )

    _merge.merge_cc_resolution_hints(hints, first_result, registry)

    second_result = CCConfirmResult(
        confirmations=[
            CCTermConfirmation(
                term_id=1,
                confirmed=None,
                candidates=["亩均税收", "亩产效益"],
            )
        ]
    )
    normalized = _merge.normalize_cc_result_with_hints(
        second_result, registry, hints, recall_map={}
    )

    assert normalized is not None
    assert normalized.confirmations[0].confirmed == "亩产效益"


@pytest.mark.intent
def test_complex_condition_duplicate_span_mappings_are_deduped_with_rrf() -> None:
    mappings = [
        ConditionTermMapping(
            original_term="贡献率",
            start=0,
            end=3,
            confirmed=None,
            candidates=["所属管理网格实际税负率（%）", "所属管理网格亩产效益（万元/亩）"],
        ),
        ConditionTermMapping(
            original_term="贡献率",
            start=0,
            end=3,
            confirmed=None,
            candidates=["所属管理网格实际税负率（%）"],
        ),
    ]

    deduped = _merge._dedupe_condition_term_mappings(mappings)

    assert len(deduped) == 1
    assert deduped[0].original_term == "贡献率"
    assert deduped[0].candidates == [
        "所属管理网格实际税负率（%）",
        "所属管理网格亩产效益（万元/亩）",
    ]
