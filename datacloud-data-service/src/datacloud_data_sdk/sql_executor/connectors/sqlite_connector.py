"""SQLite 连接器（内存/文件）。"""
from __future__ import annotations
import sqlite3
from typing import Any
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector
from datacloud_data_sdk.sql_executor.models import DataSourceConfig


class SQLiteConnector(BaseSourceConnector):
    def __init__(self, config: DataSourceConfig) -> None:
        super().__init__(config)
        db_path = config.jdbc_url.replace("jdbc:sqlite:", "")
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row

    @classmethod
    def supported_type(cls) -> str:
        return "SQLITE"

    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        cursor = self._conn.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    async def test_connection(self) -> bool:
        try:
            self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        self._conn.close()
