"""Dependency injection — Platform provisioning for API route factories.

With the factory-router pattern, the Platform instance is injected via
closure capture in each ``create_*_routes(platform)`` factory — no global singleton needed.
This module provides convenience helpers for cases that still need global access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_platform import DatacloudPlatform

_platform: DatacloudPlatform | None = None


def set_platform(p: DatacloudPlatform) -> None:
    """Register the Platform instance (optional, for compatibility)."""
    global _platform  # noqa: PLW0603
    _platform = p


def get_platform() -> DatacloudPlatform:
    """Retrieve the registered Platform instance.

    Raises:
        RuntimeError: If no Platform has been set.
    """
    if _platform is None:
        raise RuntimeError("Platform not set. Call set_platform() first.")
    return _platform
