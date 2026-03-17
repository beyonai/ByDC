"""ClickHouse 连接器。"""

from __future__ import annotations

from typing import Any

from datacloud_data.exceptions import SqlExecutionError
from datacloud_data.sql_executor.base_connector import BaseSourceConnector
from datacloud_data.sql_executor.jdbc_parser import parse_clickhouse_jdbc_url
from datacloud_data.sql_executor.models import DataSourceConfig


def _build_clickhouse_url(params: dict[str, Any]) -> str:
    host = params.get("host", "localhost")
    port = params.get("port", 8123)
    return f"http://{host}:{port}/"


class ClickHouseConnector(BaseSourceConnector):
    """ClickHouse 异步连接器，基于 aiochclient。

    需要安装: pip install aiochclient[aiohttp]
    """

    def __init__(self, config: DataSourceConfig) -> None:
        super().__init__(config)
        self._client = None
        self._session = None
        self._params = dict(parse_clickhouse_jdbc_url(config.jdbc_url))
        if config.user:
            self._params["user"] = config.user
        if config.password:
            self._params["password"] = config.password

    async def _get_client(self) -> Any:
        if self._client is None:
            try:
                from aiochclient import ChClient
                from aiohttp import ClientSession
            except ImportError as e:
                raise ImportError(
                    "aiochclient not installed. Install with: pip install aiochclient[aiohttp]"
                ) from e

            self._session = ClientSession()
            self._client = ChClient(
                self._session,
                url=_build_clickhouse_url(self._params),
                user=self._params.get("user") or None,
                password=self._params.get("password") or None,
                database=self._params.get("database", "default"),
            )
        return self._client

    @classmethod
    def supported_type(cls) -> str:
        return "CLICKHOUSE"

    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            client = await self._get_client()
            rows = await client.fetch(sql, params=params or {})
            if not rows:
                return []
            out: list[dict[str, Any]] = []
            for row in rows:
                if hasattr(row, "_mapping"):
                    out.append(dict(row._mapping))
                elif hasattr(row, "keys"):
                    out.append(dict(row))
                else:
                    out.append({"value": row})
            return out
        except Exception as e:
            raise SqlExecutionError(self.config.alias, sql, str(e)) from e

    async def test_connection(self) -> bool:
        try:
            result = await self.execute("SELECT 1")
            return len(result) == 1
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
        if self._session:
            await self._session.close()
            self._session = None
