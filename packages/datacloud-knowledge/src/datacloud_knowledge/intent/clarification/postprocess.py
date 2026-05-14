"""Post-processing helpers for confirmed clarification results."""

from __future__ import annotations

import logging
import re
from typing import Any

from datacloud_knowledge.adapters import create_reader, store_clarification_results

logger = logging.getLogger(__name__)

_FIELD_CODE_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SORT_KEY_ALIASES: frozenset[str] = frozenset({"sort", "op", "order"})


def normalize_clarification_params(
    params: dict[str, Any],
    *,
    ontology_code: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Normalize confirmed clarification params to canonical English field codes."""
    field_terms, _ = collect_terms_from_params(params)
    result = create_reader().resolve_field_aliases(terms=field_terms, scope_code=ontology_code)
    patched = apply_resolved_to_params(params, result.resolved)
    scope_maps = _load_scope_term_maps(ontology_code)
    return _normalize_filter_values(patched, scope_maps)


def persist_confirmed_synonyms(
    *,
    paradigm_list: list[dict[str, Any]],
    ontology_code: str,
    user_id: str | None,
) -> list[str]:
    """Persist user-confirmed aliases so later lightweight alias resolution can reuse them."""
    normalized_user_id = (user_id or "").strip()
    if not normalized_user_id or not paradigm_list or not ontology_code:
        return []

    scope_maps = _load_scope_term_maps(ontology_code)
    if not scope_maps["field_terms"]:
        logger.info(
            "[clarification.postprocess] skip synonym persistence: no props for scope=%s",
            ontology_code,
        )
        return []

    clarification_results: dict[str, dict[str, str]] = {}
    for paradigm in paradigm_list:
        for result in paradigm.get("paradigmResult") or []:
            clarification_results.update(_build_synonym_payload(result, scope_maps))

    if not clarification_results:
        return []

    created_ids = store_clarification_results(clarification_results, normalized_user_id)
    logger.info(
        "[clarification.postprocess] persisted confirmed synonyms: scope=%s user_id=%s count=%d",
        ontology_code,
        normalized_user_id,
        len(created_ids),
    )
    return created_ids


def _load_scope_term_maps(scope_code: str) -> dict[str, Any]:
    """Load field/prop/value maps for a scope_code using reader adapter."""
    if not scope_code:
        return {"field_terms": {}, "prop_codes": {}, "value_terms_by_prop": {}}

    reader = create_reader()
    source_term_ids = list(reader.get_scope_term_ids(scope_code=scope_code))
    if not source_term_ids:
        return {"field_terms": {}, "prop_codes": {}, "value_terms_by_prop": {}}

    field_terms: dict[str, str] = {}
    prop_codes: dict[str, str] = {}
    prop_value_codes: dict[str, dict[str, str]] = {}
    reader = create_reader()
    for props in reader.get_object_props(source_term_ids=source_term_ids).values():
        for prop in props:
            field_terms.setdefault(prop.term_name, prop.term_id)
            field_terms.setdefault(prop.term_code, prop.term_id)
            prop_codes.setdefault(prop.term_name, prop.term_id)
            prop_codes.setdefault(prop.term_code, prop.term_id)

    value_terms_by_prop: dict[str, dict[str, str]] = {}
    for values in reader.get_prop_values_with_aliases(source_term_ids=source_term_ids).values():
        for value in values:
            prop_values = value_terms_by_prop.setdefault(value.parent_term_id, {})
            prop_values.setdefault(value.term_name, value.term_id)
            prop_values.setdefault(value.term_code, value.term_id)
            prop_codes_map = prop_value_codes.setdefault(value.parent_term_id, {})
            prop_codes_map.setdefault(value.term_name, value.term_code)
            prop_codes_map.setdefault(value.term_code, value.term_code)
            for alias in value.aliases:
                prop_values.setdefault(alias, value.term_id)
                prop_codes_map.setdefault(alias, value.term_code)
    return {
        "field_terms": field_terms,
        "prop_codes": prop_codes,
        "value_terms_by_prop": value_terms_by_prop,
        "prop_value_codes": prop_value_codes,
    }


def _build_synonym_payload(
    result: dict[str, Any],
    scope_maps: dict[str, Any],
) -> dict[str, dict[str, str]]:
    if str(result.get("type") or "") == "predicate":
        return _build_predicate_synonym_payload(result, scope_maps)

    keyword = str(result.get("keyword") or "").strip()
    choice_keyword = str(result.get("choiceKeyword") or "").strip()
    if not keyword or not choice_keyword or keyword == choice_keyword:
        return {}

    field_terms = scope_maps.get("field_terms") or {}
    term_id = field_terms.get(choice_keyword)
    if term_id is None:
        return {}
    return {keyword: {"term_id": term_id}}


def _build_predicate_synonym_payload(
    result: dict[str, Any],
    scope_maps: dict[str, Any],
) -> dict[str, dict[str, str]]:
    payload: dict[str, dict[str, str]] = {}
    raw_field = str(result.get("field") or "").strip()
    choice_field = str(result.get("choiceField") or "").strip()
    raw_value = str(result.get("value") or "").strip()
    choice_value = str(result.get("choiceValue") or "").strip()

    field_terms = scope_maps.get("field_terms") or {}
    prop_codes = scope_maps.get("prop_codes") or {}
    value_terms_by_prop = scope_maps.get("value_terms_by_prop") or {}

    prop_term_id = prop_codes.get(choice_field)
    if raw_field and choice_field and raw_field != choice_field:
        field_term_id = field_terms.get(choice_field)
        if field_term_id is not None:
            payload[raw_field] = {"term_id": field_term_id}

    if raw_value and choice_value and raw_value != choice_value and prop_term_id is not None:
        prop_values = value_terms_by_prop.get(prop_term_id) or {}
        value_term_id = prop_values.get(choice_value)
        if value_term_id is not None:
            payload[raw_value] = {"term_id": value_term_id}
    return payload


def _is_field_code(term: str) -> bool:
    return bool(_FIELD_CODE_RE.match(term))


def collect_terms_from_params(tool_params: dict[str, Any]) -> tuple[list[str], list[str]]:
    def _get_field_term(item: dict[str, Any]) -> str | None:
        raw = item.get("field_name_cn") or item.get("field")
        if not raw:
            return None
        text = str(raw)
        return None if _is_field_code(text) else text

    field_terms: list[str] = []
    value_terms: list[str] = []

    for filter_item in tool_params.get("filters") or []:
        if isinstance(filter_item, dict):
            field_term = _get_field_term(filter_item)
            if field_term:
                field_terms.append(field_term)
            raw_value = filter_item.get("value")
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            for value in values:
                text = str(value or "").strip()
                if text and not _is_field_code(text):
                    value_terms.append(text)
    for select_item in tool_params.get("select") or []:
        if select_item and not _is_field_code(str(select_item)):
            field_terms.append(str(select_item))
    for key in ("dimensions", "metrics", "order_by", "having"):
        for item in tool_params.get(key) or []:
            if isinstance(item, dict):
                field_term = _get_field_term(item)
                if field_term:
                    field_terms.append(field_term)
            elif key == "dimensions" and item and not _is_field_code(str(item)):
                field_terms.append(str(item))
    return field_terms, value_terms


def _normalize_sort_key(item: dict[str, Any]) -> dict[str, Any]:
    alias_keys = _SORT_KEY_ALIASES & item.keys()
    if not alias_keys:
        return item
    new_item = {k: v for k, v in item.items() if k not in _SORT_KEY_ALIASES}
    if "direction" not in new_item:
        new_item["direction"] = next(item[k] for k in _SORT_KEY_ALIASES if k in item)
    return new_item


def _normalize_dim_group_op(dim: dict[str, Any]) -> dict[str, Any]:
    """Normalize LLM grouping aliases to the executor protocol without defaults."""
    new_dim = dict(dim)
    if "group_op" not in new_dim:
        for alias_key in ("granularity", "level"):
            if alias_key in new_dim:
                new_dim["group_op"] = new_dim[alias_key]
                break
    new_dim.pop("granularity", None)
    new_dim.pop("level", None)
    return new_dim


def apply_resolved_to_params(
    tool_params: dict[str, Any],
    resolved: dict[str, str],
) -> dict[str, Any]:
    patched = dict(tool_params)

    def _map(term: str) -> str:
        return resolved.get(term, term)

    def _translate_field(item: dict[str, Any]) -> dict[str, Any]:
        raw = item.get("field_name_cn") or item.get("field")
        if not raw:
            return item
        text = str(raw)
        resolved_code = text if _is_field_code(text) else _map(text)
        new_item = {k: v for k, v in item.items() if k not in ("field_name_cn", "field")}
        new_item["field"] = resolved_code
        return new_item

    patched["filters"] = [
        _translate_field(filter_item) if isinstance(filter_item, dict) else filter_item
        for filter_item in patched.get("filters") or []
    ]
    patched["select"] = [
        select_item if _is_field_code(str(select_item)) else _map(str(select_item))
        for select_item in patched.get("select") or []
    ]
    if "dimensions" in tool_params:
        patched["dimensions"] = [
            _normalize_dim_group_op(_translate_field(item))
            if isinstance(item, dict)
            else item
            if _is_field_code(str(item))
            else _map(str(item))
            for item in patched.get("dimensions") or []
        ]
    if "metrics" in tool_params:
        patched["metrics"] = [
            _translate_field(item) if isinstance(item, dict) else item
            for item in patched.get("metrics") or []
        ]
    patched["order_by"] = [
        _normalize_sort_key(_translate_field(item)) if isinstance(item, dict) else item
        for item in patched.get("order_by") or []
    ]
    if "having" in tool_params:
        patched["having"] = [
            _translate_field(item) if isinstance(item, dict) else item
            for item in patched.get("having") or []
        ]
    return patched


def _normalize_filter_values(
    tool_params: dict[str, Any],
    scope_maps: dict[str, Any],
) -> dict[str, Any]:
    patched = dict(tool_params)
    prop_codes = scope_maps.get("prop_codes") or {}
    prop_value_codes = scope_maps.get("prop_value_codes") or {}
    normalized_filters: list[Any] = []

    for filter_item in patched.get("filters") or []:
        if not isinstance(filter_item, dict):
            normalized_filters.append(filter_item)
            continue
        field_code = str(filter_item.get("field") or "").strip()
        prop_term_id = prop_codes.get(field_code)
        if not field_code or prop_term_id is None:
            normalized_filters.append(filter_item)
            continue
        value_code_map = prop_value_codes.get(prop_term_id) or {}
        raw_value = filter_item.get("value")
        if isinstance(raw_value, list):
            normalized_value = [value_code_map.get(str(v), str(v)) for v in raw_value]
        elif raw_value is None:
            normalized_value = raw_value
        else:
            normalized_value = value_code_map.get(str(raw_value), raw_value)
        normalized_filters.append({**filter_item, "value": normalized_value})

    patched["filters"] = normalized_filters
    return patched
