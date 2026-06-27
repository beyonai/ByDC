"""StorageMixin — file / result persistence operations."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.backends._contracts import _HasStorageBackend

logger = logging.getLogger(__name__)


class StorageMixin:
    """Mixin for storage-backend-routed operations: store, get, delete results."""

    def store_result(
        self: _HasStorageBackend,
        base_id: str,
        key: str,
        data: bytes,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a result file; returns file_id.

        Raises:
            PermissionError: If storage is ``"none"`` for this base.
        """
        backend = self._storage_for(base_id)
        if backend is None:
            raise PermissionError(f"Storage not available for base '{base_id}'")
        return backend.store_result(key, data, metadata=metadata)

    def get_result(self: _HasStorageBackend, base_id: str, file_id: str) -> bytes:
        """Retrieve a stored result file.

        Raises:
            PermissionError: If storage is ``"none"`` for this base.
        """
        backend = self._storage_for(base_id)
        if backend is None:
            raise PermissionError(f"Storage not available for base '{base_id}'")
        return backend.get_result(file_id)

    def delete_result(self: _HasStorageBackend, base_id: str, file_id: str) -> None:
        """Delete a stored result file.

        Raises:
            PermissionError: If storage is ``"none"`` for this base.
        """
        backend = self._storage_for(base_id)
        if backend is None:
            raise PermissionError(f"Storage not available for base '{base_id}'")
        backend.delete_result(file_id)
