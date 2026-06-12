"""ClickHouse 连接器。"""

from __future__ import annotations

import re
from typing import Any

from datacloud_data_sdk.exceptions import SqlExecutionError
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector
from datacloud_data_sdk.sql_executor.jdbc_parser import parse_clickhouse_jdbc_url
from datacloud_data_sdk.sql_executor.models import DataSourceConfig


def _build_clickhouse_url(params: dict[str, Any]) -> str:
    host = params.get("host", "localhost")
    port = params.get("port", 8123)
    return f"http://{host}:{port}/"


def _inline_params(sql: str, params: dict[str, Any]) -> str:
    """将 SQLAlchemy 风格的 :param_name 替换为 ClickHouse 可接受的字面值。

    ClickHouse HTTP 接口不支持 :name 占位符，需要在发送前内联替换。
    """

    def _quote(val: Any) -> str:
        if val is None:
            return "NULL"
        if isinstance(val, bool):
            return "1" if val else "0"
        if isinstance(val, (int, float)):
            return str(val)
        # 字符串：单引号转义
        return "'" + str(val).replace("\\", "\\\\").replace("'", "\\'") + "'"

    def _replace(m: re.Match) -> str:
        name = m.group(1)
        return _quote(params[name]) if name in params else m.group(0)

    return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", _replace, sql)


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
            # ClickHouse HTTP 接口不支持 SQLAlchemy :name 占位符，内联替换后以纯 SQL 发送
            if params:
                sql = _inline_params(sql, params)
                params = None
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

    def __getstate__(self) -> dict[str, Any]:
        return {"config": self.config, "_params": self._params}

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.config = state["config"]
        self._params = state["_params"]
        self._client = None
        self._session = None
