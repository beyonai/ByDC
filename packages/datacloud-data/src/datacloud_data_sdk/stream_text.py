"""Normalize stream chunk payloads for gateways that only join str in history (e.g. by-framework)."""

from __future__ import annotations

import json
from typing import Any


def coerce_stream_chunk_text(value: Any) -> str:
    """Return a string safe for ``StreamChunkEvent(content=...)`` / history ``join``.

    by-framework ``flush_to_history`` does ``"".join(_response_buffer)``; non-str elements
    (e.g. multimodal dict blocks) raise TypeError. Callers should pass output through this.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)
    return str(value)
