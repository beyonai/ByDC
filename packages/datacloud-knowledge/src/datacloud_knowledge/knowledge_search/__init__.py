from __future__ import annotations

from .owl_relation_resolver import resolve_related_owl_terms
from .term_search import (
    get_object_props,
    get_prop_values_with_aliases,
    get_term_ids,
    get_term_names,
    search_terms_by_type,
)

__all__ = [
    "get_object_props",
    "get_prop_values_with_aliases",
    "get_term_ids",
    "get_term_names",
    "resolve_related_owl_terms",
    "search_terms_by_type",
]
