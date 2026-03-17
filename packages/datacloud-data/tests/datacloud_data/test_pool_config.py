"""单元测试：验证 MySQLConnector 和 PostgreSQLConnector 正确传递 pool 参数给 create_async_engine。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from datacloud_data.sql_executor.models import DataSourceConfig


def test_mysql_connector_passes_pool_params() -> None:
    """config 含 pool_min=2, pool_max=10, pool_timeout=15，验证 create_async_engine 被调用时 pool_size=2, max_overflow=8, pool_timeout=15。"""
    with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create:
        from datacloud_data.sql_executor.connectors.mysql_connector import (
            MySQLConnector,
        )

        config = DataSourceConfig(
            alias="mysql_test",
            db_type="MYSQL",
            jdbc_url="jdbc:mysql://localhost:3306/testdb",
            user="u",
            password="p",
            pool_min=2,
            pool_max=10,
            pool_timeout=15.0,
        )
        MySQLConnector(config)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["pool_size"] == 2
        assert call_kwargs["max_overflow"] == 8
        assert call_kwargs["pool_timeout"] == 15.0


def test_mysql_connector_pool_max_less_than_min() -> None:
    """pool_min=5, pool_max=2，验证 pool_size=5, max_overflow=0。"""
    with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create:
        from datacloud_data.sql_executor.connectors.mysql_connector import (
            MySQLConnector,
        )

        config = DataSourceConfig(
            alias="mysql_test",
            db_type="MYSQL",
            jdbc_url="jdbc:mysql://localhost:3306/testdb",
            user="u",
            password="p",
            pool_min=5,
            pool_max=2,
        )
        MySQLConnector(config)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["pool_size"] == 5
        assert call_kwargs["max_overflow"] == 0


def test_postgresql_connector_passes_pool_params() -> None:
    """pool_min=1, pool_max=5, pool_timeout=30，验证 pool_size=1, max_overflow=4, pool_timeout=30。"""
    with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create:
        from datacloud_data.sql_executor.connectors.postgresql_connector import (
            PostgreSQLConnector,
        )

        config = DataSourceConfig(
            alias="pg_test",
            db_type="POSTGRESQL",
            jdbc_url="jdbc:postgresql://localhost:5432/testdb",
            user="u",
            password="p",
            pool_min=1,
            pool_max=5,
            pool_timeout=30.0,
        )
        PostgreSQLConnector(config)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["pool_size"] == 1
        assert call_kwargs["max_overflow"] == 4
        assert call_kwargs["pool_timeout"] == 30.0
