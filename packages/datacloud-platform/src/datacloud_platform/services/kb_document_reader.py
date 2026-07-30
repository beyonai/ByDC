"""Download full Markdown documents from knowledge bases."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from threading import Thread
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

DEFAULT_DOWNLOAD_FILE_PATH = "/byaiService/datasetController/download"
DEFAULT_READ_FILE_PATH = DEFAULT_DOWNLOAD_FILE_PATH
_TIMEOUT_SECONDS = 30.0

GetBytes = Callable[[str, dict[str, Any], dict[str, str]], Any]


class KbDocumentReadError(RuntimeError):
    """Raised when the knowledge-base document cannot be read."""


@dataclass(frozen=True)
class KbDocumentReader:
    """Discovery-only client for ByClaw's knowledge document download API."""

    read_path: str = DEFAULT_READ_FILE_PATH
    get_bytes: GetBytes | None = None

    @property
    def service_name(self) -> str:
        """Resolve the only supported runtime service from BE_DOMAINNAME."""
        return _default_service_name()

    def read_text(
        self,
        *,
        resource_id: str,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Download one knowledge-base document as Markdown text."""
        _ = start_line, end_line
        normalized_resource_id = resource_id.strip()
        normalized_file_path = file_path.strip()
        if not normalized_resource_id:
            raise KbDocumentReadError("kb_resource_id is required")
        try:
            parsed_resource_id = int(normalized_resource_id)
        except ValueError as exc:
            raise KbDocumentReadError("kb_resource_id must be an integer") from exc
        if not normalized_file_path.startswith("/"):
            raise KbDocumentReadError("filePath must start with /")

        params: dict[str, Any] = {
            "resourceId": parsed_resource_id,
            "directoryPath": normalized_file_path,
        }

        headers = _build_headers()
        response_payload = self._get(params=params, headers=headers)
        content = _extract_text(response_payload)
        logger.info(
            "KB document download succeeded: resourceId=%s filePath=%s content_length=%d",
            normalized_resource_id,
            normalized_file_path,
            len(content),
        )
        return content

    def _get(self, *, params: dict[str, Any], headers: dict[str, str]) -> Any:
        if self.get_bytes is not None:
            return self.get_bytes(self.read_path, params, headers)
        service_name = self.service_name
        if not service_name:
            raise KbDocumentReadError("BE_DOMAINNAME is required")
        logger.info(
            "KB document download request: transport=discovery service_name=%s path=%s "
            "resourceId=%s filePath=%s has_token=%s",
            service_name,
            self.read_path,
            params.get("resourceId", ""),
            params.get("directoryPath", ""),
            bool(headers.get("Beyond-Token") or headers.get("beyond-token")),
        )
        return _run_async_in_thread(
            _download_by_discovery(
                service_name=service_name,
                path=self.read_path,
                params=params,
                headers=headers,
            )
        )


def build_default_kb_document_reader() -> KbDocumentReader:
    """Build the default Platform KB document reader from environment config."""
    return KbDocumentReader(read_path=DEFAULT_DOWNLOAD_FILE_PATH)


async def _download_by_discovery(
    *,
    service_name: str,
    path: str,
    params: dict[str, Any],
    headers: dict[str, str],
) -> Any:
    try:
        from by_framework.core.discovery import DiscoveryClient  # noqa: PLC0415
        from datacloud_platform.redis_client import (  # noqa: PLC0415
            create_async_redis_client,
        )
    except ImportError as exc:
        raise KbDocumentReadError(
            "KB download service discovery dependencies are unavailable"
        ) from exc

    redis_client = create_async_redis_client()
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
                    response = await client.get(url, params=params)
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
    result_code = str(
        response_body.get("code", response_body.get("resultCode", "0"))
    ).strip()
    if result_code not in {"0", "200"}:
        message = str(
            response_body.get("msg")
            or response_body.get("resultMsg")
            or "KB document download failed"
        )
        raise KbDocumentReadError(message)

    result_object = response_body.get("data", response_body.get("resultObject"))
    if not isinstance(result_object, dict):
        raise KbDocumentReadError("data must be a JSON object")

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


def _default_service_name() -> str:
    return os.getenv("BE_DOMAINNAME", "").strip()
