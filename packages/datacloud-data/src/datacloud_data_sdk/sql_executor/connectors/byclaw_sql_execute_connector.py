"""ByClaw sqlExecute connector backed by file-based SQLite."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from typing import Any

from datacloud_data_sdk.exceptions import SqlExecutionError
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector
from datacloud_data_sdk.sql_executor.models import DataSourceConfig

DEFAULT_MOUNT_PATH = None  # type: ignore[reportGeneralTypeIssues]
_MOUNT_PATH: str | None = DEFAULT_MOUNT_PATH

FIXED_DB_NAME = "personal_object.db"


class ByclawSqlExecuteConnector(BaseSourceConnector):
    """Execute SQL against a shared file-based SQLite database.

    Database path: {mount_path}/byclaw-datacloud/personal_object.db
    where mount_path defaults to .

    All callers share the same single database file.
    """

    def __init__(
        self,
        config: DataSourceConfig,
    ) -> None:
        super().__init__(config)
        db_path = self._resolve_db_path(config)
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._execute_lock = asyncio.Lock()

    @classmethod
    def supported_type(cls) -> str:
        return "BYCLAW_SQL_EXECUTE"

    @classmethod
    def configure_mount_path(cls, mount_path: str | None) -> None:
        """Override the default FILE_STORAGE_MINIO_MOUNT_PATH mount point."""
        global _MOUNT_PATH
        _MOUNT_PATH = mount_path

    def _resolve_db_path(self, config: DataSourceConfig) -> str:
        mount = (
            _MOUNT_PATH
            if _MOUNT_PATH is not DEFAULT_MOUNT_PATH
            else os.environ.get("FILE_STORAGE_MINIO_MOUNT_PATH", "")
        )
        if not mount:
            raise SqlExecutionError(
                config.alias,
                "",
                "FILE_STORAGE_MINIO_MOUNT_PATH is required",
            )
        return os.path.join(mount, "byclaw-datacloud", FIXED_DB_NAME)

    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        async with self._execute_lock:
            cursor = self._conn.execute(sql, params or [])
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            self._conn.commit()
            return [dict(zip(columns, row)) for row in rows]

    async def test_connection(self) -> bool:
        try:
            self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        self._conn.close()
