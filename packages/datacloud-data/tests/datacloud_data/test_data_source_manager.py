"""DataSourceManager 选型规则测试（chatbi 对接方案）。

覆盖：
1. ``loader.sql_execute_url`` 非空时强制走 HTTP_SQL，且把 URL 注入 connector
2. 注入是基于 dataclasses.replace 的副本，不污染原 config
3. ``sql_execute_url`` 与 ``datasource_id`` 都为空时仍按 db_type 走本地 connector
4. 仅 ``datasource_id`` 非空（兼容历史路径）时仍走 HTTP_SQL
"""

from __future__ import annotations

from typing import Any

import pytest
from datacloud_data_sdk.sql_executor.connectors.http_sql_connector import HttpSqlConnector
from datacloud_data_sdk.sql_executor.data_source_manager import (
    DataSourceManager,
    _LoggingConnectorProxy,
)
from datacloud_data_sdk.sql_executor.models import DataSourceConfig


class _FakeLoader:
    """duck-typed loader stub，仅暴露 DataSourceManager 需要的属性。"""

    def __init__(self, *, sql_execute_url: str | None = None) -> None:
        self._sql_execute_url = sql_execute_url

    @property
    def sql_execute_url(self) -> str | None:
        return self._sql_execute_url


def _unwrap(connector: Any) -> Any:
    """剥掉 _LoggingConnectorProxy。"""
    if isinstance(connector, _LoggingConnectorProxy):
        return connector._real  # type: ignore[attr-defined]
    return connector


def test_sql_execute_url_forces_http_connector_and_injects_endpoint_url() -> None:
    config = DataSourceConfig(
        alias="local_mysql",
        db_type="MYSQL",  # 即使是 MYSQL，sql_execute_url 也应强制走 HTTP_SQL
        datasource_id=12345,  # 必须有 datasource_id 否则 HttpSqlConnector.execute 会失败
    )
    loader = _FakeLoader(sql_execute_url="http://chatbi.example/api/sql")
    manager = DataSourceManager({"local_mysql": config}, fallback_loader=loader)

    connector = _unwrap(manager.get_connector("local_mysql"))
    assert isinstance(connector, HttpSqlConnector)
    assert connector.config.endpoint_url == "http://chatbi.example/api/sql"


def test_sql_execute_url_injection_does_not_mutate_original_config() -> None:
    config = DataSourceConfig(
        alias="local_mysql",
        db_type="MYSQL",
        datasource_id=12345,
        endpoint_url="",  # 原始为空
    )
    loader = _FakeLoader(sql_execute_url="http://chatbi.example/api/sql")
    manager = DataSourceManager({"local_mysql": config}, fallback_loader=loader)

    manager.get_connector("local_mysql")
    # 原 config 不应被修改
    assert config.endpoint_url == ""


def test_no_sql_execute_url_no_datasource_id_uses_db_type_connector() -> None:
    config = DataSourceConfig(alias="sqlite_db", db_type="SQLITE")
    loader = _FakeLoader(sql_execute_url=None)
    manager = DataSourceManager({"sqlite_db": config}, fallback_loader=loader)

    connector = _unwrap(manager.get_connector("sqlite_db"))
    # SQLite connector 类型校验，不严格断类，只验证不是 HttpSqlConnector
    assert not isinstance(connector, HttpSqlConnector)


def test_datasource_id_only_still_forces_http_connector() -> None:
    """兼容旧路径：未传 sql_execute_url 但 datasource_id 非空，仍强制 HTTP。"""
    config = DataSourceConfig(
        alias="legacy_http",
        db_type="MYSQL",
        datasource_id=999,
        endpoint_url="http://legacy.example/sql",  # 历史调用方需要自己塞 endpoint_url
    )
    manager = DataSourceManager({"legacy_http": config}, fallback_loader=None)

    connector = _unwrap(manager.get_connector("legacy_http"))
    assert isinstance(connector, HttpSqlConnector)
    assert connector.config.endpoint_url == "http://legacy.example/sql"


def test_loader_without_sql_execute_url_attribute_is_tolerated() -> None:
    """fallback_loader 没有 sql_execute_url 属性时不应崩溃。"""

    class _LegacyLoader:
        pass

    config = DataSourceConfig(alias="sqlite_db", db_type="SQLITE")
    manager = DataSourceManager({"sqlite_db": config}, fallback_loader=_LegacyLoader())

    # 不应抛异常，按 db_type 走本地 connector
    connector = _unwrap(manager.get_connector("sqlite_db"))
    assert not isinstance(connector, HttpSqlConnector)


@pytest.mark.parametrize("empty_value", ["", None])
def test_empty_or_none_sql_execute_url_does_not_force_http(empty_value: str | None) -> None:
    config = DataSourceConfig(alias="sqlite_db", db_type="SQLITE")
    loader = _FakeLoader(sql_execute_url=empty_value)
    manager = DataSourceManager({"sqlite_db": config}, fallback_loader=loader)

    connector = _unwrap(manager.get_connector("sqlite_db"))
    assert not isinstance(connector, HttpSqlConnector)
