"""连接器注册表：按 db_type 查找连接器类。"""

from __future__ import annotations
from typing import Type
from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector


class ConnectorRegistry:
    _registry: dict[str, Type[BaseSourceConnector]] = {}

    @classmethod
    def register(cls, db_type: str, connector_cls: Type[BaseSourceConnector]) -> None:
        cls._registry[db_type.upper()] = connector_cls

    @classmethod
    def get(cls, db_type: str) -> Type[BaseSourceConnector]:
        connector_cls = cls._registry.get(db_type.upper())
        if connector_cls is None:
            raise DataSourceUnavailableError(db_type)
        return connector_cls


from datacloud_data_sdk.sql_executor.connectors.sqlite_connector import SQLiteConnector

ConnectorRegistry.register("SQLITE", SQLiteConnector)

try:
    from datacloud_data_sdk.sql_executor.connectors.mysql_connector import MySQLConnector

    ConnectorRegistry.register("MYSQL", MySQLConnector)
    ConnectorRegistry.register("DORIS", MySQLConnector)
except ImportError:
    pass

try:
    from datacloud_data_sdk.sql_executor.connectors.postgresql_connector import (
        PostgreSQLConnector,
    )

    ConnectorRegistry.register("POSTGRESQL", PostgreSQLConnector)
except ImportError:
    pass

try:
    from datacloud_data_sdk.sql_executor.connectors.opengauss_connector import (
        OpenGaussConnector,
    )

    ConnectorRegistry.register("OPENGAUSS", OpenGaussConnector)
except ImportError:
    pass

try:
    from datacloud_data_sdk.sql_executor.connectors.clickhouse_connector import (
        ClickHouseConnector,
    )

    ConnectorRegistry.register("CLICKHOUSE", ClickHouseConnector)
except ImportError:
    pass
