"""StorageBackend adapter — store/get/delete/list result files."""

from __future__ import annotations

import json as _json
import logging
import uuid
from typing import Any

from datacloud_platform.adapters.data_adapter._base import DataCloudDataBackendBase
from datacloud_platform.models import StoredFile

logger = logging.getLogger(__name__)


class StorageBackendMixin(DataCloudDataBackendBase):
    """StorageBackend adapter — store/get/delete/list result files."""

    # ── StorageBackend ─────────────────────────────────────────────────────

    def store_result(
        self, key: str, data: bytes, *, metadata: dict[str, Any] | None = None
    ) -> str:
        """Store result file bytes, returning a unique file_id.

        Args:
            key: Human-readable file key / name.
            data: Raw bytes to persist.
            metadata: Optional metadata dict (stored as a JSON sidecar).

        Returns:
            A UUID-based file_id for retrieval.
        """
        file_id = uuid.uuid4().hex
        store_dir = self._storage_dir()
        store_dir.mkdir(parents=True, exist_ok=True)

        data_path = store_dir / file_id
        data_path.write_bytes(data)

        if metadata:
            meta_path = store_dir / f"{file_id}.meta"
            meta_path.write_text(
                _json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
            )

        logger.info("Stored result file_id=%s key=%s size=%d", file_id, key, len(data))
        return file_id

    def get_result(self, file_id: str) -> bytes:
        """Get result file bytes by ID.

        Args:
            file_id: The file identifier returned by :meth:`store_result`.

        Returns:
            Raw bytes of the stored file.

        Raises:
            FileNotFoundError: If the file_id does not exist.
        """
        data_path = self._storage_dir() / file_id
        if not data_path.exists():
            raise FileNotFoundError(f"Result file not found: {file_id}")
        return data_path.read_bytes()

    def delete_result(self, file_id: str) -> None:
        """Delete a result file by ID.

        Args:
            file_id: The file identifier to delete.
        """
        data_path = self._storage_dir() / file_id
        meta_path = self._storage_dir() / f"{file_id}.meta"
        if data_path.exists():
            data_path.unlink()
        if meta_path.exists():
            meta_path.unlink()
        logger.info("Deleted result file_id=%s", file_id)

    def list_results(self, prefix: str = "") -> list[StoredFile]:
        """List stored result files, optionally filtered by prefix.

        Args:
            prefix: Optional key prefix filter.

        Returns:
            List of StoredFile summaries.
        """
        store_dir = self._storage_dir()
        if not store_dir.exists():
            return []

        files: list[StoredFile] = []
        for entry in sorted(store_dir.iterdir()):
            if entry.is_dir() or entry.suffix == ".meta":
                continue
            fid = entry.name
            if prefix and not fid.startswith(prefix):
                continue
            stat = entry.stat()
            files.append(
                StoredFile(
                    file_id=fid,
                    key=fid,
                    size_bytes=stat.st_size,
                    created_at=str(stat.st_ctime),
                )
            )
        return files
