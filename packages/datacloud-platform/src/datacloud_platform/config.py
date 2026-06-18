"""Global configuration — re-exports from datacloud-server."""

from __future__ import annotations

try:
    from datacloud_server.config import get_settings
except ImportError:

    def get_settings() -> object:
        """Fallback settings when datacloud-server is not installed."""
        raise RuntimeError("datacloud-server is not installed; cannot resolve settings")


__all__ = ["get_settings"]
