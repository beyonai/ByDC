"""Streaming text processing — re-exports from datacloud-data SDK."""

from __future__ import annotations

from typing import Any

try:
    from datacloud_data_sdk.stream_text import coerce_stream_chunk_text
except ImportError:

    def coerce_stream_chunk_text(value: Any) -> str:
        """Fallback: normalize stream chunk payloads to str."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)


__all__ = ["coerce_stream_chunk_text"]
