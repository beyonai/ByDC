"""Backend contract for ByClaw BE operational APIs."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from datacloud_platform.models.document import DocumentTaskStatus


class ByClawBeServiceError(RuntimeError):
    """Raised when a ByClaw BE operation request fails."""


@runtime_checkable
class ByClawBeServiceBackend(Protocol):
    """Operations exposed by the ByClaw BE service."""

    async def save_or_update_object_files(
        self, *, object_files: list[dict[str, Any]]
    ) -> None: ...

    async def update_task_status(
        self, *, session_id: str, task_status: DocumentTaskStatus
    ) -> None: ...
