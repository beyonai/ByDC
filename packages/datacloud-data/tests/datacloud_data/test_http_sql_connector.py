"""HttpSqlConnector 行为测试（chatbi 对接方案）。

覆盖：
1. execute() 从 ``DataSourceConfig.endpoint_url`` 读取地址（不再读 env）
2. endpoint_url 为空时抛出明确异常，不再降级到 env
3. _build_headers 中 cookie 取值优先级：extras["cookie"] > RequestContext.cookie
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.exceptions import SqlExecutionError
from datacloud_data_sdk.sql_executor.connectors.http_sql_connector import HttpSqlConnector
from datacloud_data_sdk.sql_executor.models import DataSourceConfig


def _make_config(
    *,
    endpoint_url: str = "http://test.example/api/sql",
    datasource_id: int | None = 86994,
) -> DataSourceConfig:
    return DataSourceConfig(
        alias="ds_http",
        db_type="HTTP_SQL",
        datasource_id=datasource_id,
        endpoint_url=endpoint_url,
    )


class _MockResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "resultCode": "0",
            "resultObject": {"resultData": [{"id": 1}]},
        }


@pytest.mark.asyncio
async def test_execute_uses_endpoint_url_from_config() -> None:
    config = _make_config(endpoint_url="http://configured.example/api/sql")
    connector = HttpSqlConnector(config)

    mock_post = AsyncMock(return_value=_MockResponse())
    with patch("httpx.AsyncClient.post", mock_post):
        await connector.execute("SELECT 1")

    mock_post.assert_awaited_once()
    args, kwargs = mock_post.await_args
    # httpx 用第一个位置参数传 URL
    posted_url = args[0] if args else kwargs.get("url")
    assert posted_url == "http://configured.example/api/sql"


@pytest.mark.asyncio
async def test_execute_raises_when_endpoint_url_empty() -> None:
    config = _make_config(endpoint_url="", datasource_id=1)
    connector = HttpSqlConnector(config)

    with pytest.raises(SqlExecutionError) as exc_info:
        await connector.execute("SELECT 1")

    msg = str(exc_info.value)
    assert "endpoint_url" in msg
    assert "DATACLOUD_SQL_SERVICE_URL" not in msg


@pytest.mark.asyncio
async def test_execute_does_not_read_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """即便 env var 仍存在，也不应被使用。"""
    monkeypatch.setenv("DATACLOUD_SQL_SERVICE_URL", "http://env-should-be-ignored.example/api")
    config = _make_config(endpoint_url="http://from-config.example/api/sql")
    connector = HttpSqlConnector(config)

    mock_post = AsyncMock(return_value=_MockResponse())
    with patch("httpx.AsyncClient.post", mock_post):
        await connector.execute("SELECT 1")

    args, _ = mock_post.await_args
    assert args[0] == "http://from-config.example/api/sql"


@pytest.mark.asyncio
async def test_cookie_extras_takes_priority_over_ctx_cookie() -> None:
    config = _make_config()
    connector = HttpSqlConnector(config)

    mock_post = AsyncMock(return_value=_MockResponse())
    with InvocationContext(cookie="legacy=1", extras={"cookie": "from_extras=2"}):
        with patch("httpx.AsyncClient.post", mock_post):
            await connector.execute("SELECT 1")

    _, kwargs = mock_post.await_args
    assert kwargs["headers"]["cookie"] == "from_extras=2"


@pytest.mark.asyncio
async def test_cookie_falls_back_to_ctx_cookie_when_extras_missing() -> None:
    config = _make_config()
    connector = HttpSqlConnector(config)

    mock_post = AsyncMock(return_value=_MockResponse())
    with InvocationContext(cookie="legacy_only=1"):
        with patch("httpx.AsyncClient.post", mock_post):
            await connector.execute("SELECT 1")

    _, kwargs = mock_post.await_args
    assert kwargs["headers"]["cookie"] == "legacy_only=1"


@pytest.mark.asyncio
async def test_cookie_extras_non_string_falls_back_to_ctx_cookie() -> None:
    """extras["cookie"] 为非字符串时应忽略，回退到 ctx.cookie。"""
    config = _make_config()
    connector = HttpSqlConnector(config)

    mock_post = AsyncMock(return_value=_MockResponse())
    with InvocationContext(cookie="legacy=1", extras={"cookie": 12345}):
        with patch("httpx.AsyncClient.post", mock_post):
            await connector.execute("SELECT 1")

    _, kwargs = mock_post.await_args
    assert kwargs["headers"]["cookie"] == "legacy=1"


@pytest.mark.asyncio
async def test_cookie_extras_empty_string_falls_back_to_ctx_cookie() -> None:
    config = _make_config()
    connector = HttpSqlConnector(config)

    mock_post = AsyncMock(return_value=_MockResponse())
    with InvocationContext(cookie="legacy=1", extras={"cookie": ""}):
        with patch("httpx.AsyncClient.post", mock_post):
            await connector.execute("SELECT 1")

    _, kwargs = mock_post.await_args
    assert kwargs["headers"]["cookie"] == "legacy=1"


@pytest.mark.asyncio
async def test_cookie_absent_when_neither_set() -> None:
    config = _make_config()
    connector = HttpSqlConnector(config)

    mock_post = AsyncMock(return_value=_MockResponse())
    with InvocationContext():
        with patch("httpx.AsyncClient.post", mock_post):
            await connector.execute("SELECT 1")

    _, kwargs = mock_post.await_args
    assert "cookie" not in kwargs["headers"]
