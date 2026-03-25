"""
连接器注册表模块

本模块提供数据库连接器的注册和查找机制。
支持按数据库类型动态注册和获取连接器类。

核心功能：
- 注册数据库连接器类
- 按数据库类型查找连接器
- 自动加载可用的连接器

支持的数据库类型：
- SQLITE: SQLite 数据库
- MYSQL: MySQL/Doris 数据库
- POSTGRESQL: PostgreSQL 数据库
- OPENGAUSS: openGauss 数据库
- CLICKHOUSE: ClickHouse 数据库

使用示例：
    # 注册自定义连接器
    ConnectorRegistry.register("MYDB", MyDBConnector)
    
    # 获取连接器类
    ConnectorClass = ConnectorRegistry.get("MYSQL")
"""

from __future__ import annotations
from typing import Type
from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector


class ConnectorRegistry:
    """
    连接器注册表
    
    管理数据库连接器类的注册和查找。
    使用类方法实现全局注册表模式。
    
    Example:
        # 注册连接器
        ConnectorRegistry.register("MYSQL", MySQLConnector)
        
        # 获取连接器类
        cls = ConnectorRegistry.get("MYSQL")
        connector = cls(config)
    """
    
    _registry: dict[str, Type[BaseSourceConnector]] = {}

    @classmethod
    def register(cls, db_type: str, connector_cls: Type[BaseSourceConnector]) -> None:
        """
        注册数据库连接器类
        
        Args:
            db_type: 数据库类型标识（不区分大小写）
            connector_cls: 连接器类
        """
        cls._registry[db_type.upper()] = connector_cls

    @classmethod
    def get(cls, db_type: str) -> Type[BaseSourceConnector]:
        """
        获取数据库连接器类
        
        Args:
            db_type: 数据库类型标识（不区分大小写）
        
        Returns:
            Type[BaseSourceConnector]: 连接器类
        
        Raises:
            DataSourceUnavailableError: 未找到对应连接器时抛出
        """
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
