from __future__ import annotations

from datacloud_knowledge.intent.clarification.postprocess import (
    normalize_clarification_params,
    persist_confirmed_synonyms,
)
from datacloud_knowledge.contracts.types import FieldResolutionResult


def test_normalize_clarification_params_translates_fields_to_codes(monkeypatch) -> None:
    def _fake_resolve_field_aliases(
        *, terms, scope_code, library_id=None, user_id=None, resolve_values=False, value_terms=None
    ):
        assert terms == ["企业总营收（万元）", "企业总营收（万元）"]
        assert scope_code == "ads_enterprise"
        assert user_id == "user-1"
        _ = library_id, resolve_values, value_terms
        return FieldResolutionResult(
            resolved={"企业总营收（万元）": "total_revenue"},
            ambiguous={},
            unresolved=[],
        )

    monkeypatch.setattr(
        "datacloud_knowledge.intent.clarification.postprocess.resolve_field_aliases",
        _fake_resolve_field_aliases,
    )
    monkeypatch.setattr(
        "datacloud_knowledge.intent.clarification.postprocess._load_scope_term_maps",
        lambda scope_code: (
            {
                "field_terms": {"企业总营收（万元）": "prop-1", "total_revenue": "prop-1"},
                "prop_codes": {"total_revenue": "prop-1"},
                "value_terms_by_prop": {},
                "prop_value_codes": {},
            }
            if scope_code == "ads_enterprise"
            else {
                "field_terms": {},
                "prop_codes": {},
                "value_terms_by_prop": {},
                "prop_value_codes": {},
            }
        ),
    )

    normalized = normalize_clarification_params(
        {
            "select": ["企业总营收（万元）"],
            "filters": [{"field": "企业总营收（万元）", "op": "gt", "value": 100}],
        },
        ontology_code="ads_enterprise",
        user_id="user-1",
    )

    assert normalized["select"] == ["total_revenue"]
    assert normalized["filters"] == [{"field": "total_revenue", "op": "gt", "value": 100}]


def test_normalize_clarification_params_translates_filter_values_to_codes(monkeypatch) -> None:
    monkeypatch.setattr(
        "datacloud_knowledge.intent.clarification.postprocess.resolve_field_aliases",
        lambda **kwargs: FieldResolutionResult(
            resolved={"区域": "region_code"},
            ambiguous={},
            unresolved=[],
        ),
    )
    monkeypatch.setattr(
        "datacloud_knowledge.intent.clarification.postprocess._load_scope_term_maps",
        lambda scope_code: (
            {
                "field_terms": {"区域": "prop-1", "region_code": "prop-1"},
                "prop_codes": {"区域": "prop-1", "region_code": "prop-1"},
                "value_terms_by_prop": {"prop-1": {"华东大区": "value-1", "华东区": "value-1"}},
                "prop_value_codes": {
                    "prop-1": {"华东大区": "east_region", "华东区": "east_region"}
                },
            }
            if scope_code == "ads_enterprise"
            else {
                "field_terms": {},
                "prop_codes": {},
                "value_terms_by_prop": {},
                "prop_value_codes": {},
            }
        ),
    )

    normalized = normalize_clarification_params(
        {"filters": [{"field": "区域", "op": "eq", "value": "华东大区"}]},
        ontology_code="ads_enterprise",
        user_id="user-1",
    )

    assert normalized["filters"] == [{"field": "region_code", "op": "eq", "value": "east_region"}]


def test_persist_confirmed_synonyms_uses_scope_terms(monkeypatch) -> None:
    monkeypatch.setattr(
        "datacloud_knowledge.intent.clarification.postprocess._load_scope_term_maps",
        lambda scope_code: (
            {
                "field_terms": {
                    "企业总营收（万元）": "term-1",
                    "total_revenue": "term-1",
                },
                "prop_codes": {
                    "企业总营收（万元）": "term-1",
                    "total_revenue": "term-1",
                },
                "value_terms_by_prop": {},
            }
            if scope_code == "ads_enterprise"
            else {"field_terms": {}, "prop_codes": {}, "value_terms_by_prop": {}}
        ),
    )

    captured: dict[str, object] = {}

    def _fake_store_clarification_results(clarification_results, user_id):
        captured["clarification_results"] = clarification_results
        captured["user_id"] = user_id
        return ["name-1"]

    monkeypatch.setattr(
        "datacloud_knowledge.intent.clarification.postprocess.store_clarification_results",
        _fake_store_clarification_results,
    )

    created_ids = persist_confirmed_synonyms(
        paradigm_list=[
            {
                "paradigmResult": [
                    {
                        "keyword": "营收",
                        "choiceKeyword": "企业总营收（万元）",
                    },
                ]
            }
        ],
        ontology_code="ads_enterprise",
        user_id="user-1",
    )

    assert created_ids == ["name-1"]
    assert captured["user_id"] == "user-1"
    assert captured["clarification_results"] == {"营收": {"term_id": "term-1"}}


def test_persist_confirmed_synonyms_handles_predicate_field_and_value(monkeypatch) -> None:
    monkeypatch.setattr(
        "datacloud_knowledge.intent.clarification.postprocess._load_scope_term_maps",
        lambda scope_code: (
            {
                "field_terms": {"区域": "prop-1"},
                "prop_codes": {"区域": "prop-1"},
                "value_terms_by_prop": {"prop-1": {"华东区": "value-1"}},
            }
            if scope_code == "ads_enterprise"
            else {"field_terms": {}, "prop_codes": {}, "value_terms_by_prop": {}}
        ),
    )

    captured: dict[str, object] = {}

    def _fake_store_clarification_results(clarification_results, user_id):
        captured["clarification_results"] = clarification_results
        captured["user_id"] = user_id
        return ["name-field", "name-value"]

    monkeypatch.setattr(
        "datacloud_knowledge.intent.clarification.postprocess.store_clarification_results",
        _fake_store_clarification_results,
    )

    created_ids = persist_confirmed_synonyms(
        paradigm_list=[
            {
                "paradigmResult": [
                    {
                        "type": "predicate",
                        "field": "大区",
                        "choiceField": "区域",
                        "value": "华东大区",
                        "choiceValue": "华东区",
                    }
                ]
            }
        ],
        ontology_code="ads_enterprise",
        user_id="user-1",
    )

    assert created_ids == ["name-field", "name-value"]
    assert captured["user_id"] == "user-1"
    assert captured["clarification_results"] == {
        "大区": {"term_id": "prop-1"},
        "华东大区": {"term_id": "value-1"},
    }
