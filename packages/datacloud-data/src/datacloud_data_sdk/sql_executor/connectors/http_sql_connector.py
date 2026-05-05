"""HTTP SQL 连接器。"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.exceptions import DatacloudError, SqlExecutionError
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector

logger = logging.getLogger(__name__)


class HttpSqlConnector(BaseSourceConnector):
    """通过外部 HTTP 接口执行 SQL 的连接器。"""

    @classmethod
    def supported_type(cls) -> str:
        return "HTTP_SQL"

    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        endpoint_url = os.environ.get("DATACLOUD_SQL_SERVICE_URL")
        if not endpoint_url:
            raise SqlExecutionError(
                self.config.alias, sql, "DATACLOUD_SQL_SERVICE_URL environment variable is required"
            )
        if self.config.datasource_id is None:
            raise SqlExecutionError(self.config.alias, sql, "HTTP SQL datasource_id is required")

        payload: dict[str, Any] = {
            "datasourceId": self.config.datasource_id,
            "sql": sql,
        }
        if params:
            payload["params"] = params

        headers = self._build_headers()
        try:
            async with httpx.AsyncClient(timeout=self.config.pool_timeout) as client:
                response = await client.post(endpoint_url, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SqlExecutionError(self.config.alias, sql, str(exc)) from exc

        try:
            return self._extract_records(body)
        except (TypeError, ValueError) as exc:
            raise SqlExecutionError(self.config.alias, sql, str(exc)) from exc

    async def test_connection(self) -> bool:
        try:
            await self.execute("SELECT 1")
        except Exception:
            return False
        return True

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}

        try:
            ctx = get_current_context()
        except DatacloudError:
            return headers

        if ctx.token:
            headers["Authorization"] = f"Bearer {ctx.token}"
        if ctx.tenant_id:
            headers["X-Tenant-Id"] = ctx.tenant_id
        if ctx.user_id:
            headers["X-User-Id"] = ctx.user_id
        if ctx.session_id:
            headers["X-Session-Id"] = ctx.session_id
        if ctx.system_code:
            headers["X-System-Code"] = ctx.system_code
        if ctx.cookie:
            headers["cookie"] = ctx.cookie
        return headers

    def _extract_records(self, body: Any) -> list[dict[str, Any]]:
        if not isinstance(body, dict):
            raise TypeError("HTTP SQL response must be a JSON object")

        result_code = body.get("resultCode")
        if result_code not in (None, "0", 0):
            message = str(body.get("resultMsg") or body.get("message") or "unknown error")
            raise ValueError(f"HTTP SQL service returned resultCode={result_code}: {message}")

        result_object = body.get("resultObject")
        if not isinstance(result_object, dict):
            return []

        result_data = result_object.get("resultData")
        if result_data is None:
            return []
        if not isinstance(result_data, list):
            raise TypeError("HTTP SQL response resultObject.resultData must be a list")

        records: list[dict[str, Any]] = []
        for row in result_data:
            if isinstance(row, dict):
                records.append(row)
            else:
                logger.debug("Ignore non-object row from HTTP SQL response: %r", row)
        return records
