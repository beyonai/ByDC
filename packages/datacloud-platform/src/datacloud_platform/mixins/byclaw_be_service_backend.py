"""Platform routing layer for ByClawBeServiceBackend operations."""

from __future__ import annotations

from typing import Any

from datacloud_platform.backends._contracts import _HasByClawBeServiceBackend


class ByClawBeServiceBackendMixin:
    async def save_or_update_object_files(
        self: _HasByClawBeServiceBackend,
        base_id: str,
        *,
        object_files: list[dict[str, Any]],
    ) -> None:
        await self._byclaw_be_service_for(base_id).save_or_update_object_files(
            object_files=object_files
        )
