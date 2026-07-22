"""Read full Markdown documents from knowledge bases."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from threading import Thread
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

DEFAULT_READ_FILE_PATH = "/api/v1/readFile"
SERVICE_NAME_ENV_VARS = (
    "DATACLOUD_KB_READ_SERVICE_NAME",
    "QA_DOMAINNAME",
    "DATACLOUD_RESULT_FILE_SERVICE_NAME",
    "BE_DOMAINNAME",
)
_TIMEOUT_SECONDS = 30.0

PostJson = Callable[[str, dict[str, Any], dict[str, str]], Any]


class KbDocumentReadError(RuntimeError):
    """Raised when the knowledge-base document cannot be read."""


@dataclass(frozen=True)
class KbDocumentReader:
    """Client for knowledge-base ``POST /api/v1/readFile``."""

    base_url: str = ""
    service_name: str = ""
    read_path: str = DEFAULT_READ_FILE_PATH
    post_json: PostJson | None = None

    def read_text(
        self,
        *,
        kn_code: str,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Read one knowledge-base document as Markdown text."""
        normalized_kn_code = kn_code.strip()
        normalized_file_path = file_path.strip()
        if not normalized_kn_code:
            raise KbDocumentReadError("knCode is required")
        if not normalized_file_path.startswith("/"):
            raise KbDocumentReadError("filePath must start with /")

        body: dict[str, Any] = {
            "knCode": normalized_kn_code,
            "filePath": normalized_file_path,
        }
        if start_line is not None:
            body["startLine"] = start_line
        if end_line is not None:
            body["endLine"] = end_line

        headers = _build_headers()
        response_body = self._post(body=body, headers=headers)
        content = _extract_content(response_body)
        logger.info(
            "KB document read succeeded: knCode=%s filePath=%s content_length=%d",
            normalized_kn_code,
            normalized_file_path,
            len(content),
        )
        return content

    def _post(self, *, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        if self.post_json is not None:
            return _ensure_dict(self.post_json(self.read_path, body, headers))

        base_url = self.base_url.strip().rstrip("/")
        if _is_complete_url(base_url):
            url = f"{base_url}{self.read_path}"
            logger.info(
                "KB document read request: transport=http url=%s knCode=%s "
                "filePath=%s has_token=%s",
                url,
                body.get("knCode", ""),
                body.get("filePath", ""),
                bool(headers.get("Beyond-Token") or headers.get("beyond-token")),
            )
            with httpx.Client(timeout=_TIMEOUT_SECONDS, headers=headers) as client:
                response = client.post(url, json=body)
                response.raise_for_status()
                return _ensure_dict(response.json())

        service_name = self.service_name.strip() or _default_service_name()
        if not service_name:
            raise KbDocumentReadError(
                "KB read service name is required: set "
                "DATACLOUD_KB_READ_SERVICE_NAME or QA_DOMAINNAME"
            )
        logger.info(
            "KB document read request: transport=discovery service_name=%s path=%s "
            "knCode=%s filePath=%s has_token=%s",
            service_name,
            self.read_path,
            body.get("knCode", ""),
            body.get("filePath", ""),
            bool(headers.get("Beyond-Token") or headers.get("beyond-token")),
        )
        return _ensure_dict(
            _run_async_in_thread(
                _post_by_discovery(
                    service_name=service_name,
                    path=self.read_path,
                    body=body,
                    headers=headers,
                )
            )
        )


def build_default_kb_document_reader() -> KbDocumentReader:
    """Build the default Platform KB document reader from environment config."""
    return KbDocumentReader(
        base_url=(
            os.getenv("DATACLOUD_KB_READ_API_BASE_URL")
            or os.getenv("DATACLOUD_BYAI_SERVICE_BASE_URL")
            or os.getenv("DATACLOUD_RESULT_FILE_API_BASE_URL")
            or ""
        ).strip(),
        service_name=_default_service_name(),
        read_path=(
            os.getenv("DATACLOUD_KB_READ_PATH") or DEFAULT_READ_FILE_PATH
        ).strip(),
    )


async def _post_by_discovery(
    *,
    service_name: str,
    path: str,
    body: dict[str, Any],
    headers: dict[str, str],
) -> Any:
    try:
        from by_framework.core.discovery import DiscoveryClient  # noqa: PLC0415
        from by_framework.util.discovery_http_client import (  # noqa: PLC0415
            DiscoveryHttpClient,
        )
        from by_framework.util.http_client import RetryConfig  # noqa: PLC0415
        from redis.asyncio import Redis  # noqa: PLC0415
    except ImportError as exc:
        raise KbDocumentReadError(
            "KB read service discovery dependencies are unavailable"
        ) from exc

    redis_client = Redis(
        host=os.getenv("DATACLOUD_GATEWAY_REDIS_HOST", "localhost"),
        port=int(os.getenv("DATACLOUD_GATEWAY_REDIS_PORT", "6379")),
        db=int(os.getenv("DATACLOUD_GATEWAY_REDIS_DB", "0")),
        password=os.getenv("DATACLOUD_GATEWAY_REDIS_PASSWORD") or None,
        username=os.getenv("DATACLOUD_GATEWAY_REDIS_USERNAME") or None,
        decode_responses=True,
    )
    discovery_client = DiscoveryClient(redis_client=redis_client, cache_interval=5)
    retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
    try:
        async with DiscoveryHttpClient(
            discovery_client,
            retry_config=retry_config,
            health_threshold_ms=-1,
        ) as client:
            response = await client.post(service_name, path, headers=headers, json=body)
    finally:
        await discovery_client.close()
        await redis_client.aclose()

    if not response.is_success:
        raise KbDocumentReadError(
            f"HTTP {response.status_code} calling {service_name}{path}: {response.data}"
        )
    return response.data


def _extract_content(response_body: dict[str, Any]) -> str:
    result_code = str(response_body.get("resultCode", "0")).strip()
    if result_code not in {"0", "200"}:
        message = str(response_body.get("resultMsg") or "KB document read failed")
        raise KbDocumentReadError(message)

    result_object = response_body.get("resultObject")
    if not isinstance(result_object, dict):
        raise KbDocumentReadError("resultObject must be a JSON object")

    content = result_object.get("data")
    if content is None:
        content = result_object.get("content")
    if not isinstance(content, str):
        raise KbDocumentReadError("resultObject.data must be a string")
    return content


def _build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = _current_context_value("token") or os.getenv("BEYOND_TOKEN", "")
    if token:
        headers["Beyond-Token"] = token
        headers["beyond-token"] = token
        headers["Authorization"] = f"Bearer {token}"

    system_code = _current_context_value("system_code")
    if system_code:
        headers["X-System-Code"] = system_code

    tenant_id = _current_context_value("tenant_id")
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id
    return headers


def _current_context_value(attr_name: str) -> str:
    try:
        from datacloud_data_sdk.context import get_current_context  # noqa: PLC0415
        from datacloud_data_sdk.exceptions import DatacloudError  # noqa: PLC0415
    except ImportError:
        return ""

    try:
        context = get_current_context()
    except (DatacloudError, LookupError, RuntimeError):
        return ""
    return str(getattr(context, attr_name, "") or "").strip()


def _ensure_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise KbDocumentReadError("KB read service response must be JSON") from exc
        if isinstance(decoded, dict):
            return decoded
    raise KbDocumentReadError("KB read service response must be a JSON object")


def _run_async_in_thread(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive bridge
            error["exc"] = exc

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "exc" in error:
        raise error["exc"]
    return result.get("value")


def _is_complete_url(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.scheme and parsed.netloc)


def _default_service_name() -> str:
    for env_name in SERVICE_NAME_ENV_VARS:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return ""
