"""Knowledge-base action backend protocols and default HTTP implementation."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from datacloud_data_sdk.exceptions import DataSourceUnavailableError, KbExecutionError
from datacloud_data_sdk.utils.curl_logger import log_curl
from datacloud_data_sdk.utils.redis_discovery import (
    RedisDiscoveryConfig,
    init_redis_discovery,
    load_redis_discovery_config,
)

logger = logging.getLogger(__name__)

PROCESSING_METADATA_FIELDS: tuple[str, ...] = (
    "dc_status",
    "dc_failure_reason",
    "dc_failure_count",
)


def _filename_requires_rfc5987(filename: str) -> bool:
    """Return whether httpx would alter a meaningful filename character."""
    return '"' in filename or "\\" in filename


def _build_rfc5987_multipart(
    parts: list[tuple[str, Any]],
) -> tuple[bytes, str]:
    """Build multipart with an exact UTF-8 filename carried by filename*."""
    boundary = f"----ByClaw{secrets.token_hex(16)}"
    body = bytearray()

    for field_name, value in parts:
        if any(char in field_name for char in ('"', "\r", "\n")):
            raise ValueError("multipart field name contains unsupported characters")
        body.extend(f"--{boundary}\r\n".encode("ascii"))

        if isinstance(value, tuple) and value and value[0] is not None:
            filename, content, content_type = value[:3]
            if "\r" in filename or "\n" in filename:
                raise ValueError("filename cannot contain CR or LF")
            encoded_filename = quote(filename, safe="", encoding="utf-8")
            body.extend(
                (
                    f'Content-Disposition: form-data; name="{field_name}"; '
                    f'filename="upload.md"; filename*=UTF-8\'\'{encoded_filename}\r\n'
                ).encode("ascii")
            )
            body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("ascii"))
            body.extend(content)
        else:
            field_value = value[1] if isinstance(value, tuple) else value
            body.extend(
                f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode(
                    "ascii"
                )
            )
            body.extend(str(field_value).encode("utf-8"))
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("ascii"))
    return bytes(body), f"multipart/form-data; boundary={boundary}"


@dataclass(frozen=True)
class KnowledgeSearchRequest:
    """Structured request passed to knowledge-base search backends."""

    object_code: str
    datasource_alias: str
    query: str
    filters: dict[str, Any] = field(default_factory=dict)
    filter_relation: str = "AND"
    select: list[str] = field(default_factory=list)
    order_by: list[dict[str, Any]] = field(default_factory=list)
    limit: int = 10
    offset: int = 0
    kb_resource_id: str | None = None
    kb_resource_ids: list[str] = field(default_factory=list)
    kb_directory: str | None = None
    field_types: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeSearchResult:
    """Normalized knowledge-base search result."""

    records: list[dict[str, Any]]
    total: int
    meta: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        """Return the MCP/tool response payload shape."""
        return {"records": self.records, "total": self.total, "meta": self.meta}


class KnowledgeSearchBackend(Protocol):
    """Protocol for third-party knowledge-base search implementations."""

    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        """Execute a knowledge-base search request."""


@dataclass(frozen=True)
class KnowledgeFileNameSearchRequest:
    """Structured request for chunk-level search constrained by a file name."""

    object_code: str
    datasource_alias: str
    query: str
    file_name: str
    kb_resource_id: str | None = None
    kb_directory: str | None = None
    metadata_field_list: list[str] = field(default_factory=list)
    limit: int = 20


class KnowledgeFileNameSearchBackend(Protocol):
    """Protocol for file-name constrained chunk search implementations."""

    async def search_by_file_name(
        self,
        request: KnowledgeFileNameSearchRequest,
    ) -> KnowledgeSearchResult:
        """Execute a file-name constrained chunk-level search request."""


@dataclass(frozen=True)
class KnowledgeWriteRequest:
    """Structured request passed to knowledge-base write backends."""

    object_code: str
    datasource_alias: str
    kb_resource_id: str
    kb_id: str | None
    file_path: str
    content: str
    labels: dict[str, Any] = field(default_factory=dict)
    file_description: str = ""
    kb_directory: str | None = None
    metadata_properties: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class KnowledgeWriteResult:
    """Normalized knowledge-base write result."""

    records: list[dict[str, Any]]
    total: int
    meta: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        """Return the MCP/tool response payload shape."""
        return {"records": self.records, "total": self.total, "meta": self.meta}


class KnowledgeWriteBackend(Protocol):
    """Protocol for third-party knowledge-base write implementations."""

    async def write(self, request: KnowledgeWriteRequest) -> KnowledgeWriteResult:
        """Write a document into a knowledge base."""


@dataclass(frozen=True)
class KnowledgeUpdateRequest:
    """Structured request for in-place update of an existing knowledge-base document."""

    object_code: str
    datasource_alias: str
    kb_resource_id: str
    kb_id: str | None
    file_path: str
    content: str
    labels: dict[str, Any] = field(default_factory=dict)
    file_description: str = ""
    kb_directory: str | None = None
    metadata_properties: list[dict[str, Any]] = field(default_factory=list)
    clear_label_fields: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class KnowledgeUpdateResult:
    """Normalized result for an in-place knowledge-base document update."""

    records: list[dict[str, Any]]
    total: int
    meta: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        """Return the MCP/tool response payload shape."""
        return {"records": self.records, "total": self.total, "meta": self.meta}


class KnowledgeUpdateBackend(Protocol):
    """Protocol for in-place knowledge-base document update implementations."""

    async def update(self, request: KnowledgeUpdateRequest) -> KnowledgeUpdateResult:
        """Update an existing document in a knowledge base without delete + re-import."""


@dataclass(frozen=True)
class KnowledgeDeleteRequest:
    """Structured request for deleting documents from a knowledge base."""

    object_code: str
    datasource_alias: str
    kb_resource_id: str
    file_paths: list[str]
    kb_directory: str | None = None


@dataclass(frozen=True)
class KnowledgeDeleteResult:
    """Normalized result for a knowledge-base document deletion."""

    deleted_paths: list[str]
    meta: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        """Return the MCP/tool response payload shape."""
        return {
            "records": [{"filePath": p} for p in self.deleted_paths],
            "total": len(self.deleted_paths),
            "meta": self.meta,
        }


class KnowledgeDeleteBackend(Protocol):
    """Protocol for knowledge-base document deletion implementations."""

    async def delete_files(self, request: KnowledgeDeleteRequest) -> KnowledgeDeleteResult:
        """Delete one or more documents from a knowledge base."""


@dataclass(frozen=True)
class KnowledgeFileMetadataRequest:
    """Structured request for fetching a single file's metadata from the knowledge base."""

    object_code: str
    datasource_alias: str
    kb_resource_id: str
    file_path: str
    kb_directory: str | None = None


@dataclass(frozen=True)
class KnowledgeFileMetadata:
    """Metadata record for a single knowledge-base file."""

    file_path: str
    labels: dict[str, Any] = field(default_factory=dict)
    exists: bool = True


class HttpKnowledgeSearchBackend:
    """Discovery-only backend for ByClaw DatasetController knowledge APIs."""

    _default_redis_config: RedisDiscoveryConfig | None = None

    def __init__(
        self,
        kb_configs: dict[str, Any] | None = None,
        redis_config: RedisDiscoveryConfig | None = None,
    ) -> None:
        self._configs = kb_configs or {}
        self._redis_config = (
            redis_config or self.__class__._default_redis_config or load_redis_discovery_config()
        )

    @classmethod
    def configure_default_redis(cls, redis_config: RedisDiscoveryConfig | None) -> None:
        """Configure default Redis discovery settings for registry-created instances."""
        cls._default_redis_config = redis_config

    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        """Search files through ByClaw's DatasetController."""
        config = self._get_config(request.datasource_alias)
        body: dict[str, Any] = {
            "resourceIdList": self._require_resource_ids(request),
            "query": request.query,
            "topK": request.limit,
            "searchMode": str(
                config.get("searchMode") or config.get("search_mode") or "mixedRecall"
            ),
        }
        where = _filters_to_where(request.filters, request.filter_relation, request.field_types)
        where = _with_kb_directory_filter(where, request.kb_directory)
        if where:
            body["where"] = where

        metadata_field_list = _with_processing_metadata_fields(
            request.select
            or _coerce_string_list(
                config.get("metadataFieldList") or config.get("metadata_field_list")
            )
        )
        body["metadataFieldList"] = metadata_field_list

        data = await self._post_json_by_discovery(
            service_name=self._resolve_service_name(config, request.datasource_alias),
            path=self._build_search_file_path(config),
            body=body,
            datasource_alias=request.datasource_alias,
        )

        records = self._normalize_records(self._extract_raw_records(data, request.datasource_alias))
        return KnowledgeSearchResult(
            records=records,
            total=len(records),
            meta={
                "object_code": request.object_code,
                "datasource_alias": request.datasource_alias,
                "query": request.query,
            },
        )

    async def search_by_file_name(
        self,
        request: KnowledgeFileNameSearchRequest,
    ) -> KnowledgeSearchResult:
        """Search chunks through ByClaw, constrained by directory and file name."""
        config = self._get_config(request.datasource_alias)
        body: dict[str, Any] = {
            "resourceIdList": [
                self._require_resource_id(
                    request.kb_resource_id,
                    request.datasource_alias,
                )
            ],
            "query": request.query,
            "topK": request.limit,
            "searchMode": str(
                config.get("searchMode") or config.get("search_mode") or "mixedRecall"
            ),
        }
        where = _with_kb_directory_filter({}, request.kb_directory)
        where = _with_file_name_filter(where, request.file_name)
        if where:
            body["where"] = where
        body["metadataFieldList"] = _with_processing_metadata_fields(request.metadata_field_list)

        data = await self._post_json_by_discovery(
            service_name=self._resolve_service_name(config, request.datasource_alias),
            path=self._build_chunk_search_path(config),
            body=body,
            datasource_alias=request.datasource_alias,
        )

        records = _aggregate_content_by_file(
            self._normalize_records(self._extract_raw_records(data, request.datasource_alias))
        )
        return KnowledgeSearchResult(
            records=records,
            total=len(records),
            meta={
                "object_code": request.object_code,
                "datasource_alias": request.datasource_alias,
                "query": request.query,
            },
        )

    async def write(self, request: KnowledgeWriteRequest) -> KnowledgeWriteResult:
        """Upload a Markdown document through ByClaw and trigger its build."""
        config = self._get_config(request.datasource_alias)
        self._require_resource_id(request.kb_resource_id, request.datasource_alias)
        markdown_file_path = _to_markdown_file_path(request.file_path, request.kb_directory)

        # Merge relation info parsed from --- related_docs --- fenced blocks into labels.
        related_docs = _parse_related_docs(request.content)
        effective_labels = _merge_related_docs_into_labels(request.labels, related_docs)

        # Strip the --- related_docs --- blocks from content before uploading.
        clean_content = _strip_related_docs_blocks(request.content)
        # Strip any leading YAML front matter (--- ... ---) so it is not duplicated.
        clean_content = _strip_front_matter(clean_content)
        file_content = _render_markdown_with_front_matter(effective_labels, clean_content)
        filename = PurePosixPath(markdown_file_path).name or "document.md"
        try:
            build_body = await self._write_by_discovery(
                service_name=self._resolve_service_name(
                    config,
                    request.datasource_alias,
                ),
                config=config,
                request=request,
                filename=filename,
                file_content=file_content,
                markdown_file_path=markdown_file_path,
            )
        except httpx.HTTPError as exc:
            raise KbExecutionError(request.datasource_alias, str(exc)) from exc

        record = {
            **effective_labels,
            "knCode": str(request.kb_resource_id),
            "filePath": markdown_file_path,
            "content": request.content,
        }
        if request.file_description:
            record["fileDescription"] = request.file_description
        return KnowledgeWriteResult(
            records=[record],
            total=1,
            meta={
                "object_code": request.object_code,
                "datasource_alias": request.datasource_alias,
                "build": _result_summary(build_body),
            },
        )

    async def update(self, request: KnowledgeUpdateRequest) -> KnowledgeUpdateResult:
        """Update an existing document through ByClaw and trigger its build."""
        config = self._get_config(request.datasource_alias)
        self._require_resource_id(request.kb_resource_id, request.datasource_alias)
        markdown_file_path = _to_markdown_file_path(request.file_path, request.kb_directory)

        related_docs = _parse_related_docs(request.content)
        effective_labels = _merge_related_docs_into_labels(request.labels, related_docs)
        clean_content = _strip_related_docs_blocks(request.content)
        clean_content = _strip_front_matter(clean_content)
        file_content = _render_markdown_with_front_matter(
            effective_labels,
            clean_content,
            clear_label_fields=request.clear_label_fields,
        )
        filename = PurePosixPath(markdown_file_path).name or "document.md"

        try:
            await self._update_by_discovery(
                service_name=self._resolve_service_name(
                    config,
                    request.datasource_alias,
                ),
                config=config,
                request=request,
                filename=filename,
                file_content=file_content,
                markdown_file_path=markdown_file_path,
            )
        except httpx.HTTPError as exc:
            raise KbExecutionError(request.datasource_alias, str(exc)) from exc

        record: dict[str, Any] = {
            **effective_labels,
            "knCode": str(request.kb_resource_id),
            "filePath": markdown_file_path,
            "content": request.content,
        }
        if request.file_description:
            record["fileDescription"] = request.file_description
        return KnowledgeUpdateResult(
            records=[record],
            total=1,
            meta={
                "object_code": request.object_code,
                "datasource_alias": request.datasource_alias,
            },
        )

    async def delete_files(self, request: KnowledgeDeleteRequest) -> KnowledgeDeleteResult:
        """Delete one or more documents through ByClaw."""
        config = self._get_config(request.datasource_alias)
        self._require_resource_id(request.kb_resource_id, request.datasource_alias)
        deleted: list[str] = []

        for file_path in request.file_paths:
            markdown_file_path = _to_markdown_file_path(file_path, request.kb_directory)
            await self._delete_file_by_discovery(
                service_name=self._resolve_service_name(
                    config,
                    request.datasource_alias,
                ),
                config=config,
                datasource_alias=request.datasource_alias,
                kb_resource_id=request.kb_resource_id,
                markdown_file_path=markdown_file_path,
            )
            deleted.append(markdown_file_path)

        return KnowledgeDeleteResult(
            deleted_paths=deleted,
            meta={
                "object_code": request.object_code,
                "datasource_alias": request.datasource_alias,
            },
        )

    async def _delete_file_by_discovery(
        self,
        *,
        service_name: str,
        config: dict[str, Any],
        datasource_alias: str,
        kb_resource_id: str,
        markdown_file_path: str,
    ) -> None:
        """Delete a single document via service-discovery."""
        try:
            from by_framework.core.discovery import DiscoveryClient
            from by_framework.util.discovery_http_client import DiscoveryHttpClient
            from by_framework.util.http_client import RetryConfig
        except ImportError as exc:
            raise KbExecutionError(
                datasource_alias,
                "redis service discovery requires by_framework dependency",
            ) from exc

        init_redis_discovery(self._redis_config)
        discovery_client = DiscoveryClient(cache_interval=5)
        retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
        try:
            instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
            if not instance:
                raise KbExecutionError(
                    datasource_alias,
                    f"knowledge service instance not found: {service_name}",
                )
            json_headers = {
                **self._build_discovery_headers(instance),
                **self._get_beyond_token_header(),
            }
            delete_path = self._build_delete_path(config)
            delete_body = {
                "resourceId": self._require_resource_id(
                    kb_resource_id,
                    datasource_alias,
                ),
                "directoryPath": markdown_file_path,
            }
            async with DiscoveryHttpClient(
                discovery_client,
                retry_config=retry_config,
                health_threshold_ms=-1,
            ) as client:
                log_curl("POST", delete_path, body=delete_body)
                resp = await client.post(
                    service_name, delete_path, headers=json_headers, json=delete_body
                )
                body = self._parse_discovery_response_body(resp, datasource_alias)
                self._ensure_success(body, datasource_alias)
        finally:
            await discovery_client.close()

    async def get_file_metadata(
        self, request: KnowledgeFileMetadataRequest
    ) -> KnowledgeFileMetadata | None:
        """Fetch a single file's metadata through ByClaw."""
        config = self._get_config(request.datasource_alias)
        markdown_file_path = _to_markdown_file_path(request.file_path, request.kb_directory)

        body: dict[str, Any] = {
            "resourceId": self._require_resource_id(
                request.kb_resource_id,
                request.datasource_alias,
            ),
            "filePath": markdown_file_path,
        }

        data = await self._post_json_by_discovery(
            service_name=self._resolve_service_name(
                config,
                request.datasource_alias,
            ),
            path=self._build_metadata_get_path(config),
            body=body,
            datasource_alias=request.datasource_alias,
        )
        if data.get("code") not in ("0", 0):
            logger.debug(
                "get_file_metadata: file not found code=%s path=%s",
                data.get("code"),
                markdown_file_path,
            )
            return KnowledgeFileMetadata(file_path=markdown_file_path, exists=False)

        result_object = data.get("data")
        if not isinstance(result_object, dict):
            return KnowledgeFileMetadata(file_path=markdown_file_path, exists=False)

        raw_metadata = result_object.get("metadata")
        if not isinstance(raw_metadata, dict):
            # resultObject 存在但 metadata 为空，文件存在但无元数据
            return KnowledgeFileMetadata(file_path=markdown_file_path, exists=True)

        # 响应格式：{"field": {"valueType": "string", "value": ...}}
        labels = {k: v.get("value") if isinstance(v, dict) else v for k, v in raw_metadata.items()}
        return KnowledgeFileMetadata(file_path=markdown_file_path, labels=labels, exists=True)

    @staticmethod
    def _build_glob_path(config: dict[str, Any]) -> str:
        _ = config
        return "/byaiService/datasetController/glob"

    @staticmethod
    def _build_metadata_get_path(config: dict[str, Any]) -> str:
        _ = config
        return "/byaiService/datasetController/knowledgeItems/metadata/get"

    async def _update_by_discovery(
        self,
        *,
        service_name: str,
        config: dict[str, Any],
        request: KnowledgeUpdateRequest,
        filename: str,
        file_content: str,
        markdown_file_path: str,
    ) -> None:
        try:
            from by_framework.core.discovery import DiscoveryClient
            from by_framework.util.discovery_http_client import DiscoveryHttpClient
            from by_framework.util.http_client import RetryConfig
        except ImportError as exc:
            raise KbExecutionError(
                request.datasource_alias,
                "redis service discovery requires by_framework dependency",
            ) from exc

        init_redis_discovery(self._redis_config)
        discovery_client = DiscoveryClient(cache_interval=5)
        retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
        try:
            instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
            if not instance:
                raise KbExecutionError(
                    request.datasource_alias,
                    f"knowledge service instance not found: {service_name}",
                )
            json_headers = {
                **self._build_discovery_headers(instance),
                **self._get_beyond_token_header(),
            }
            upload_headers = {
                **self._build_discovery_upload_headers(instance),
                **self._get_beyond_token_header(),
            }
            async with DiscoveryHttpClient(
                discovery_client,
                retry_config=retry_config,
                health_threshold_ms=-1,
            ) as client:
                update_path = self._build_update_path(config)
                file_bytes = file_content.encode("utf-8")
                resource_id = str(
                    self._require_resource_id(
                        request.kb_resource_id,
                        request.datasource_alias,
                    )
                )
                parts: list[tuple[str, Any]] = [
                    ("resourceId", (None, resource_id)),
                    ("filePath", (None, markdown_file_path)),
                    (
                        "fileContent",
                        (filename, file_bytes, "text/markdown; charset=utf-8"),
                    ),
                    ("processFrontMatter", (None, "true")),
                ]
                if request.file_description:
                    parts.append(("fileDescription", (None, request.file_description)))
                log_curl(
                    "UPLOAD",
                    update_path,
                    body={
                        "resourceId": resource_id,
                        "filePath": markdown_file_path,
                        "fileContent": f"@{filename}",
                    },
                )
                resp = await self._upload_by_discovery(
                    client, service_name, update_path, parts, filename, upload_headers
                )
                body = self._parse_discovery_response_body(resp, request.datasource_alias)
                self._ensure_success(body, request.datasource_alias)
                self._ensure_update_success(body, request.datasource_alias)
                await self._trigger_file_build_by_discovery(
                    client,
                    service_name,
                    config,
                    request,
                    markdown_file_path,
                    json_headers,
                )
        finally:
            await discovery_client.close()

    async def _trigger_file_build_by_discovery(
        self,
        client: Any,
        service_name: str,
        config: dict[str, Any],
        request: KnowledgeWriteRequest | KnowledgeUpdateRequest,
        file_path: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        build_url = self._build_file_to_markdown_index_path(config)
        build_body = {
            "resourceId": self._require_resource_id(
                request.kb_resource_id,
                request.datasource_alias,
            ),
            "directoryPath": file_path,
        }
        log_curl("POST", build_url, body=build_body)
        resp = await client.post(service_name, build_url, headers=headers, json=build_body)
        body = self._parse_discovery_response_body(resp, request.datasource_alias)
        self._ensure_success(body, request.datasource_alias)
        return body

    async def _file_exists_by_discovery(
        self,
        client: Any,
        service_name: str,
        config: dict[str, Any],
        kb_resource_id: str,
        markdown_file_path: str,
        datasource_alias: str,
        headers: dict[str, str],
    ) -> bool:
        """Return True if the file exists in the knowledge base via discovery glob."""
        glob_path = self._build_glob_path(config)
        path = PurePosixPath(markdown_file_path)
        path_rule = str(path) if str(path).startswith("/") else f"/{path}"
        body: dict[str, Any] = {
            "resourceId": self._require_resource_id(
                kb_resource_id,
                datasource_alias,
            ),
            "pathRule": path_rule,
        }
        log_curl("POST", glob_path, body=body)
        resp = await client.post(service_name, glob_path, headers=headers, json=body)
        data = self._parse_discovery_response_body(resp, datasource_alias)
        self._ensure_success(data, datasource_alias)
        items = data.get("data")
        return isinstance(items, list) and len(items) > 0

    async def _write_by_discovery(
        self,
        *,
        service_name: str,
        config: dict[str, Any],
        request: KnowledgeWriteRequest,
        filename: str,
        file_content: str,
        markdown_file_path: str,
    ) -> dict[str, Any]:
        try:
            from by_framework.core.discovery import DiscoveryClient
            from by_framework.util.discovery_http_client import DiscoveryHttpClient
            from by_framework.util.http_client import RetryConfig
        except ImportError as exc:
            raise KbExecutionError(
                request.datasource_alias,
                "redis service discovery requires by_framework dependency",
            ) from exc

        init_redis_discovery(self._redis_config)
        discovery_client = DiscoveryClient(cache_interval=5)
        retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
        try:
            instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
            if not instance:
                raise KbExecutionError(
                    request.datasource_alias,
                    f"knowledge service instance not found: {service_name}",
                )
            json_headers = {
                **self._build_discovery_headers(instance),
                **self._get_beyond_token_header(),
            }
            upload_headers = {
                **self._build_discovery_upload_headers(instance),
                **self._get_beyond_token_header(),
            }
            async with DiscoveryHttpClient(
                discovery_client,
                retry_config=retry_config,
                health_threshold_ms=-1,
            ) as client:
                file_exists = await self._file_exists_by_discovery(
                    client,
                    service_name,
                    config,
                    request.kb_resource_id,
                    markdown_file_path,
                    request.datasource_alias,
                    json_headers,
                )
                file_bytes = file_content.encode("utf-8")
                resource_id = str(
                    self._require_resource_id(
                        request.kb_resource_id,
                        request.datasource_alias,
                    )
                )
                if file_exists:
                    update_path = self._build_update_path(config)
                    log_curl(
                        "UPLOAD",
                        update_path,
                        body={
                            "resourceId": resource_id,
                            "filePath": markdown_file_path,
                            "fileContent": f"@{filename}",
                        },
                    )
                    parts: list[tuple[str, Any]] = [
                        ("resourceId", (None, resource_id)),
                        ("filePath", (None, markdown_file_path)),
                        (
                            "fileContent",
                            (filename, file_bytes, "text/markdown; charset=utf-8"),
                        ),
                        ("processFrontMatter", (None, "true")),
                    ]
                    if request.file_description:
                        parts.append(("fileDescription", (None, request.file_description)))
                    resp = await self._upload_by_discovery(
                        client, service_name, update_path, parts, filename, upload_headers
                    )
                else:
                    import_path = self._build_import_path(config)
                    directory_path = str(PurePosixPath(markdown_file_path).parent)
                    if not directory_path.startswith("/"):
                        directory_path = f"/{directory_path}"
                    log_curl(
                        "UPLOAD",
                        import_path,
                        body={
                            "resourceId": resource_id,
                            "directoryPath": directory_path,
                            "file": f"@{filename}",
                            "skipIfDuplicate": "true",
                        },
                    )
                    parts = [
                        ("resourceId", (None, resource_id)),
                        ("directoryPath", (None, directory_path)),
                        (
                            "files",
                            (filename, file_bytes, "text/markdown; charset=utf-8"),
                        ),
                        ("processFrontMatter", (None, "true")),
                        ("overwrite", (None, "false")),
                        ("skipIfDuplicate", (None, "true")),
                    ]
                    if request.file_description:
                        parts.append(("fileDescription", (None, request.file_description)))
                    resp = await self._upload_by_discovery(
                        client, service_name, import_path, parts, filename, upload_headers
                    )

                body = self._parse_discovery_response_body(resp, request.datasource_alias)
                self._ensure_success(body, request.datasource_alias)
                if file_exists:
                    self._ensure_update_success(body, request.datasource_alias)
                else:
                    self._ensure_upload_success(body, request.datasource_alias)
                return await self._trigger_file_build_by_discovery(
                    client,
                    service_name,
                    config,
                    request,
                    markdown_file_path,
                    json_headers,
                )
        finally:
            await discovery_client.close()

    @staticmethod
    def _parse_discovery_response_body(resp: Any, datasource_alias: str) -> dict[str, Any]:
        body = getattr(resp, "data", None)
        if not isinstance(body, dict):
            raise KbExecutionError(
                datasource_alias,
                "invalid discovery response: root is not object",
            )
        return body

    @staticmethod
    async def _upload_by_discovery(
        client: Any,
        service_name: str,
        path: str,
        parts: list[tuple[str, Any]],
        filename: str,
        headers: dict[str, str],
    ) -> Any:
        """Upload while preserving quotes/backslashes in multipart filenames."""
        if not _filename_requires_rfc5987(filename):
            return await client._upload_with_discovery(
                service_name, path, parts, headers=headers
            )

        body, content_type = _build_rfc5987_multipart(parts)
        request_headers = {**headers, "Content-Type": content_type}
        return await client._request_with_discovery(
            "POST",
            service_name,
            path,
            headers=request_headers,
            data=body,
        )

    @staticmethod
    def _ensure_success(body: dict[str, Any], datasource_alias: str) -> None:
        if body.get("code") not in ("0", 0):
            error_message = _format_error_message(body)
            logger.error(
                "knowledge backend request failed: datasource_alias=%s, error=%s, body=%s",
                datasource_alias,
                error_message,
                body,
            )
            raise KbExecutionError(datasource_alias, error_message)

    @staticmethod
    def _ensure_upload_success(body: dict[str, Any], datasource_alias: str) -> None:
        data = body.get("data")
        if not isinstance(data, dict):
            raise KbExecutionError(datasource_alias, "upload response data is missing")
        failed_items = data.get("failedItems")
        if isinstance(failed_items, list) and failed_items:
            errors = [
                str(item.get("error") or item.get("filePath") or "upload failed")
                for item in failed_items
                if isinstance(item, dict)
            ]
            raise KbExecutionError(
                datasource_alias,
                "; ".join(errors) or "upload failed",
            )
        upload_items = data.get("uploadItems")
        if not isinstance(upload_items, list) or not upload_items:
            raise KbExecutionError(datasource_alias, "uploadItems is empty")
        failed = [
            item for item in upload_items if isinstance(item, dict) and item.get("success") is False
        ]
        if failed:
            raise KbExecutionError(
                datasource_alias,
                str(failed[0].get("error") or "upload failed"),
            )

    @staticmethod
    def _ensure_update_success(body: dict[str, Any], datasource_alias: str) -> None:
        data = body.get("data")
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            raise KbExecutionError(datasource_alias, "update response data is empty")
        failed = [item for item in items if isinstance(item, dict) and item.get("success") is False]
        if failed:
            raise KbExecutionError(
                datasource_alias,
                str(failed[0].get("error") or "update failed"),
            )

    @staticmethod
    def _extract_raw_records(data: dict[str, Any], datasource_alias: str) -> Any:
        HttpKnowledgeSearchBackend._ensure_success(data, datasource_alias)
        result_object = data.get("data")
        if not isinstance(result_object, dict):
            return []
        return result_object.get("data")

    def _get_config(self, datasource_alias: str) -> dict[str, Any]:
        if not self._configs:
            return {}
        if datasource_alias not in self._configs:
            if _looks_like_single_backend_config(self._configs):
                return self._configs
            raise DataSourceUnavailableError(datasource_alias)
        config = self._configs[datasource_alias]
        if not isinstance(config, dict):
            raise DataSourceUnavailableError(datasource_alias)
        return config

    @staticmethod
    def _resolve_service_name(config: dict[str, Any], datasource_alias: str) -> str:
        _ = config
        env_service_name = _first_non_empty_str(os.getenv("BE_DOMAINNAME"))
        if env_service_name:
            return env_service_name
        raise KbExecutionError(datasource_alias, "BE_DOMAINNAME is required")

    @staticmethod
    def _require_resource_id(resource_id: Any, datasource_alias: str) -> int:
        value = str(resource_id or "").strip()
        if not value:
            raise KbExecutionError(datasource_alias, "kb_resource_id is required")
        try:
            return int(value)
        except ValueError as exc:
            raise KbExecutionError(
                datasource_alias,
                "kb_resource_id must be an integer",
            ) from exc

    @classmethod
    def _require_resource_ids(cls, request: KnowledgeSearchRequest) -> list[int]:
        raw_ids = request.kb_resource_ids or (
            [request.kb_resource_id] if request.kb_resource_id else []
        )
        if not raw_ids:
            raise KbExecutionError(
                request.datasource_alias,
                "kb_resource_id is required",
            )
        return [
            cls._require_resource_id(resource_id, request.datasource_alias)
            for resource_id in raw_ids
        ]

    @staticmethod
    def _build_search_file_path(config: dict[str, Any]) -> str:
        _ = config
        return "/byaiService/datasetController/knowledgeItems/searchFile"

    @staticmethod
    def _build_chunk_search_path(config: dict[str, Any]) -> str:
        _ = config
        return "/byaiService/datasetController/knowledgeItems/search"

    @staticmethod
    def _build_import_path(config: dict[str, Any]) -> str:
        _ = config
        return "/byaiService/datasetController/uploadFiles"

    @staticmethod
    def _build_delete_path(config: dict[str, Any]) -> str:
        _ = config
        return "/byaiService/datasetController/removeFile"

    @staticmethod
    def _build_file_to_markdown_index_path(config: dict[str, Any]) -> str:
        _ = config
        return "/byaiService/datasetController/build"

    @staticmethod
    def _build_discovery_headers(
        instance: Any,
    ) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        metadata = getattr(instance, "metadata", None)
        if isinstance(metadata, dict):
            token = metadata.get("token")
            if isinstance(token, str) and token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _build_discovery_upload_headers(instance: Any) -> dict[str, str]:
        headers: dict[str, str] = {}
        metadata = getattr(instance, "metadata", None)
        if isinstance(metadata, dict):
            token = metadata.get("token")
            if isinstance(token, str) and token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _get_beyond_token_header() -> dict[str, str]:
        """Return Beyond-Token header from the current InvocationContext, or empty dict.

        兜底：context 无 token 时回退到 BEYOND_TOKEN 环境变量（平台 RPC 路径
        context 未注入 token，与 kb_document_reader._build_headers 行为对齐）。
        """
        try:
            from datacloud_data_sdk.context import get_current_context  # type: ignore[import]

            token = get_current_context().token
            if token:
                return {"Beyond-Token": token}
        except Exception:  # noqa: BLE001
            pass
        token = os.getenv("BEYOND_TOKEN", "")
        if token:
            return {"Beyond-Token": token}
        return {}

    @staticmethod
    def _mask_token(token: str) -> str:
        """Return first 4 + last 4 chars of token with middle masked, or <empty>."""
        if not token:
            return "<empty>"
        if len(token) <= 8:
            return "***"
        return f"{token[:4]}...{token[-4:]}"

    async def _post_json_by_discovery(
        self,
        *,
        service_name: str,
        path: str,
        body: dict[str, Any],
        datasource_alias: str,
    ) -> dict[str, Any]:
        try:
            from by_framework.core.discovery import DiscoveryClient
            from by_framework.util.discovery_http_client import DiscoveryHttpClient
            from by_framework.util.http_client import RetryConfig
        except ImportError as exc:
            raise KbExecutionError(
                datasource_alias,
                "redis service discovery requires by_framework dependency",
            ) from exc

        init_redis_discovery(self._redis_config)
        discovery_client = DiscoveryClient(cache_interval=5)
        retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
        try:
            instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
            if not instance:
                raise KbExecutionError(
                    datasource_alias,
                    f"knowledge service instance not found: {service_name}",
                )
            _beyond_header = self._get_beyond_token_header()
            headers = {**self._build_discovery_headers(instance), **_beyond_header}
            logger.info(
                "[kb-backend] POST (discovery) service=%s path=%s datasource=%s beyond_token=%s",
                service_name,
                path,
                datasource_alias,
                self._mask_token(_beyond_header.get("Beyond-Token", "")),
            )
            async with DiscoveryHttpClient(
                discovery_client,
                retry_config=retry_config,
                health_threshold_ms=-1,
            ) as client:
                log_curl("POST", path, body=body)
                response = await client.post(
                    service_name,
                    path,
                    headers=headers,
                    json=body,
                )
        finally:
            await discovery_client.close()

        logger.info(
            "[kb-backend] POST (discovery) service=%s path=%s datasource=%s done",
            service_name,
            path,
            datasource_alias,
        )
        return self._parse_discovery_response_body(response, datasource_alias)

    @staticmethod
    def _build_update_path(config: dict[str, Any]) -> str:
        _ = config
        return "/byaiService/datasetController/knowledgeItems/update"

    @staticmethod
    def _normalize_records(results: Any) -> list[dict[str, Any]]:
        if not isinstance(results, list):
            return []

        records: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            record: dict[str, Any] = {}
            for key in (
                "knCode",
                "filePath",
                "chunkId",
                "chunkNo",
                "chunkText",
                "startLine",
                "endLine",
            ):
                if key in item:
                    record[key] = item[key]
            content = item.get("content", item.get("chunkText", ""))
            if content:
                record["content"] = content
            if "score" in item:
                record["score"] = item["score"]
            metadata = item.get("metadata")
            if isinstance(metadata, dict):
                record.update(_flatten_metadata(metadata))
            records.append(record)
        return records


def _coerce_string_list(value: Any) -> list[str]:
    """Normalize metadata API list-like config values."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _with_processing_metadata_fields(fields: list[str]) -> list[str]:
    """补齐文档处理内置标签，并保持业务字段的原始顺序。"""
    return list(dict.fromkeys([*fields, *PROCESSING_METADATA_FIELDS]))


def _looks_like_single_backend_config(config: dict[str, Any]) -> bool:
    return any(
        key in config
        for key in (
            "url",
            "endpoint",
            "endpoint_url",
            "service_name",
            "serviceName",
            "search_file_url",
            "searchFileUrl",
            "import_url",
            "importUrl",
            "kb_resource_id",
            "kbResourceId",
        )
    )


def _flatten_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Flatten metadata service field envelopes to plain record columns."""
    flattened: dict[str, Any] = {}
    for key, raw_value in metadata.items():
        if isinstance(raw_value, dict) and "value" in raw_value:
            flattened[key] = raw_value.get("value")
        else:
            flattened[key] = raw_value
    return flattened


def _aggregate_content_by_file(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate chunk text into one record per file while preserving record attributes."""
    aggregated: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        key = str(record.get("filePath") or record.get("knCode") or len(order))
        if key not in aggregated:
            aggregated[key] = dict(record)
            order.append(key)
        else:
            aggregated[key].update({k: v for k, v in record.items() if k not in {"content"}})

        content = str(record.get("content") or "")
        if not content:
            continue
        existing_content = str(aggregated[key].get("content") or "")
        if not existing_content:
            aggregated[key]["content"] = content
        elif content not in existing_content:
            aggregated[key]["content"] = f"{existing_content}\n\n{content}"
    return [aggregated[key] for key in order]


def _first_non_empty_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _result_summary(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": body.get("code"),
        "msg": body.get("msg"),
    }


def _format_error_message(body: dict[str, Any]) -> str:
    message = str(
        body.get("msg")
        or body.get("code")
        or body.get("resultMsg")
        or body.get("resultCode")
        or "request failed"
    )
    result_object = body.get("resultObject")
    if isinstance(result_object, dict):
        error_code = result_object.get("errorCode")
        if error_code:
            message = f"{error_code}: {message}"

        errors = result_object.get("errors")
        error_list = result_object.get("errorList")
        error_lines = [
            *_format_validation_errors(errors),
            *_format_dsl_error_list(error_list),
        ]
        if error_lines:
            message = f"{message}; {', '.join(error_lines)}"
    return message


def _format_validation_errors(errors: Any) -> list[str]:
    if not isinstance(errors, list):
        return []

    error_lines: list[str] = []
    for item in errors:
        if not isinstance(item, dict):
            error_lines.append(str(item))
            continue
        location = item.get("loc")
        location_text = (
            ".".join(str(part) for part in location) if isinstance(location, list) else ""
        )
        detail = str(item.get("msg") or item.get("type") or "unknown error")
        if location_text:
            error_lines.append(f"{location_text}: {detail}")
        else:
            error_lines.append(detail)
    return error_lines


def _format_dsl_error_list(error_list: Any) -> list[str]:
    if not isinstance(error_list, list):
        return []

    error_lines: list[str] = []
    for item in error_list:
        if not isinstance(item, dict):
            error_lines.append(str(item))
            continue

        path = str(item.get("path") or "")
        code = str(item.get("code") or "")
        detail = str(item.get("message") or "unknown error")
        if path and code:
            error_lines.append(f"{path} [{code}]: {detail}")
        elif path:
            error_lines.append(f"{path}: {detail}")
        elif code:
            error_lines.append(f"{code}: {detail}")
        else:
            error_lines.append(detail)
    return error_lines


def _to_markdown_file_path(file_path: str, kb_directory: str | None = None) -> str:
    """Convert source file path to the Markdown path imported into knowledge base."""
    path = PurePosixPath(file_path)
    filename = (path.name or "document.md").rsplit(".", 1)[0] + ".md"
    if not kb_directory:
        if not path.name:
            return "/document.md" if file_path.startswith("/") else "document.md"
        return str(path.with_name(filename))
    directory = PurePosixPath(kb_directory)
    return str(directory / filename)


_RELATED_DOCS_BLOCK_RE = re.compile(
    r"---\s*related_docs\s*---(.*?)---\s*related_docs\s*---",
    re.DOTALL,
)

# Matches a YAML front matter block at the very start of a document.
_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\r?\n.*?^---[ \t]*\r?\n?", re.DOTALL | re.MULTILINE)


def _parse_related_docs(content: str) -> list[dict[str, str]]:
    """Extract all entries from ``--- related_docs ---`` fenced blocks.

    Returns a list of ``{target_doc_id, relation, kb_resource_id}`` dicts, e.g.::

        [
            {
                "target_doc_id": "Concept/Skill.md",
                "relation": "maps-to",
                "kb_resource_id": "12",
            },
        ]
    """
    import yaml  # lazy import — optional dependency

    entries: list[dict[str, str]] = []
    for block_text in _RELATED_DOCS_BLOCK_RE.findall(content):
        try:
            parsed = yaml.safe_load(block_text)
        except yaml.YAMLError:
            logger.warning("related_docs block YAML parse error — skipping")
            continue
        if not isinstance(parsed, dict):
            continue
        related_docs = parsed.get("related_docs")
        if not isinstance(related_docs, list):
            continue
        for item in related_docs:
            if not isinstance(item, dict):
                continue
            target = str(item.get("target_doc_id") or "").strip()
            # 处理 /.sessions?/<session_id>/<path> 格式，提取 session_id 并规范化路径
            match = re.search(r"/\.sessions?/(\d+)/(.*)", target)
            if match:
                parts = [p for p in match.group(2).split("/") if p]
                target = "/" + "/".join(parts[-2:] if len(parts) > 2 else parts)
            relation = str(item.get("relation") or "").strip()
            kb_id = str(item.get("kb_resource_id") or "").strip()
            if target and relation:
                entries.append(
                    {"target_doc_id": target, "relation": relation, "kb_resource_id": kb_id}
                )
    return entries


def _strip_related_docs_blocks(content: str) -> str:
    """Remove all ``--- related_docs ---`` fenced blocks from *content*.

    Trims any trailing blank lines left behind so the result ends cleanly.
    """
    stripped = _RELATED_DOCS_BLOCK_RE.sub("", content)
    # Collapse runs of 3+ newlines down to 2 (one blank line)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped.rstrip()


def _strip_front_matter(content: str) -> str:
    """Remove a leading YAML front matter block (``--- ... ---``) from *content*."""
    return _FRONT_MATTER_RE.sub("", content, count=1).lstrip("\n")


def _related_doc_id_to_term(target_doc_id: str) -> tuple[str, str]:
    """Split ``Type/Name.md`` into ``(type_code, term_name)``.

    Examples::

        "Concept/Skill.md" → ("Concept", "Skill")
        "Product/byDC.md"  → ("Product", "byDC")
        "Skill"            → ("", "Skill")
    """
    path = PurePosixPath(target_doc_id)
    term_name = path.stem or target_doc_id
    # Use the parent directory name as the type code (ignore root "/")
    parent = path.parent
    type_code = parent.name if parent.name and parent.name != "." else ""
    return type_code, term_name


def _merge_related_docs_into_labels(
    labels: dict[str, Any],
    related_docs: list[dict[str, str]],
) -> dict[str, Any]:
    """Merge ``related_docs`` entries into *labels* as flat relation keys.

    Each relation name becomes a top-level key whose value is a list of
    ``target_doc_id`` strings, mirroring the existing front-matter convention::

        maps-to:
          - Concept/Skill.md
          - Concept/Agent.md
        part-of:
          - Concept/本体库.md

    Existing relation keys in *labels* are preserved; new targets are appended.
    """
    if not related_docs:
        return labels

    merged = dict(labels)
    for entry in related_docs:
        relation = entry["relation"]
        target = entry["kb_resource_id"] + entry["target_doc_id"]
        bucket = merged.get(relation)
        if not isinstance(bucket, list):
            bucket = [bucket] if bucket is not None else []
            merged[relation] = bucket
        if target not in bucket:
            bucket.append(target)

    return merged


def _render_markdown_with_front_matter(
    labels: dict[str, Any],
    content: str,
    *,
    clear_label_fields: set[str] | None = None,
) -> str:
    """Render labels as YAML front matter before Markdown content."""
    explicit_empty_fields = clear_label_fields or set()
    front_matter_labels = {
        key: value
        for key, value in labels.items()
        if str(key) in explicit_empty_fields or not _is_empty_front_matter_value(value)
    }
    if not front_matter_labels:
        return content
    lines = ["---"]
    for key, value in front_matter_labels.items():
        lines.extend(_yaml_lines(str(key), value))
    lines.append("---")
    lines.append("")
    lines.append(content)
    return "\n".join(lines)


def _is_empty_front_matter_value(value: Any) -> bool:
    """Return whether a label value should be omitted from YAML front matter."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return not value
    return False


def _yaml_lines(key: str, value: Any) -> list[str]:
    if isinstance(value, list):
        lines = [f"{key}:"]
        for item in value:
            lines.append(f"  - {_yaml_scalar(item)}")
        return lines
    return [f"{key}: {_yaml_scalar(value)}"]


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


_SYSTEM_FIELD_TYPES: dict[str, str] = {
    "fileName": "string",
    "fileType": "string",
    "fileSize": "number",
    "mimeType": "string",
    "filePath": "string",
    "createdAt": "datetime",
    "updatedAt": "datetime",
}


def _filters_to_where(
    filters: dict[str, Any],
    filter_relation: str,
    field_types: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compile query-style filters to metadata API ``where`` AST."""
    if not filters:
        return {}

    nodes: list[dict[str, Any]] = []
    for field_name, raw_filter in filters.items():
        node = _filter_to_where_node(str(field_name), raw_filter, field_types or {})
        if node:
            nodes.append(node)

    if not nodes:
        return {}
    if len(nodes) == 1:
        return nodes[0]
    relation = "or" if filter_relation.upper() == "OR" else "and"
    return {relation: nodes}


def _merge_where_nodes(*nodes: dict[str, Any]) -> dict[str, Any]:
    valid_nodes = [node for node in nodes if isinstance(node, dict) and node]
    if not valid_nodes:
        return {}
    if len(valid_nodes) == 1:
        return valid_nodes[0]

    merged: list[dict[str, Any]] = []
    for node in valid_nodes:
        if isinstance(node.get("and"), list):
            merged.extend(node["and"])
        else:
            merged.append(node)
    return {"and": merged}


def _with_kb_directory_filter(where: dict[str, Any], kb_directory: str | None) -> dict[str, Any]:
    """Add the object's knowledge-base directory constraint to the metadata where AST."""
    directory_prefix = _kb_directory_to_file_path_prefix(kb_directory)
    if not directory_prefix:
        return where

    directory_node = {"prefix": {"fieldName": "filePath", "value": directory_prefix}}
    return _merge_where_nodes(directory_node, where)


def _with_file_name_filter(where: dict[str, Any], file_name: str | None) -> dict[str, Any]:
    """Add the fixed file name constraint for file-scoped semantic search."""
    normalized_file_name = _normalize_file_name(file_name)
    if not normalized_file_name:
        return where

    file_name_node = {"eq": {"fieldName": "fileName", "value": normalized_file_name}}
    return _merge_where_nodes(file_name_node, where)


def _kb_directory_to_file_path_prefix(kb_directory: str | None) -> str | None:
    if not kb_directory:
        return None
    directory = str(kb_directory).strip()
    if not directory:
        return None
    if not directory.startswith("/"):
        directory = f"/{directory}"
    if directory != "/" and not directory.endswith("/"):
        directory = f"{directory}/"
    return directory


def _normalize_file_name(file_name: str | None) -> str | None:
    if not file_name:
        return None
    name = str(file_name).strip()
    if not name:
        return None
    return PurePosixPath(name).name


def _normalize_metadata_field_type(field_type: str | None) -> str:
    normalized = str(field_type or "").strip().lower()
    if normalized in {"array", "list", "string_list", "stringlist"}:
        return "stringList"
    if normalized in {
        "integer",
        "int",
        "bigint",
        "long",
        "smallint",
        "number",
        "float",
        "double",
        "decimal",
        "real",
    }:
        return "number"
    if normalized in {"boolean", "bool"}:
        return "boolean"
    if normalized in {"date", "datetime", "time", "timestamp"}:
        return "datetime"
    return "string"


def _field_type_for_filter(field_name: str, field_types: dict[str, str]) -> str:
    return _normalize_metadata_field_type(
        field_types.get(field_name) or _SYSTEM_FIELD_TYPES.get(field_name)
    )


def _contains_wildcard_value(value: Any) -> str:
    text = str(value or "")
    if "*" in text or "?" in text:
        return text
    if "%" in text or "_" in text:
        return text.replace("%", "*").replace("_", "?")
    return f"*{text}*"


def _string_list_contains_node(field_name: str, value: Any) -> dict[str, Any]:
    return {"contains": {"fieldName": field_name, "value": str(value)}}


def _string_contains_node(field_name: str, value: Any) -> dict[str, Any]:
    return {"wildcard": {"fieldName": field_name, "value": _contains_wildcard_value(value)}}


def _filter_to_where_node(
    field_name: str,
    raw_filter: Any,
    field_types: dict[str, str],
) -> dict[str, Any]:
    """Compile a single query-style filter to metadata API leaf/compound node."""
    if isinstance(raw_filter, dict):
        op = str(raw_filter.get("op", "eq") or "eq").lower()
        value = raw_filter.get("value")
    else:
        op = "eq"
        value = raw_filter

    field_type = _field_type_for_filter(field_name, field_types)
    if op == "is_null":
        return {"not": {"exists": {"fieldName": field_name}}}
    if op == "is_not_null":
        return {"exists": {"fieldName": field_name}}
    if op == "between":
        values = value if isinstance(value, list) else [value, value]
        start = values[0] if values else None
        end = values[1] if len(values) > 1 else start
        return {
            "and": [
                {"gte": {"fieldName": field_name, "value": start}},
                {"lte": {"fieldName": field_name, "value": end}},
            ]
        }
    if op == "in":
        values = value if isinstance(value, list) else [value]
        values = [item for item in values if item is not None]
        if not values:
            return {}
        if field_type != "stringList":
            return {"in": {"fieldName": field_name, "value": values}}
        nodes = [_string_list_contains_node(field_name, item) for item in values]
        if len(nodes) == 1:
            return nodes[0]
        return {"or": nodes}

    if op in {"like", "contains"}:
        if field_type == "stringList":
            return _string_list_contains_node(field_name, value)
        if field_type == "string":
            return _string_contains_node(field_name, value)
        return {"eq": {"fieldName": field_name, "value": value}}

    if field_type == "stringList":
        if op == "eq":
            return _string_list_contains_node(field_name, value)
        if op in {"neq", "ne"}:
            return {"not": _string_list_contains_node(field_name, value)}

    op_map = {
        "eq": "eq",
        "neq": "ne",
        "ne": "ne",
        "gt": "gt",
        "gte": "gte",
        "lt": "lt",
        "lte": "lte",
        "prefix": "prefix",
        "wildcard": "wildcard",
    }
    metadata_op = op_map.get(op, "eq")
    return {metadata_op: {"fieldName": field_name, "value": value}}
