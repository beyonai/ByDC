"""DataSourceManager: 数据源连接管理。"""

from __future__ import annotations
from typing import Any
from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.sql_executor.models import DataSourceConfig
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector
from datacloud_data_sdk.sql_executor.connector_registry import ConnectorRegistry


class DataSourceManager:
    def __init__(self, configs: dict[str, DataSourceConfig]) -> None:
        self._configs = configs
        self._connectors: dict[str, BaseSourceConnector] = {}

    def get_connector(self, alias: str) -> BaseSourceConnector:
        if alias in self._connectors:
            return self._connectors[alias]
        config = self._configs.get(alias)
        if config is None:
            raise DataSourceUnavailableError(alias)
        connector_cls = ConnectorRegistry.get(config.db_type)
        connector = connector_cls(config)
        self._connectors[alias] = connector
        return connector

    async def close_all(self) -> None:
        for conn in self._connectors.values():
            await conn.close()
        self._connectors.clear()
