"""
数据源管理器模块

本模块提供数据源连接的管理能力，负责创建和缓存数据库连接器。
支持多种数据库类型的统一管理。

核心功能：
- 根据配置创建数据库连接器
- 连接器缓存，避免重复创建
- 统一的连接关闭接口

使用示例：
    configs = {
        "main_db": DataSourceConfig(db_type="mysql", host="localhost", ...),
        "analytics": DataSourceConfig(db_type="clickhouse", ...)
    }
    manager = DataSourceManager(configs)
    connector = manager.get_connector("main_db")
    records = await connector.execute("SELECT 1")
"""

from __future__ import annotations
from typing import Any
from datacloud_data_sdk.exceptions import DataSourceUnavailableError
from datacloud_data_sdk.sql_executor.models import DataSourceConfig
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector
from datacloud_data_sdk.sql_executor.connector_registry import ConnectorRegistry


class DataSourceManager:
    """
    数据源管理器

    管理多个数据源的连接器实例，支持按别名获取连接器。
    连接器会被缓存以提高性能。

    Attributes:
        _configs: 数据源配置字典，key 为别名
        _connectors: 已创建的连接器缓存
        _fallback_loader: 可选的 OntologyLoader，用于动态获取数据源配置

    Example:
        manager = DataSourceManager(configs)
        connector = manager.get_connector("main_db")
        await manager.close_all()
    """

    def __init__(self, configs: dict[str, DataSourceConfig], fallback_loader: Any = None) -> None:
        """
        初始化数据源管理器

        Args:
            configs: 数据源配置字典
                key: 数据源别名
                value: DataSourceConfig 配置对象
            fallback_loader: 可选的 OntologyLoader 实例，用于动态获取数据源配置
        """
        self._configs = configs
        self._connectors: dict[str, BaseSourceConnector] = {}
        self._fallback_loader = fallback_loader

    def get_connector(self, alias: str) -> BaseSourceConnector:
        """
        获取指定数据源的连接器

        如果连接器已缓存则直接返回，否则根据配置创建新连接器。
        如果本地配置中找不到，尝试从 fallback_loader 获取。

        Args:
            alias: 数据源别名

        Returns:
            BaseSourceConnector: 数据库连接器实例

        Raises:
            DataSourceUnavailableError: 数据源配置不存在时抛出
        """
        if alias in self._connectors:
            return self._connectors[alias]

        config = self._configs.get(alias)

        # 如果本地配置中没有，尝试从 fallback_loader 获取
        if config is None and self._fallback_loader is not None:
            try:
                fallback_configs = getattr(self._fallback_loader, '_config', None)
                if fallback_configs is not None:
                    datasource_configs = getattr(fallback_configs, 'datasource_configs', {})
                    config = datasource_configs.get(alias)
                    if config is not None:
                        # 缓存到本地配置中，避免重复查找
                        self._configs[alias] = config
            except Exception:
                pass

        if config is None:
            raise DataSourceUnavailableError(alias)

        connector_cls = ConnectorRegistry.get(config.db_type)
        connector = connector_cls(config)
        self._connectors[alias] = connector
        return connector

    async def close_all(self) -> None:
        """
        关闭所有连接器
        
        清理所有缓存的连接器，释放数据库连接资源。
        """
        for conn in self._connectors.values():
            await conn.close()
        self._connectors.clear()
