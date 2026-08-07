"""Service-discovery implementation of DocumentLibraryBackend."""

from __future__ import annotations

import inspect
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from datacloud_platform.backends.document_library import DocumentLibraryError
from datacloud_platform.models.document import MetadataSearchPage
from datacloud_platform.services.kb_document_reader import (
    DEFAULT_DOWNLOAD_FILE_PATH,
    GetBytes,
    KbDocumentReader,
    _build_discovered_url,
    _build_headers,
)

METADATA_SEARCH_PATH = "/byaiService/datasetController/knowledgeItems/metadataSearch"
KNOWLEDGE_ITEMS_SEARCH_PATH = "/byaiService/datasetController/knowledgeItems/search"
_TIMEOUT_SECONDS = 30.0
_ERROR_RESPONSE_PREVIEW_CHARS = 4000
PostJson = Callable[[str, dict[str, Any], dict[str, str]], object]


@dataclass(frozen=True, slots=True)
class ServiceDiscoveryDocumentLibraryBackend:
    """DocumentLibraryBackend implemented through runtime service discovery."""

    search_path: str = METADATA_SEARCH_PATH
    post_json: PostJson | None = None
    read_path: str = DEFAULT_DOWNLOAD_FILE_PATH
    get_bytes: GetBytes | None = None

    async def search_knowledge_item_metadata(
        self, *, payload: dict[str, Any]
    ) -> MetadataSearchPage:
        headers = _build_headers()
        if self.post_json is not None:
            response = self.post_json(self.search_path, payload, headers)
            raw: Any = await response if inspect.isawaitable(response) else response
        else:
            raw = await _post_by_discovery(
                service_name=os.getenv("BE_DOMAINNAME", "").strip(),
                path=self.search_path,
                payload=payload,
                headers=headers,
            )
        return _extract_page(raw)

    async def search(self, payload: dict[str, Any]) -> MetadataSearchPage:
        """Backward-compatible alias for the former service client."""
        return await self.search_knowledge_item_metadata(payload=payload)

    async def read_knowledge_document(self, *, resource_id: str, file_path: str) -> str:
        """Download one complete document using the established KB protocol."""
        return KbDocumentReader(
            read_path=self.read_path, get_bytes=self.get_bytes
        ).read_text(resource_id=resource_id, file_path=file_path)

    async def search_knowledge_items(
        self, *, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        """Search chunk-level knowledge items through the portal endpoint."""
        headers = _build_headers()
        if self.post_json is not None:
            response = self.post_json(KNOWLEDGE_ITEMS_SEARCH_PATH, payload, headers)
            raw: Any = await response if inspect.isawaitable(response) else response
        else:
            raw = await _post_by_discovery(
                service_name=os.getenv("BE_DOMAINNAME", "").strip(),
                path=KNOWLEDGE_ITEMS_SEARCH_PATH,
                payload=payload,
                headers=headers,
            )
        return _extract_knowledge_items(raw)


async def _post_by_discovery(
    *,
    service_name: str,
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> Any:
    if not service_name:
        raise DocumentLibraryError("BE_DOMAINNAME is required")
    try:
        from by_framework.core.discovery import DiscoveryClient  # noqa: PLC0415
        from datacloud_platform.redis_client import (  # noqa: PLC0415
            create_async_redis_client,
        )
    except ImportError as exc:
        raise DocumentLibraryError(
            f"service discovery dependencies are unavailable: path={path}"
        ) from exc

    redis_client = create_async_redis_client()
    discovery_client = DiscoveryClient(redis_client=redis_client, cache_interval=5)
    try:
        instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
        if not instance:
            raise DocumentLibraryError(
                f"No available instances for service: {service_name}"
            )
        url = _build_discovered_url(instance, path)
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS, headers=headers
        ) as client:
            response = await client.post(url, json=payload)
            try:
                response_payload: Any = response.json()
            except ValueError as exc:
                response_text = response.text
                if not response.is_success:
                    raise DocumentLibraryError(
                        _format_http_error(
                            path=path,
                            status_code=response.status_code,
                            response_payload=response_text,
                        )
                    ) from exc
                raise DocumentLibraryError(
                    f"response must be JSON: path={path} body={response_text[:_ERROR_RESPONSE_PREVIEW_CHARS]}"
                ) from exc
            if not response.is_success:
                raise DocumentLibraryError(
                    _format_http_error(
                        path=path,
                        status_code=response.status_code,
                        response_payload=response_payload,
                    )
                )
            return response_payload
    except httpx.HTTPError as exc:
        raise DocumentLibraryError(f"HTTP error calling path={path}: {exc}") from exc
    finally:
        await discovery_client.close()
        await redis_client.aclose()


def _format_http_error(*, path: str, status_code: int, response_payload: Any) -> str:
    if isinstance(response_payload, str):
        detail = response_payload
    else:
        detail = json.dumps(response_payload, ensure_ascii=False, default=str)
    detail = detail[:_ERROR_RESPONSE_PREVIEW_CHARS]
    return f"request failed: path={path} HTTP {status_code} response={detail}"


def _extract_page(payload: Any) -> MetadataSearchPage:
    if not isinstance(payload, dict):
        raise DocumentLibraryError("metadataSearch response must be an object")
    if "resultCode" in payload:
        result_code = str(payload.get("resultCode", ""))
        result_object = payload.get("resultObject")
        result_message = payload.get("resultMsg")
        succeeded = result_code in {"0", "200"}
    else:
        result_code = str(payload.get("code", ""))
        result_object = payload.get("data")
        result_message = payload.get("msg")
        succeeded = result_code in {"0", "200"} and payload.get("success") is not False
    if not succeeded:
        error_details = result_object if isinstance(result_object, dict) else {}
        message = str(result_message or "metadataSearch failed")
        if error_details:
            message = (
                f"{message}: "
                f"{json.dumps(error_details, ensure_ascii=False, sort_keys=True)}"
            )
        raise DocumentLibraryError(message)
    if not isinstance(result_object, dict):
        raise DocumentLibraryError("metadataSearch data must be an object")
    rows = result_object.get("data")
    if not isinstance(rows, list):
        raise DocumentLibraryError("metadataSearch data.data must be an array")
    return MetadataSearchPage(
        data=tuple(row for row in rows if isinstance(row, dict)),
        total=int(result_object.get("total") or 0),
        page_num=int(result_object.get("pageNum") or 1),
        page_size=int(result_object.get("pageSize") or len(rows) or 20),
    )


def _extract_knowledge_items(payload: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(payload, dict):
        raise DocumentLibraryError("knowledgeItems/search response must be an object")
    result_code = str(payload.get("code", payload.get("resultCode", "")))
    if result_code not in {"0", "200"}:
        message = str(
            payload.get("msg")
            or payload.get("resultMsg")
            or "knowledgeItems/search failed"
        )
        raise DocumentLibraryError(message)
    result_object = payload.get("data", payload.get("resultObject"))
    if not isinstance(result_object, dict):
        raise DocumentLibraryError("knowledgeItems/search data must be an object")
    rows = result_object.get("data")
    if not isinstance(rows, list):
        raise DocumentLibraryError("knowledgeItems/search data.data must be an array")
    return tuple(row for row in rows if isinstance(row, dict))
