"""Platform routing layer for ByClawBeServiceBackend operations."""

from __future__ import annotations

from typing import Any

from datacloud_platform.backends._contracts import _HasByClawBeServiceBackend
from datacloud_platform.models.document import DocumentTaskStatus


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

    async def update_task_status(
        self: _HasByClawBeServiceBackend,
        base_id: str,
        *,
        session_id: str,
        task_status: DocumentTaskStatus,
    ) -> None:
        await self._byclaw_be_service_for(base_id).update_task_status(
            session_id=session_id,
            task_status=task_status,
        )
