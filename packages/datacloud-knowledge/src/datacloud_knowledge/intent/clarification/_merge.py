"""Result merging — re-exports from merge/ subpackage.

This file is a backward-compatibility shim. New code should import from
``datacloud_knowledge.intent.clarification.merge`` directly.
"""

from .merge._cc_normalize import (
    _dedupe_condition_term_mappings,
    merge_cc_resolution_hints,
    normalize_cc_result_with_hints,
)
from .merge._hints import (
    _recall_fallback_candidates,
    _TermResolutionHint,
    build_main_resolution_hints,
    merge_pre_resolve_hints,
)
from .merge._llm_confirm import (
    _MergeConfirmed,
    merge_confirmed_common,
    merge_to_confirmed_compute,
    merge_to_confirmed_query,
)
from .merge._pre_resolve import apply_pre_resolve_results

__all__ = [
    "_MergeConfirmed",
    "_TermResolutionHint",
    "_dedupe_condition_term_mappings",
    "_recall_fallback_candidates",
    "apply_pre_resolve_results",
    "build_main_resolution_hints",
    "merge_cc_resolution_hints",
    "merge_confirmed_common",
    "merge_pre_resolve_hints",
    "merge_to_confirmed_compute",
    "merge_to_confirmed_query",
    "normalize_cc_result_with_hints",
]
