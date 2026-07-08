"""Dependency injection — Platform provisioning for API route factories.

With the factory-router pattern, the Platform instance is injected via
closure capture in each ``create_*_routes(platform)`` factory — no global singleton needed.
This module provides convenience helpers for cases that still need global access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

from datacloud_platform.adapters.byclaw_sync import hook_ctx

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


def extract_beyond_token(request: Request) -> None:
    """FastAPI Depends: extract ``Beyond-Token`` header and inject into hook_ctx.

    Called automatically for every RPC handler via ``Depends()``.
    Handler code never needs to touch this header directly.
    """
    token: str | None = request.headers.get("Beyond-Token")
    if token:
        hook_ctx.set({"beyond_token": token})
