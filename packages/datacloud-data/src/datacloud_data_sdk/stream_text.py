"""Normalize stream chunk payloads for gateways that only join str in history (e.g. by-framework)."""

from __future__ import annotations

from typing import Any

from datacloud_data_sdk.utils.json_utils import dump_json


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
            return dump_json(value)
        except (TypeError, ValueError):
            return str(value)
    return str(value)
