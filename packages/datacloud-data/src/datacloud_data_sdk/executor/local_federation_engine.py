"""本地联邦执行引擎抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager


@dataclass(frozen=True)
class LocalFederationTable:
    """本地联邦表载荷。"""

    columns: list[str]
    rows: list[dict[str, Any]]
    column_types: dict[str, str]


@dataclass
class LocalFederationRuntime:
    """本地联邦运行时句柄。"""

    datasource_alias: str
    datasource_manager: DataSourceManager

    async def close(self) -> None:
        """释放运行时资源。"""


class BaseLocalFederationEngine(ABC):
    """本地联邦引擎基类。"""

    @abstractmethod
    def materialize_tables(
        self,
        tables: dict[str, LocalFederationTable],
    ) -> LocalFederationRuntime:
        """将联邦临时表加载到本地引擎。"""


def create_local_federation_engine(config: Any | None = None) -> BaseLocalFederationEngine:
    """按配置创建本地联邦引擎。"""
    engine_name = str(getattr(config, "local_federation_engine", "SQLITE") or "SQLITE").upper()
    if engine_name == "SQLITE":
        from datacloud_data_sdk.executor.sqlite_local_federation_engine import (
            SQLiteLocalFederationEngine,
        )

        return SQLiteLocalFederationEngine()
    raise ValueError(f"Unsupported local federation engine: {engine_name}")
