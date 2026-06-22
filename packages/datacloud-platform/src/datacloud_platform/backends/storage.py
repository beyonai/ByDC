"""StorageBackend Protocol — file upload/download and result persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datacloud_platform.models.shared import StoredFile


class StorageBackend(Protocol):
    """File upload/download and result persistence."""

    def store_result(
        self, key: str, data: bytes, *, metadata: dict[str, Any] | None = None
    ) -> str:
        """Store result file, return file_id."""
        ...

    def get_result(self, file_id: str) -> bytes:
        """Get result file by ID."""
        ...

    def delete_result(self, file_id: str) -> None:
        """Delete result file."""
        ...

    def list_results(self, prefix: str = "") -> list[StoredFile]:
        """List result files."""
        ...
