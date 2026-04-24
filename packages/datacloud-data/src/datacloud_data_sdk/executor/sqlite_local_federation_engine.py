"""SQLite 本地联邦执行引擎。"""

from __future__ import annotations

import sqlite3
import tempfile
from decimal import Decimal
from os import close as os_close
from pathlib import Path

from datacloud_data_sdk.executor.local_federation_engine import (
    BaseLocalFederationEngine,
    LocalFederationRuntime,
    LocalFederationTable,
)
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
from datacloud_data_sdk.sql_executor.models import DataSourceConfig

_LOCAL_SQLITE_ALIAS = "__federated_view_sqlite__"


def _normalize_sqlite_value(value: object) -> object:
    """将 SQLite 不直接支持的值转换为可绑定类型。"""
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


class SQLiteFederationRuntime(LocalFederationRuntime):
    """SQLite 联邦运行时句柄。"""

    def __init__(
        self,
        datasource_alias: str,
        datasource_manager: DataSourceManager,
        db_path: Path,
    ) -> None:
        super().__init__(datasource_alias=datasource_alias, datasource_manager=datasource_manager)
        self._db_path = db_path

    async def close(self) -> None:
        """关闭本地 SQLite 运行时。"""
        await self.datasource_manager.close_all()
        self._db_path.unlink(missing_ok=True)


class SQLiteLocalFederationEngine(BaseLocalFederationEngine):
    """基于 SQLite 文件库的本地联邦执行引擎。"""

    def materialize_tables(
        self,
        tables: dict[str, LocalFederationTable],
    ) -> LocalFederationRuntime:
        """将联邦临时表加载到本地 SQLite 文件库。"""
        fd, temp_name = tempfile.mkstemp(suffix=".sqlite3")
        os_close(fd)
        db_path = Path(temp_name)
        self._load_tables(db_path, tables)

        datasource_manager = DataSourceManager(
            {
                _LOCAL_SQLITE_ALIAS: DataSourceConfig(
                    alias=_LOCAL_SQLITE_ALIAS,
                    db_type="SQLITE",
                    jdbc_url=f"jdbc:sqlite:{db_path}",
                )
            }
        )
        return SQLiteFederationRuntime(_LOCAL_SQLITE_ALIAS, datasource_manager, db_path)

    def _load_tables(self, db_path: Path, tables: dict[str, LocalFederationTable]) -> None:
        """将临时表载荷写入 SQLite。"""
        conn = sqlite3.connect(db_path)
        try:
            for table_name, payload in tables.items():
                if not payload.columns:
                    raise ValueError(f"Table {table_name} missing schema for federated execution")

                column_defs = ", ".join(
                    f'"{column}" {payload.column_types.get(column, "TEXT")}'
                    for column in payload.columns
                )
                conn.execute(f'CREATE TABLE "{table_name}" ({column_defs})')
                if not payload.rows:
                    continue

                placeholders = ", ".join("?" for _ in payload.columns)
                insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders})'
                for row in payload.rows:
                    values = [
                        _normalize_sqlite_value(row.get(column)) for column in payload.columns
                    ]
                    conn.execute(insert_sql, values)
            conn.commit()
        finally:
            conn.close()
