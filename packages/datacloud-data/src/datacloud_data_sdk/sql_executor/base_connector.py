"""
数据源连接器抽象基类模块

本模块定义了数据源连接器的抽象接口，所有具体数据库连接器
都需要继承 BaseSourceConnector 并实现其抽象方法。

支持的数据库类型：
- MySQL
- PostgreSQL
- SQLite
- OpenGauss
- ClickHouse

使用示例：
    class MySQLConnector(BaseSourceConnector):
        @classmethod
        def supported_type(cls) -> str:
            return "mysql"

        async def execute(self, sql: str, params: dict | None = None) -> list[dict]:
            # 实现具体的执行逻辑
            pass
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from datacloud_data_sdk.sql_executor.models import DataSourceConfig


class BaseSourceConnector(ABC):
    """
    数据源连接器抽象基类

    定义了所有数据库连接器必须实现的接口。
    支持异步执行和连接测试。

    Attributes:
        config: 数据源配置对象

    Example:
        connector = MySQLConnector(config)
        records = await connector.execute("SELECT * FROM users")
        is_ok = await connector.test_connection()
    """

    def __init__(self, config: DataSourceConfig) -> None:
        """
        初始化连接器

        Args:
            config: 数据源配置对象
        """
        self.config = config

    @classmethod
    @abstractmethod
    def supported_type(cls) -> str:
        """
        返回此连接器支持的数据库类型

        Returns:
            str: 数据库类型标识，如 "mysql", "postgresql"
        """
        ...

    @abstractmethod
    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        执行 SQL 查询

        Args:
            sql: SQL 查询语句
            params: 可选的查询参数

        Returns:
            list[dict]: 查询结果列表，每行为一个字典
        """
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        测试数据库连接

        Returns:
            bool: 连接成功返回 True，否则返回 False
        """
        ...

    async def close(self) -> None:
        """
        关闭连接

        子类可重写此方法以实现连接池清理等操作。
        """
        pass
