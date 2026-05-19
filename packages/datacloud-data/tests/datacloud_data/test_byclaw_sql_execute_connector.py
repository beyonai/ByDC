"""ByClaw sqlExecute connector tests."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType
from typing import Any
from unittest.mock import Mock, patch

import pytest
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.sql_executor.connector_registry import ConnectorRegistry
from datacloud_data_sdk.sql_executor.connectors.byclaw_sql_execute_connector import (
    ByclawSqlExecuteConnector,
    RedisDiscoveryConfig,
    _load_redis_discovery_config,
)
from datacloud_data_sdk.sql_executor.data_source_manager import (
    DataSourceManager,
    _LoggingConnectorProxy,
)
from datacloud_data_sdk.sql_executor.models import DataSourceConfig


def _make_config(
    *,
    endpoint_url: str = "http://byclaw.example/sqlExecute",
    service_name: str = "",
) -> DataSourceConfig:
    return DataSourceConfig(
        alias="dynamic_table",
        db_type="SQLITE",
        connector_type="BYCLAW_SQL_EXECUTE",
        service_name=service_name,
        endpoint_url=endpoint_url,
    )


def _unwrap(connector: Any) -> Any:
    if isinstance(connector, _LoggingConnectorProxy):
        return connector._real  # type: ignore[attr-defined]
    return connector


@pytest.mark.asyncio
async def test_byclaw_connector_posts_sql_and_user_code() -> None:
    connector = ByclawSqlExecuteConnector(
        _make_config(endpoint_url="http://ignored.example/sqlExecute"),
        redis_config=RedisDiscoveryConfig(host="redis.local"),
    )

    with _patch_by_framework(
        expected_service_name="BYCLAW_EXE_0027024630",
        expected_payload={"sql": "SELECT 1", "user_code": "0027024630"},
        response_body={"ok": True, "data": {"rows": [{"id": 1}]}},
    ):
        with InvocationContext(user_id="0027024630", token="gateway-token"):
            records = await connector.execute("SELECT 1")

    assert records == [{"id": 1}]


@pytest.mark.asyncio
async def test_byclaw_connector_uses_extras_user_code() -> None:
    connector = ByclawSqlExecuteConnector(
        _make_config(endpoint_url=""),
        redis_config=RedisDiscoveryConfig(host="redis.local"),
    )

    with _patch_by_framework(
        expected_service_name="BYCLAW_EXE_extra-user",
        expected_payload={"sql": "SELECT 1 AS value", "user_code": "extra-user"},
        response_body={"resultObject": {"resultData": []}},
    ):
        with InvocationContext(user_id="fallback-user", extras={"user_code": "extra-user"}):
            await connector.execute("SELECT :p0 AS value", {"p0": 1})


def test_byclaw_connector_registered_by_default() -> None:
    assert ConnectorRegistry.get("BYCLAW_SQL_EXECUTE") is ByclawSqlExecuteConnector


def test_data_source_manager_uses_byclaw_connector_type() -> None:
    manager = DataSourceManager({"dynamic_table": _make_config()})

    connector = _unwrap(manager.get_connector("dynamic_table"))

    assert isinstance(connector, ByclawSqlExecuteConnector)


def test_byclaw_connector_uses_configured_default_redis() -> None:
    redis_config = RedisDiscoveryConfig(host="configured.redis")
    ByclawSqlExecuteConnector.configure_default_redis(redis_config)
    try:
        connector = ByclawSqlExecuteConnector(_make_config())
    finally:
        ByclawSqlExecuteConnector.configure_default_redis(None)

    assert connector._redis_config == redis_config  # type: ignore[attr-defined]


def test_redis_discovery_config_prefers_unprefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_HOST", "redis.local")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DATABASE", "2")
    monkeypatch.setenv("REDIS_PASSWORD", "redis-password")
    monkeypatch.setenv("REDIS_USERNAME", "redis-user")
    monkeypatch.setenv("DATACLOUD_REDIS_HOST", "datacloud-redis.local")
    monkeypatch.setenv("DATACLOUD_REDIS_PORT", "6381")
    monkeypatch.setenv("DATACLOUD_REDIS_DATABASE", "3")

    config = _load_redis_discovery_config()

    assert config == RedisDiscoveryConfig(
        host="redis.local",
        port=6380,
        database=2,
        password="redis-password",
        username="redis-user",
    )


def test_redis_discovery_config_falls_back_to_prefixed_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_DATABASE",
        "REDIS_PASSWORD",
        "REDIS_USERNAME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATACLOUD_REDIS_HOST", "datacloud-redis.local")
    monkeypatch.setenv("DATACLOUD_REDIS_PORT", "6381")
    monkeypatch.setenv("DATACLOUD_REDIS_DATABASE", "3")

    config = _load_redis_discovery_config()

    assert config.host == "datacloud-redis.local"
    assert config.port == 6381
    assert config.database == 3


@pytest.mark.asyncio
async def test_byclaw_connector_uses_service_discovery_when_endpoint_url_empty() -> None:
    connector = ByclawSqlExecuteConnector(
        _make_config(endpoint_url="", service_name="BYCLAW_EXE_CUSTOM"),
        redis_config=RedisDiscoveryConfig(host="redis.local", port=6380, database=2),
    )

    with _patch_by_framework(
        expected_service_name="BYCLAW_EXE_CUSTOM",
        expected_payload={"sql": "SELECT 1", "user_code": "0027024630"},
        response_body={"ok": True, "data": {"rows": [{"id": 1}]}},
    ) as init_redis:
        with InvocationContext(user_id="0027024630"):
            records = await connector.execute("SELECT 1")

    init_redis.assert_called_once_with(
        host="redis.local",
        port=6380,
        db=2,
        password=None,
        username=None,
    )
    assert records == [{"id": 1}]


@contextmanager
def _patch_by_framework(
    *,
    expected_service_name: str,
    expected_payload: dict[str, Any],
    response_body: dict[str, Any],
) -> Iterator[Mock]:
    class _MockInstance:
        metadata = {"token": "instance-token"}

    class _MockDiscoveryClient:
        def __init__(self, cache_interval: int) -> None:
            self.cache_interval = cache_interval

        async def discover(self, service_name: str, health_threshold_ms: int) -> _MockInstance:
            assert service_name == expected_service_name
            assert health_threshold_ms == -1
            return _MockInstance()

        async def close(self) -> None:
            return None

    class _MockRetryConfig:
        def __init__(self, max_attempts: int, retry_on_status_codes: set[int]) -> None:
            self.max_attempts = max_attempts
            self.retry_on_status_codes = retry_on_status_codes

    class _MockDiscoveryHttpClient:
        def __init__(
            self,
            discovery_client: _MockDiscoveryClient,
            *,
            retry_config: _MockRetryConfig,
            health_threshold_ms: int,
        ) -> None:
            self.discovery_client = discovery_client
            self.retry_config = retry_config
            self.health_threshold_ms = health_threshold_ms

        async def __aenter__(self) -> _MockDiscoveryHttpClient:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        async def post(
            self,
            service_name: str,
            path: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> Any:
            assert service_name == expected_service_name
            assert path == "/plugins/byclaw-sqlite/sqlExecute"
            assert headers["Authorization"] == "Bearer instance-token"
            assert json == expected_payload
            return type("_MockDiscoveryResponse", (), {"data": response_body})()

    common_module = ModuleType("by_framework.common")
    redis_module = ModuleType("by_framework.common.redis_client")
    core_module = ModuleType("by_framework.core")
    discovery_module = ModuleType("by_framework.core.discovery")
    util_module = ModuleType("by_framework.util")
    discovery_http_module = ModuleType("by_framework.util.discovery_http_client")
    http_client_module = ModuleType("by_framework.util.http_client")

    init_redis = Mock()
    redis_module.init_redis = init_redis  # type: ignore[attr-defined]
    discovery_module.DiscoveryClient = _MockDiscoveryClient  # type: ignore[attr-defined]
    discovery_http_module.DiscoveryHttpClient = _MockDiscoveryHttpClient  # type: ignore[attr-defined]
    http_client_module.RetryConfig = _MockRetryConfig  # type: ignore[attr-defined]

    modules = {
        "by_framework.common": common_module,
        "by_framework.common.redis_client": redis_module,
        "by_framework.core": core_module,
        "by_framework.core.discovery": discovery_module,
        "by_framework.util": util_module,
        "by_framework.util.discovery_http_client": discovery_http_module,
        "by_framework.util.http_client": http_client_module,
    }
    with patch.dict(sys.modules, modules):
        yield init_redis
