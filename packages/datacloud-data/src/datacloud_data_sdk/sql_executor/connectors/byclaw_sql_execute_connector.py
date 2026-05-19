"""ByClaw sqlExecute connector based on service discovery."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.exceptions import DatacloudError, SqlExecutionError
from datacloud_data_sdk.sql_executor.base_connector import BaseSourceConnector
from datacloud_data_sdk.sql_executor.models import DataSourceConfig

_SQL_EXECUTE_PATH = "/plugins/byclaw-sqlite/sqlExecute"


@dataclass(frozen=True)
class RedisDiscoveryConfig:
    """Redis configuration used by ByClaw service discovery."""

    host: str
    port: int = 6379
    database: int = 0
    password: str | None = None
    username: str | None = None


class ByclawSqlExecuteConnector(BaseSourceConnector):
    """Execute SQL through ByClaw sqlExecute API discovered from Redis."""

    _default_redis_config: RedisDiscoveryConfig | None = None

    def __init__(
        self,
        config: DataSourceConfig,
        redis_config: RedisDiscoveryConfig | None = None,
    ) -> None:
        super().__init__(config)
        self._redis_config = (
            redis_config or self.__class__._default_redis_config or _load_redis_discovery_config()
        )

    @classmethod
    def supported_type(cls) -> str:
        return "BYCLAW_SQL_EXECUTE"

    @classmethod
    def configure_default_redis(cls, redis_config: RedisDiscoveryConfig | None) -> None:
        """Configure default Redis discovery settings for registry-created instances."""
        cls._default_redis_config = redis_config

    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        user_code = self._resolve_user_code()
        payload: dict[str, Any] = {
            "sql": _render_sql(sql, params),
            "user_code": user_code,
        }

        try:
            body = await self._post_by_discovery(user_code, payload)
        except (ImportError, ValueError, RuntimeError) as exc:
            raise SqlExecutionError(self.config.alias, sql, str(exc)) from exc

        try:
            return self._extract_records(body)
        except (TypeError, ValueError) as exc:
            raise SqlExecutionError(self.config.alias, sql, str(exc)) from exc

    async def test_connection(self) -> bool:
        try:
            await self.execute("SELECT 1")
        except Exception:  # noqa: BLE001
            return False
        return True

    async def _post_by_discovery(self, user_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        service_name = self._resolve_service_name(user_code)

        try:
            from by_framework.common.redis_client import init_redis
            from by_framework.core.discovery import DiscoveryClient
            from by_framework.util.discovery_http_client import DiscoveryHttpClient
            from by_framework.util.http_client import RetryConfig
        except ImportError as exc:
            raise RuntimeError(
                "BYCLAW_SQL_EXECUTE service discovery requires by_framework dependency"
            ) from exc

        init_redis(
            host=self._redis_config.host,
            port=self._redis_config.port,
            db=self._redis_config.database,
            password=self._redis_config.password,
            username=self._redis_config.username,
        )
        discovery_client = DiscoveryClient(cache_interval=5)
        retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
        try:
            instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
            if not instance:
                raise RuntimeError(f"未找到 SQLite 服务实例: {service_name}")

            metadata = instance.metadata or {}
            token = metadata.get("token", "")
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            async with DiscoveryHttpClient(
                discovery_client,
                retry_config=retry_config,
                health_threshold_ms=-1,
            ) as client:
                response = await client.post(
                    service_name,
                    _SQL_EXECUTE_PATH,
                    headers=headers,
                    json=payload,
                )
        finally:
            await discovery_client.close()

        body = response.data
        if not isinstance(body, dict):
            raise ValueError("BYCLAW_SQL_EXECUTE response must be a JSON object")
        return body

    def _resolve_user_code(self) -> str:
        try:
            ctx = get_current_context()
        except DatacloudError as exc:
            raise SqlExecutionError(
                self.config.alias,
                "",
                "InvocationContext is required to resolve BYCLAW_SQL_EXECUTE user_code",
            ) from exc

        if isinstance(ctx.extras, dict):
            user_code = ctx.extras.get("user_code")
            if isinstance(user_code, str) and user_code:
                return user_code

        if ctx.user_id:
            return ctx.user_id

        raise SqlExecutionError(
            self.config.alias,
            "",
            "BYCLAW_SQL_EXECUTE user_code is required; set InvocationContext(user_id=...) "
            'or extras={"user_code": "..."}',
        )

    def _resolve_service_name(self, user_code: str) -> str:
        service_name = self.config.service_name.strip()
        return service_name or f"BYCLAW_EXE_{user_code}"

    def _extract_records(self, body: Any) -> list[dict[str, Any]]:
        if not isinstance(body, dict):
            raise TypeError("BYCLAW_SQL_EXECUTE response must be a JSON object")

        if body.get("ok") is False:
            error = body.get("error")
            raise ValueError(f"BYCLAW_SQL_EXECUTE service returned error: {error or body}")

        result_code = body.get("resultCode")
        if result_code not in (None, "0", 0):
            message = str(body.get("resultMsg") or body.get("message") or "unknown error")
            raise ValueError(
                f"BYCLAW_SQL_EXECUTE service returned resultCode={result_code}: {message}"
            )

        candidates = [
            body.get("data"),
            body.get("resultObject"),
            body.get("resultData"),
        ]
        for candidate in candidates:
            records = _extract_record_list(candidate)
            if records is not None:
                return records
        return []


def _load_redis_discovery_config() -> RedisDiscoveryConfig:
    return RedisDiscoveryConfig(
        host=_env_first("REDIS_HOST", "DATACLOUD_GATEWAY_REDIS_HOST") or "localhost",
        port=_env_int_first(6379, "REDIS_PORT", "DATACLOUD_GATEWAY_REDIS_PORT"),
        database=_env_int_first(0, "REDIS_DATABASE", "DATACLOUD_GATEWAY_REDIS_DATABASE"),
        password=_env_first("REDIS_PASSWORD", "DATACLOUD_GATEWAY_REDIS_PASSWORD") or None,
        username=_env_first("REDIS_USERNAME", "DATACLOUD_GATEWAY_REDIS_USERNAME") or None,
    )


def _env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def _env_int_first(default: int, *names: str) -> int:
    value = _env_first(*names)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _extract_record_list(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    if not isinstance(value, dict):
        return None
    for key in ("records", "rows", "data", "resultData"):
        records = _extract_record_list(value.get(key))
        if records is not None:
            return records
    return None


def _render_sql(sql: str, params: dict[str, Any] | None) -> str:
    if not params:
        return sql

    result = sql
    for key in sorted(params.keys(), key=len, reverse=True):
        value = params[key]
        result = re.sub(rf":{re.escape(key)}\b", _sql_literal(value), result)
    return result


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"
