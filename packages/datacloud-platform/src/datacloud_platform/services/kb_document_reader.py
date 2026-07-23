"""Download full Markdown documents from knowledge bases."""

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

DEFAULT_DOWNLOAD_FILE_PATH = "/api/v1/downloadFile"
DEFAULT_READ_FILE_PATH = DEFAULT_DOWNLOAD_FILE_PATH
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
    """Client for knowledge-base ``POST /api/v1/downloadFile``."""

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
        """Download one knowledge-base document as Markdown text."""
        _ = start_line, end_line
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

        headers = _build_headers()
        response_payload = self._post(body=body, headers=headers)
        content = _extract_text(response_payload)
        logger.info(
            "KB document download succeeded: knCode=%s filePath=%s content_length=%d",
            normalized_kn_code,
            normalized_file_path,
            len(content),
        )
        return content

    def _post(self, *, body: dict[str, Any], headers: dict[str, str]) -> Any:
        if self.post_json is not None:
            return self.post_json(self.read_path, body, headers)

        base_url = self.base_url.strip().rstrip("/")
        if _is_complete_url(base_url):
            url = f"{base_url}{self.read_path}"
            logger.info(
                "KB document download request: transport=http url=%s knCode=%s "
                "filePath=%s has_token=%s",
                url,
                body.get("knCode", ""),
                body.get("filePath", ""),
                bool(headers.get("Beyond-Token") or headers.get("beyond-token")),
            )
            with httpx.Client(timeout=_TIMEOUT_SECONDS, headers=headers) as client:
                response = client.post(url, json=body)
                return _payload_from_httpx_response(response)

        service_name = self.service_name.strip() or _default_service_name()
        if not service_name:
            raise KbDocumentReadError(
                "KB download service name is required: set "
                "DATACLOUD_KB_READ_SERVICE_NAME or QA_DOMAINNAME"
            )
        logger.info(
            "KB document download request: transport=discovery service_name=%s path=%s "
            "knCode=%s filePath=%s has_token=%s",
            service_name,
            self.read_path,
            body.get("knCode", ""),
            body.get("filePath", ""),
            bool(headers.get("Beyond-Token") or headers.get("beyond-token")),
        )
        return _run_async_in_thread(
            _download_by_discovery(
                service_name=service_name,
                path=self.read_path,
                body=body,
                headers=headers,
            )
        )


def build_default_kb_document_reader() -> KbDocumentReader:
    """Build the default Platform KB document reader from environment config."""
    return KbDocumentReader(
        base_url=(
            os.getenv("DATACLOUD_KB_DOWNLOAD_API_BASE_URL")
            or os.getenv("DATACLOUD_KB_READ_API_BASE_URL")
            or os.getenv("DATACLOUD_BYAI_SERVICE_BASE_URL")
            or os.getenv("DATACLOUD_RESULT_FILE_API_BASE_URL")
            or ""
        ).strip(),
        service_name=_default_service_name(),
        read_path=(
            os.getenv("DATACLOUD_KB_DOWNLOAD_PATH")
            or os.getenv("DATACLOUD_KB_READ_PATH")
            or DEFAULT_DOWNLOAD_FILE_PATH
        ).strip(),
    )


async def _download_by_discovery(
    *,
    service_name: str,
    path: str,
    body: dict[str, Any],
    headers: dict[str, str],
) -> Any:
    try:
        from by_framework.core.discovery import DiscoveryClient  # noqa: PLC0415
        from redis.asyncio import Redis  # noqa: PLC0415
    except ImportError as exc:
        raise KbDocumentReadError(
            "KB download service discovery dependencies are unavailable"
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
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS,
            headers=headers,
        ) as client:
            last_error: KbDocumentReadError | None = None
            for _ in range(3):
                instance = await discovery_client.discover(
                    service_name,
                    health_threshold_ms=-1,
                )
                if not instance:
                    raise KbDocumentReadError(
                        f"No available instances for service: {service_name}"
                    )
                url = _build_discovered_url(instance, path)
                try:
                    response = await client.post(url, json=body)
                except httpx.HTTPError as exc:
                    last_error = KbDocumentReadError(
                        f"HTTP error calling {service_name}{path}: {exc}"
                    )
                    continue
                if response.is_success or response.status_code not in {502, 503, 504}:
                    return _payload_from_httpx_response(response)
            if last_error is not None:
                raise last_error
            raise KbDocumentReadError(
                f"Service request failed after retries: {service_name}{path}"
            )
    finally:
        await discovery_client.close()
        await redis_client.aclose()


def _payload_from_httpx_response(response: httpx.Response) -> Any:
    content_type = response.headers.get("content-type", "").lower()
    if content_type.startswith("application/json"):
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise KbDocumentReadError(
                "KB download service response must be JSON"
            ) from exc
    else:
        payload = response.content

    if response.is_success:
        return payload

    if isinstance(payload, dict):
        _extract_text(payload)
    raise KbDocumentReadError(
        f"HTTP {response.status_code} downloading KB document: "
        f"{_response_preview(payload)}"
    )


def _build_discovered_url(instance: Any, path: str) -> str:
    protocol = str(getattr(instance, "protocol", "") or "http").strip() or "http"
    path_segments: list[str] = []
    path_prefix = str(getattr(instance, "path_prefix", "") or "").strip("/")
    if path_prefix:
        path_segments.append(path_prefix)
    request_path = path.strip("/")
    if request_path:
        path_segments.append(request_path)
    suffix = "/".join(path_segments)
    base = f"{protocol}://{instance.host}:{instance.port}"
    return f"{base}/{suffix}" if suffix else base


def _extract_text(response_payload: Any) -> str:
    if isinstance(response_payload, bytes | bytearray | memoryview):
        return _decode_downloaded_bytes(bytes(response_payload))
    if isinstance(response_payload, str):
        json_payload = _try_parse_json_object(response_payload)
        if json_payload is not None:
            return _extract_content(json_payload)
        return response_payload
    if isinstance(response_payload, dict):
        return _extract_content(response_payload)
    raise KbDocumentReadError("KB download service response must be bytes or JSON")


def _decode_downloaded_bytes(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KbDocumentReadError(
            "KB downloaded document must be UTF-8 Markdown text"
        ) from exc


def _try_parse_json_object(value: str) -> dict[str, Any] | None:
    stripped = value.lstrip()
    if not stripped.startswith("{"):
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _response_preview(payload: Any) -> str:
    if isinstance(payload, bytes | bytearray | memoryview):
        return bytes(payload)[:200].decode("utf-8", errors="replace")
    return str(payload)[:200]


def _extract_content(response_body: dict[str, Any]) -> str:
    result_code = str(response_body.get("resultCode", "0")).strip()
    if result_code not in {"0", "200"}:
        message = str(response_body.get("resultMsg") or "KB document download failed")
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
