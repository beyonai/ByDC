"""Shared row-count rules aligned with :func:`insight.build_structured_data_envelope`.

Why this module exists
----------------------
``[tool return]`` and ``[user SSE 6001]`` must use the **same** definition of
“how many rows feed the 6001 payload”, so logs can be reconciled without
copy-pasting logic into ``sandbox_executor``.
"""

from __future__ import annotations

from typing import Any


def count_rows_like_envelope_build(output: dict[str, Any]) -> int | None:
    """Return row count that :func:`build_structured_data_envelope` would merge from ``output``.

    Mirrors ``insight._records_shaped_output``:
    - ``records`` + ``meta`` → len(records)
    - ``preview`` + ``columns`` → len(preview)
    - else → None (not query-shaped for 6001)
    """
    if not isinstance(output, dict):
        return None
    if "records" in output and "meta" in output:
        recs = output.get("records")
        return len(recs) if isinstance(recs, list) else None
    if "preview" in output and "columns" in output:
        prev = output.get("preview", [])
        return len(prev) if isinstance(prev, list) else None
    return None
