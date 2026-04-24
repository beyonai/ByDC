"""澄清模块 — StructuredQuery / StructuredCompute 的术语确认与用户澄清。

公共 API::

    from datacloud_knowledge.intent.clarification import (
        analyze_query_clarification_query,
        analyze_query_clarification_compute,
        format_clarification_query,
        format_clarification_compute,
    )
"""

from .api import (
    analyze_query_clarification_compute,
    analyze_query_clarification_query,
    format_clarification_compute,
    format_clarification_query,
)
from .postprocess import (
    apply_resolved_to_params,
    collect_terms_from_params,
    normalize_clarification_params,
    persist_confirmed_synonyms,
)

__all__ = [
    "analyze_query_clarification_compute",
    "analyze_query_clarification_query",
    "apply_resolved_to_params",
    "collect_terms_from_params",
    "format_clarification_compute",
    "format_clarification_query",
    "normalize_clarification_params",
    "persist_confirmed_synonyms",
]
