"""Knowledge-base action backend protocols and default HTTP implementation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Protocol

import httpx

from datacloud_data_sdk.exceptions import DataSourceUnavailableError, KbExecutionError
from datacloud_data_sdk.utils.curl_logger import log_curl
from datacloud_data_sdk.utils.redis_discovery import (
    RedisDiscoveryConfig,
    load_redis_discovery_config,
)


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
    kb_id: str | None = None
    kb_directory: str | None = None


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
class KnowledgeWriteRequest:
    """Structured request passed to knowledge-base write backends."""

    object_code: str
    datasource_alias: str
    kb_id: str
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


class HttpKnowledgeSearchBackend:
    """Default metadata service backend using knowledgeItems search/import APIs."""

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
        """Search the configured metadata endpoint and normalize returned records."""
        config = self._get_config(request.datasource_alias)
        body: dict[str, Any] = {
            "query": request.query,
            "topK": request.limit,
            "searchMode": str(
                config.get("searchMode") or config.get("search_mode") or "mixedRecall"
            ),
        }
        where = _with_kb_directory_filter(
            _filters_to_where(request.filters, request.filter_relation),
            request.kb_directory,
        )
        if where:
            body["where"] = where

        kn_code_list = _coerce_string_list(request.kb_id) or _coerce_string_list(
            config.get("knCodeList") or config.get("kn_code_list") or config.get("knCode")
        )
        if kn_code_list:
            body["knCodeList"] = kn_code_list

        metadata_field_list = request.select or _coerce_string_list(
            config.get("metadataFieldList") or config.get("metadata_field_list")
        )
        if metadata_field_list:
            body["metadataFieldList"] = metadata_field_list

        endpoint = self._resolve_endpoint(config)
        if endpoint:
            url = self._build_search_file_url(endpoint, config)
            data = await self._post_json(url, body, request.datasource_alias)
        else:
            service_name = self._resolve_service_name(config, request.datasource_alias)
            data = await self._post_json_by_discovery(
                service_name=service_name,
                path=self._build_search_file_path(config),
                body=body,
                datasource_alias=request.datasource_alias,
            )

        result_object = data.get("resultObject")
        if isinstance(result_object, dict):
            raw_records = result_object.get("data")
            error_code = result_object.get("errorCode")
            if data.get("resultCode") not in (None, "0", 0):
                raise KbExecutionError(
                    request.datasource_alias,
                    f"{error_code or data.get('resultCode')}: {data.get('resultMsg', '')}",
                )
        else:
            raw_records = data.get("results")
            if data.get("resultCode") not in (None, "0", 0):
                raise KbExecutionError(
                    request.datasource_alias,
                    str(data.get("resultMsg") or data.get("resultCode")),
                )

        records = self._normalize_records(raw_records)
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
        """Upload a generated Markdown document to the configured metadata endpoint."""
        config = self._get_config(request.datasource_alias)
        markdown_file_path = _to_markdown_file_path(request.file_path, request.kb_directory)
        file_content = _render_markdown_with_front_matter(request.labels, request.content)
        filename = PurePosixPath(markdown_file_path).name or "document.md"
        data = {
            "knCode": request.kb_id,
            "filePath": markdown_file_path,
        }
        if request.file_description:
            data["fileDescription"] = request.file_description

        endpoint = self._resolve_endpoint(config)
        if endpoint:
            import_url = self._build_import_url(endpoint, config)
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    await self._ensure_metadata_properties_http(client, endpoint, config, request)

                    log_curl("POST", import_url, body={**data, "fileContent": f"@{filename}"})
                    resp = await client.post(
                        import_url,
                        data=data,
                        files={
                            "fileContent": (
                                filename,
                                file_content.encode("utf-8"),
                                "text/markdown; charset=utf-8",
                            )
                        },
                    )
                    body = self._parse_response_body(resp, request.datasource_alias)
                    self._ensure_success(body, request.datasource_alias)
                    build_body = await self._trigger_file_build_http(
                        client,
                        endpoint,
                        config,
                        request,
                        markdown_file_path,
                    )
            except httpx.HTTPError as exc:
                raise KbExecutionError(request.datasource_alias, str(exc)) from exc
        else:
            service_name = self._resolve_service_name(config, request.datasource_alias)
            try:
                build_body = await self._write_by_discovery(
                    service_name=service_name,
                    config=config,
                    request=request,
                    data=data,
                    filename=filename,
                    file_content=file_content,
                    markdown_file_path=markdown_file_path,
                )
            except httpx.HTTPError as exc:
                raise KbExecutionError(request.datasource_alias, str(exc)) from exc

        record = {
            **request.labels,
            "knCode": request.kb_id,
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

    async def _ensure_metadata_properties_by_discovery(
        self,
        client: Any,
        service_name: str,
        config: dict[str, Any],
        request: KnowledgeWriteRequest,
        headers: dict[str, str],
    ) -> None:
        properties = _normalize_metadata_properties(request.labels, request.metadata_properties)
        if not properties:
            return

        names = [str(item["propertyName"]) for item in properties]
        list_body = {"propertyNameList": names}
        list_path = self._build_metadata_properties_list_path(config)
        log_curl("POST", list_path, body=list_body)
        resp = await client.post(service_name, list_path, headers=headers, json=list_body)
        body = self._parse_discovery_response_body(resp, request.datasource_alias)
        self._ensure_success(body, request.datasource_alias)

        existing_names = _metadata_property_names(body)
        missing_properties = [
            property_def
            for property_def in properties
            if str(property_def["propertyName"]) not in existing_names
        ]
        if not missing_properties:
            return

        create_path = self._build_metadata_properties_batch_create_path(config)
        create_body = {"propertyList": missing_properties}
        log_curl("POST", create_path, body=create_body)
        resp = await client.post(service_name, create_path, headers=headers, json=create_body)
        body = self._parse_discovery_response_body(resp, request.datasource_alias)
        self._ensure_success(body, request.datasource_alias)

    async def _ensure_metadata_properties_http(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        config: dict[str, Any],
        request: KnowledgeWriteRequest,
    ) -> None:
        properties = _normalize_metadata_properties(request.labels, request.metadata_properties)
        if not properties:
            return

        names = [str(item["propertyName"]) for item in properties]
        list_url = self._build_metadata_properties_list_url(endpoint, config)
        list_body = {"propertyNameList": names}
        log_curl("POST", list_url, body=list_body)
        resp = await client.post(list_url, json=list_body)
        body = self._parse_response_body(resp, request.datasource_alias)
        self._ensure_success(body, request.datasource_alias)

        existing_names = _metadata_property_names(body)
        missing_properties = [
            property_def
            for property_def in properties
            if str(property_def["propertyName"]) not in existing_names
        ]
        if not missing_properties:
            return

        create_url = self._build_metadata_properties_batch_create_url(endpoint, config)
        create_body = {"propertyList": missing_properties}
        log_curl("POST", create_url, body=create_body)
        resp = await client.post(create_url, json=create_body)
        body = self._parse_response_body(resp, request.datasource_alias)
        self._ensure_success(body, request.datasource_alias)

    async def _trigger_file_build_by_discovery(
        self,
        client: Any,
        service_name: str,
        config: dict[str, Any],
        request: KnowledgeWriteRequest,
        file_path: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        build_url = self._build_file_to_markdown_index_path(config)
        build_body = {"knCode": request.kb_id, "filePath": file_path}
        log_curl("POST", build_url, body=build_body)
        resp = await client.post(service_name, build_url, headers=headers, json=build_body)
        body = self._parse_discovery_response_body(resp, request.datasource_alias)
        self._ensure_success(body, request.datasource_alias)
        return body

    async def _trigger_file_build_http(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        config: dict[str, Any],
        request: KnowledgeWriteRequest,
        file_path: str,
    ) -> dict[str, Any]:
        build_url = self._build_file_to_markdown_index_url(endpoint, config)
        build_body = {"knCode": request.kb_id, "filePath": file_path}
        log_curl("POST", build_url, body=build_body)
        resp = await client.post(build_url, json=build_body)
        body = self._parse_response_body(resp, request.datasource_alias)
        self._ensure_success(body, request.datasource_alias)
        return body

    async def _write_by_discovery(
        self,
        *,
        service_name: str,
        config: dict[str, Any],
        request: KnowledgeWriteRequest,
        data: dict[str, str],
        filename: str,
        file_content: str,
        markdown_file_path: str,
    ) -> dict[str, Any]:
        try:
            from by_framework.common.redis_client import init_redis
            from by_framework.core.discovery import DiscoveryClient
            from by_framework.util.discovery_http_client import DiscoveryHttpClient
            from by_framework.util.http_client import RetryConfig
        except ImportError as exc:
            raise KbExecutionError(
                request.datasource_alias,
                "redis service discovery requires by_framework dependency",
            ) from exc

        redis_config = self._redis_config
        init_redis(
            host=redis_config.host,
            port=redis_config.port,
            db=redis_config.database,
            password=redis_config.password,
            username=redis_config.username,
        )
        discovery_client = DiscoveryClient(cache_interval=5)
        retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
        try:
            instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
            if not instance:
                raise KbExecutionError(
                    request.datasource_alias,
                    f"knowledge service instance not found: {service_name}",
                )
            json_headers = self._build_discovery_headers(instance)
            upload_headers = self._build_discovery_upload_headers(instance)
            async with DiscoveryHttpClient(
                discovery_client,
                retry_config=retry_config,
                health_threshold_ms=-1,
            ) as client:
                await self._ensure_metadata_properties_by_discovery(
                    client,
                    service_name,
                    config,
                    request,
                    json_headers,
                )

                import_path = self._build_import_path(config)
                file_bytes = file_content.encode("utf-8")
                log_curl("UPLOAD", import_path, body={**data, "fileContent": f"@{filename}"})
                parts: list[tuple[str, Any]] = [
                    ("knCode", data["knCode"]),
                    ("filePath", data["filePath"]),
                ]
                if request.file_description:
                    parts.append(("fileDescription", request.file_description))
                parts.append(
                    (
                        "fileContent",
                        (
                            filename,
                            file_bytes,
                            "text/markdown; charset=utf-8",
                        ),
                    )
                )
                instance_url = client._build_absolute_url(instance, import_path)
                resp = await client.http_client._upload(  # noqa: SLF001
                    instance_url,
                    parts,
                    headers=upload_headers,
                )

                body = self._parse_discovery_response_body(resp, request.datasource_alias)
                self._ensure_success(body, request.datasource_alias)
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
    def _parse_response_body(resp: httpx.Response, datasource_alias: str) -> dict[str, Any]:
        if resp.status_code >= 400:
            raise KbExecutionError(
                datasource_alias,
                f"HTTP {resp.status_code}: {resp.text}",
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise KbExecutionError(
                datasource_alias,
                f"invalid JSON response: {exc}",
            ) from exc
        if not isinstance(body, dict):
            raise KbExecutionError(datasource_alias, "invalid JSON response: root is not object")
        return body

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
    def _ensure_success(body: dict[str, Any], datasource_alias: str) -> None:
        if body.get("resultCode") not in (None, "0", 0):
            raise KbExecutionError(
                datasource_alias,
                str(body.get("resultMsg") or body.get("resultCode")),
            )

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
    def _resolve_endpoint(config: dict[str, Any]) -> str | None:
        endpoint = _first_non_empty_str(
            config.get("url"),
            config.get("endpoint"),
            config.get("endpoint_url"),
        )
        return endpoint

    @staticmethod
    def _resolve_service_name(config: dict[str, Any], datasource_alias: str) -> str:
        service_name = _first_non_empty_str(config.get("service_name"), config.get("serviceName"))
        if service_name:
            return service_name
        env_service_name = _first_non_empty_str(
            os.getenv("QA_DOMAINNAME"),
        )
        if env_service_name:
            return env_service_name
        return datasource_alias

    @staticmethod
    def _build_search_file_path(config: dict[str, Any]) -> str:
        return _normalize_discovery_path(
            _first_non_empty_str(config.get("search_file_path"), config.get("searchFilePath")),
            "/api/v1/knowledgeItems/searchFile",
        )

    @staticmethod
    def _build_import_path(config: dict[str, Any]) -> str:
        return _normalize_discovery_path(
            _first_non_empty_str(config.get("import_path"), config.get("importPath")),
            "/api/v1/knowledgeItems/import",
        )

    @staticmethod
    def _build_metadata_properties_list_path(config: dict[str, Any]) -> str:
        return _normalize_discovery_path(
            _first_non_empty_str(
                config.get("metadata_properties_list_path"),
                config.get("metadataPropertiesListPath"),
            ),
            "/api/v1/metadataProperties/list",
        )

    @staticmethod
    def _build_metadata_properties_batch_create_path(config: dict[str, Any]) -> str:
        return _normalize_discovery_path(
            _first_non_empty_str(
                config.get("metadata_properties_batch_create_path"),
                config.get("metadataPropertiesBatchCreatePath"),
            ),
            "/api/v1/metadataProperties/batchCreate",
        )

    @staticmethod
    def _build_file_to_markdown_index_path(config: dict[str, Any]) -> str:
        return _normalize_discovery_path(
            _first_non_empty_str(
                config.get("file_to_markdown_index_path"),
                config.get("fileToMarkdownIndexPath"),
            ),
            "/api/v1/fileToMarkdownIndex",
        )

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

    async def _post_json(
        self,
        url: str,
        body: dict[str, Any],
        datasource_alias: str,
    ) -> dict[str, Any]:
        log_curl("POST", url, body=body)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=body)
        except httpx.HTTPError as exc:
            raise KbExecutionError(datasource_alias, str(exc)) from exc
        return self._parse_response_body(response, datasource_alias)

    async def _post_json_by_discovery(
        self,
        *,
        service_name: str,
        path: str,
        body: dict[str, Any],
        datasource_alias: str,
    ) -> dict[str, Any]:
        try:
            from by_framework.common.redis_client import init_redis
            from by_framework.core.discovery import DiscoveryClient
            from by_framework.util.discovery_http_client import DiscoveryHttpClient
            from by_framework.util.http_client import RetryConfig
        except ImportError as exc:
            raise KbExecutionError(
                datasource_alias,
                "redis service discovery requires by_framework dependency",
            ) from exc

        redis_config = self._redis_config
        init_redis(
            host=redis_config.host,
            port=redis_config.port,
            db=redis_config.database,
            password=redis_config.password,
            username=redis_config.username,
        )
        discovery_client = DiscoveryClient(cache_interval=5)
        retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
        try:
            instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
            if not instance:
                raise KbExecutionError(
                    datasource_alias,
                    f"knowledge service instance not found: {service_name}",
                )
            headers = self._build_discovery_headers(instance)
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

        return self._parse_discovery_response_body(response, datasource_alias)

    @staticmethod
    def _build_search_file_url(endpoint: str, config: dict[str, Any]) -> str:
        explicit_url = config.get("search_file_url") or config.get("searchFileUrl")
        if explicit_url:
            return str(explicit_url)

        if endpoint.rstrip("/").endswith("/api/v1/knowledgeItems/searchFile"):
            return endpoint.rstrip("/")

        path = str(
            config.get("search_file_path")
            or config.get("searchFilePath")
            or "/api/v1/knowledgeItems/searchFile"
        )
        return endpoint.rstrip("/") + "/" + path.lstrip("/")

    @staticmethod
    def _build_import_url(endpoint: str, config: dict[str, Any]) -> str:
        explicit_url = config.get("import_url") or config.get("importUrl")
        if explicit_url:
            return str(explicit_url)

        if endpoint.rstrip("/").endswith("/api/v1/knowledgeItems/import"):
            return endpoint.rstrip("/")

        path = str(
            config.get("import_path") or config.get("importPath") or "/api/v1/knowledgeItems/import"
        )
        return endpoint.rstrip("/") + "/" + path.lstrip("/")

    @staticmethod
    def _build_metadata_properties_list_url(endpoint: str, config: dict[str, Any]) -> str:
        explicit_url = config.get("metadata_properties_list_url") or config.get(
            "metadataPropertiesListUrl"
        )
        if explicit_url:
            return str(explicit_url)

        if endpoint.rstrip("/").endswith("/api/v1/metadataProperties/list"):
            return endpoint.rstrip("/")

        path = str(
            config.get("metadata_properties_list_path")
            or config.get("metadataPropertiesListPath")
            or "/api/v1/metadataProperties/list"
        )
        return endpoint.rstrip("/") + "/" + path.lstrip("/")

    @staticmethod
    def _build_metadata_properties_batch_create_url(endpoint: str, config: dict[str, Any]) -> str:
        explicit_url = config.get("metadata_properties_batch_create_url") or config.get(
            "metadataPropertiesBatchCreateUrl"
        )
        if explicit_url:
            return str(explicit_url)

        if endpoint.rstrip("/").endswith("/api/v1/metadataProperties/batchCreate"):
            return endpoint.rstrip("/")

        path = str(
            config.get("metadata_properties_batch_create_path")
            or config.get("metadataPropertiesBatchCreatePath")
            or "/api/v1/metadataProperties/batchCreate"
        )
        return endpoint.rstrip("/") + "/" + path.lstrip("/")

    @staticmethod
    def _build_file_to_markdown_index_url(endpoint: str, config: dict[str, Any]) -> str:
        explicit_url = config.get("file_to_markdown_index_url") or config.get(
            "fileToMarkdownIndexUrl"
        )
        if explicit_url:
            return str(explicit_url)

        if endpoint.rstrip("/").endswith("/api/v1/fileToMarkdownIndex"):
            return endpoint.rstrip("/")

        path = str(
            config.get("file_to_markdown_index_path")
            or config.get("fileToMarkdownIndexPath")
            or "/api/v1/fileToMarkdownIndex"
        )
        return endpoint.rstrip("/") + "/" + path.lstrip("/")

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


def _normalize_metadata_properties(
    labels: dict[str, Any],
    metadata_properties: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build metadata property definitions for labels used in front matter."""
    if not labels:
        return []

    definitions_by_name = {
        str(item.get("propertyName")): dict(item)
        for item in metadata_properties
        if isinstance(item, dict) and item.get("propertyName")
    }
    properties: list[dict[str, Any]] = []
    for name, value in labels.items():
        property_name = str(name)
        definition = definitions_by_name.get(property_name, {})
        property_def: dict[str, Any] = {
            "propertyName": property_name,
            "valueType": str(definition.get("valueType") or _infer_metadata_value_type(value)),
        }
        description = definition.get("description")
        if description:
            property_def["description"] = str(description)
        ext_params = definition.get("extParams")
        if isinstance(ext_params, dict) and ext_params:
            property_def["extParams"] = ext_params
        properties.append(property_def)
    return properties


def _first_non_empty_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_discovery_path(path: str, default_path: str) -> str:
    resolved = path or default_path
    if not resolved.startswith("/"):
        resolved = f"/{resolved}"
    return resolved


def _infer_metadata_value_type(value: Any) -> str:
    """Infer metadata API valueType when field metadata is unavailable."""
    if isinstance(value, list):
        return "stringList"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def _metadata_property_names(body: dict[str, Any]) -> set[str]:
    result_object = body.get("resultObject")
    if not isinstance(result_object, dict):
        return set()
    data = result_object.get("data")
    if not isinstance(data, list):
        return set()
    return {
        str(item.get("propertyName"))
        for item in data
        if isinstance(item, dict) and item.get("propertyName")
    }


def _result_summary(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "resultCode": body.get("resultCode"),
        "resultMsg": body.get("resultMsg"),
    }


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


def _render_markdown_with_front_matter(labels: dict[str, Any], content: str) -> str:
    """Render labels as YAML front matter before Markdown content."""
    front_matter_labels = {
        key: value for key, value in labels.items() if not _is_empty_front_matter_value(value)
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


def _filters_to_where(filters: dict[str, Any], filter_relation: str) -> dict[str, Any]:
    """Compile query-style filters to metadata API ``where`` AST."""
    if not filters:
        return {}

    nodes: list[dict[str, Any]] = []
    for field_name, raw_filter in filters.items():
        node = _filter_to_where_node(str(field_name), raw_filter)
        if node:
            nodes.append(node)

    if not nodes:
        return {}
    if len(nodes) == 1:
        return nodes[0]
    relation = "or" if filter_relation.upper() == "OR" else "and"
    return {relation: nodes}


def _with_kb_directory_filter(where: dict[str, Any], kb_directory: str | None) -> dict[str, Any]:
    """Add the object's knowledge-base directory constraint to the metadata where AST."""
    directory_prefix = _kb_directory_to_file_path_prefix(kb_directory)
    if not directory_prefix:
        return where

    directory_node = {"prefix": {"fieldName": "filePath", "value": directory_prefix}}
    if not where:
        return directory_node
    if isinstance(where.get("and"), list):
        return {"and": [directory_node, *where["and"]]}
    return {"and": [directory_node, where]}


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


def _filter_to_where_node(field_name: str, raw_filter: Any) -> dict[str, Any]:
    """Compile a single query-style filter to metadata API leaf/compound node."""
    if isinstance(raw_filter, dict):
        op = str(raw_filter.get("op", "eq") or "eq").lower()
        value = raw_filter.get("value")
    else:
        op = "eq"
        value = raw_filter

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
        nodes = [
            {"contains": {"fieldName": field_name, "value": item}}
            for item in values
            if item is not None
        ]
        if not nodes:
            return {}
        if len(nodes) == 1:
            return nodes[0]
        return {"or": nodes}

    op_map = {
        "eq": "eq",
        "neq": "ne",
        "ne": "ne",
        "like": "contains",
        "contains": "contains",
        "gt": "gt",
        "gte": "gte",
        "lt": "lt",
        "lte": "lte",
        "prefix": "prefix",
        "wildcard": "wildcard",
    }
    metadata_op = op_map.get(op, "eq")
    return {metadata_op: {"fieldName": field_name, "value": value}}
