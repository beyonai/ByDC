from __future__ import annotations

from .owl_relation_resolver import resolve_related_owl_terms
from .term_search import (
    get_object_props,
    get_prop_values_with_aliases,
    get_term_ids,
    get_term_names,
    resolve_field_aliases,
    resolve_value_aliases,
    search_terms_by_type,
)
from .types import AmbiguousCandidate, FieldResolutionResult, ValueResolutionResult

__all__ = [
    "AmbiguousCandidate",
    "FieldResolutionResult",
    "ValueResolutionResult",
    "get_object_props",
    "get_prop_values_with_aliases",
    "get_term_ids",
    "get_term_names",
    "resolve_field_aliases",
    "resolve_related_owl_terms",
    "resolve_value_aliases",
    "search_terms_by_type",
]
