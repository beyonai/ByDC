from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datacloud_data_sdk.executor.kb_search_backend import (
    HttpKnowledgeSearchBackend,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    KnowledgeWriteRequest,
    KnowledgeWriteResult,
    _render_markdown_with_front_matter,
)
from datacloud_data_sdk.executor.kb_search_executor import KbSearchExecutor
from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.models import OntologyClass, OntologyField
from datacloud_data_service.tools.virtual_action_injector import inject_virtual_actions


@dataclass
class DummyConfig:
    kb_source_configs: dict[str, dict[str, Any]] | None = None
    kb_search_backend: Any = None
    kb_backends: dict[str, Any] = field(default_factory=dict)
    default_kb_backend: str | None = None


class DummyLoader:
    def __init__(self, cls: OntologyClass, config: DummyConfig) -> None:
        self._cls = cls
        self._config = config

    def get_ontology_class(self, object_code: str) -> OntologyClass:
        assert object_code == self._cls.object_code
        return self._cls


class CustomSearchBackend:
    def __init__(self) -> None:
        self.request: KnowledgeSearchRequest | None = None
        self.write_request: KnowledgeWriteRequest | None = None

    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        self.request = request
        return KnowledgeSearchResult(
            records=[{"content": "命中文档", "doc_id": "d1"}],
            total=1,
            meta={"provider": "custom"},
        )

    async def write(self, request: KnowledgeWriteRequest) -> KnowledgeWriteResult:
        self.write_request = request
        return KnowledgeWriteResult(
            records=[
                {
                    **request.labels,
                    "knCode": request.kb_id,
                    "filePath": request.file_path,
                    "content": request.content,
                }
            ],
            total=1,
            meta={"provider": "custom"},
        )


def test_render_markdown_with_front_matter_skips_empty_values() -> None:
    rendered = _render_markdown_with_front_matter(
        {
            "status": "active",
            "empty_string": "",
            "blank_string": "   ",
            "empty_list": [],
            "empty_dict": {},
            "none_value": None,
            "is_active": False,
            "count": 0,
        },
        "会议内容",
    )

    assert rendered == ('---\nstatus: "active"\nis_active: false\ncount: 0\n---\n\n会议内容')


@pytest.mark.asyncio
async def test_kb_search_executor_uses_custom_backend() -> None:
    backend = CustomSearchBackend()
    cls = OntologyClass(
        object_code="kb_object",
        object_name="知识库对象",
        description="",
        source_type="KNOWLEDGE_BASE",
        datasource_alias="kb_docs",
    )
    loader = DummyLoader(cls, DummyConfig(kb_search_backend=backend))

    result = await KbSearchExecutor(loader).execute(
        "kb_object",
        {
            "query": "如何配置数据源",
            "filters": [{"field": "category", "op": "eq", "value": "config"}],
            "limit": 3,
        },
    )

    assert backend.request == KnowledgeSearchRequest(
        object_code="kb_object",
        datasource_alias="kb_docs",
        query="如何配置数据源",
        filters={"category": {"op": "eq", "value": "config"}},
        filter_relation="AND",
        select=[],
        order_by=[],
        limit=3,
        offset=0,
    )
    assert result == {
        "records": [{"content": "命中文档", "doc_id": "d1"}],
        "total": 1,
        "meta": {"provider": "custom"},
    }


@pytest.mark.asyncio
async def test_kb_search_executor_accepts_query_style_arguments() -> None:
    backend = CustomSearchBackend()
    cls = OntologyClass(
        object_code="kb_object",
        object_name="知识库对象",
        description="",
        source_type="KNOWLEDGE_BASE",
        datasource_alias="kb_docs",
    )
    loader = DummyLoader(cls, DummyConfig(kb_search_backend=backend))

    await KbSearchExecutor(loader).execute(
        "kb_object",
        {
            "query": "续签流程",
            "select": ["status", "tags"],
            "filters": [{"field": "status", "op": "eq", "value": "active"}],
            "filter_relation": "OR",
            "order_by": [{"field": "updatedAt", "direction": "desc"}],
            "limit": 5,
            "offset": 10,
        },
    )

    assert backend.request == KnowledgeSearchRequest(
        object_code="kb_object",
        datasource_alias="kb_docs",
        query="续签流程",
        filters={"status": {"op": "eq", "value": "active"}},
        filter_relation="OR",
        select=["status", "tags"],
        order_by=[{"field": "updatedAt", "direction": "desc"}],
        limit=5,
        offset=10,
    )


@pytest.mark.asyncio
async def test_http_kb_search_converts_in_filter_to_or_contains() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"resultCode": "0", "resultMsg": "success", "resultObject": []}
    backend = HttpKnowledgeSearchBackend({"endpoint_url": "http://kb-service"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as post:
        await backend.search(
            KnowledgeSearchRequest(
                object_code="kb_object",
                datasource_alias="kb_object",
                query="续签流程",
                filters={
                    "status": {"op": "eq", "value": "active"},
                    "tags": {"op": "in", "value": ["contract", "renewal"]},
                },
                filter_relation="AND",
                limit=5,
            )
        )

    body = post.call_args.kwargs["json"]
    assert body["where"] == {
        "and": [
            {"eq": {"fieldName": "status", "value": "active"}},
            {
                "or": [
                    {"contains": {"fieldName": "tags", "value": "contract"}},
                    {"contains": {"fieldName": "tags", "value": "renewal"}},
                ]
            },
        ]
    }


@pytest.mark.asyncio
async def test_http_kb_search_adds_kb_directory_file_path_prefix_filter() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"resultCode": "0", "resultMsg": "success", "resultObject": []}
    backend = HttpKnowledgeSearchBackend({"endpoint_url": "http://kb-service"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as post:
        await backend.search(
            KnowledgeSearchRequest(
                object_code="kb_object",
                datasource_alias="kb_object",
                query="请假制度",
                kb_directory="/制度/人事",
            )
        )

    body = post.call_args.kwargs["json"]
    assert body["where"] == {"prefix": {"fieldName": "filePath", "value": "/制度/人事/"}}


@pytest.mark.asyncio
async def test_http_kb_search_combines_kb_directory_with_user_filters() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"resultCode": "0", "resultMsg": "success", "resultObject": []}
    backend = HttpKnowledgeSearchBackend({"endpoint_url": "http://kb-service"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as post:
        await backend.search(
            KnowledgeSearchRequest(
                object_code="kb_object",
                datasource_alias="kb_object",
                query="续签流程",
                filters={
                    "status": {"op": "eq", "value": "active"},
                    "tags": {"op": "in", "value": ["contract", "renewal"]},
                },
                filter_relation="AND",
                kb_directory="/制度/人事/",
            )
        )

    body = post.call_args.kwargs["json"]
    assert body["where"] == {
        "and": [
            {"prefix": {"fieldName": "filePath", "value": "/制度/人事/"}},
            {"eq": {"fieldName": "status", "value": "active"}},
            {
                "or": [
                    {"contains": {"fieldName": "tags", "value": "contract"}},
                    {"contains": {"fieldName": "tags", "value": "renewal"}},
                ]
            },
        ]
    }


@pytest.mark.asyncio
async def test_kb_search_executor_write_uses_ext_property_binding() -> None:
    backend = CustomSearchBackend()
    cls = OntologyClass(
        object_code="kb_object",
        object_name="知识库对象",
        description="",
        source_type="KNOWLEDGE_BASE",
        datasource_alias="kb_docs",
        ext_property={"kb_id": "kb-sales", "kb_directory": "/sales"},
    )
    loader = DummyLoader(cls, DummyConfig(kb_search_backend=backend))

    result = await KbSearchExecutor(loader).write(
        "kb_object",
        {
            "source_path": "/sales/meeting.md",
            "labels": {"status": "active"},
            "content": "会议内容",
        },
    )

    assert result["records"] == [
        {
            "status": "active",
            "knCode": "kb-sales",
            "filePath": "/sales/meeting.md",
            "content": "会议内容",
        }
    ]
    assert result["meta"]["fields"] == []


@pytest.mark.asyncio
async def test_http_kb_write_ensures_metadata_properties_and_triggers_build() -> None:
    """HTTP write 先补齐元数据属性，再导入文件并触发构建。"""
    list_resp = MagicMock()
    list_resp.status_code = 200
    list_resp.json.return_value = {
        "resultCode": "0",
        "resultMsg": "success",
        "resultObject": {"data": [{"propertyName": "status", "valueType": "string"}]},
    }
    create_resp = MagicMock()
    create_resp.status_code = 200
    create_resp.json.return_value = {
        "resultCode": "0",
        "resultMsg": "success",
        "resultObject": {"data": [{"propertyName": "tags", "valueType": "stringList"}]},
    }
    import_resp = MagicMock()
    import_resp.status_code = 200
    import_resp.json.return_value = {"resultCode": "0", "resultMsg": "success", "resultObject": {}}
    build_resp = MagicMock()
    build_resp.status_code = 200
    build_resp.json.return_value = {"resultCode": "0", "resultMsg": "success", "resultObject": {}}

    backend = HttpKnowledgeSearchBackend({"endpoint_url": "http://kb-service"})
    request = KnowledgeWriteRequest(
        object_code="kb_object",
        datasource_alias="kb_docs",
        kb_id="kb-sales",
        file_path="/sales/meeting.md",
        labels={"status": "active", "tags": ["sales", "meeting"]},
        content="会议内容",
        metadata_properties=[
            {
                "propertyName": "status",
                "valueType": "string",
                "description": "状态",
            },
            {
                "propertyName": "tags",
                "valueType": "stringList",
                "description": "标签",
            },
        ],
    )

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=[list_resp, create_resp, import_resp, build_resp],
    ) as mock_post:
        result = await backend.write(request)

    calls = mock_post.call_args_list
    assert len(calls) == 4
    assert calls[0].args[0] == "http://kb-service/api/v1/metadataProperties/list"
    assert calls[0].kwargs["json"] == {"propertyNameList": ["status", "tags"]}
    assert calls[1].args[0] == "http://kb-service/api/v1/metadataProperties/batchCreate"
    assert calls[1].kwargs["json"] == {
        "propertyList": [
            {
                "propertyName": "tags",
                "valueType": "stringList",
                "description": "标签",
            }
        ]
    }
    assert calls[2].args[0] == "http://kb-service/api/v1/knowledgeItems/import"
    assert calls[2].kwargs["data"] == {"knCode": "kb-sales", "filePath": "/sales/meeting.md"}
    assert calls[3].args[0] == "http://kb-service/api/v1/fileToMarkdownIndex"
    assert calls[3].kwargs["json"] == {"knCode": "kb-sales", "filePath": "/sales/meeting.md"}
    assert result.records[0]["filePath"] == "/sales/meeting.md"
    assert result.meta["build"] == {"resultCode": "0", "resultMsg": "success"}


@pytest.mark.asyncio
async def test_http_kb_write_imports_markdown_file_with_front_matter() -> None:
    """源文件路径转为 .md，文件内容写入 YAML front matter 后再导入和构建。"""
    list_resp = MagicMock()
    list_resp.status_code = 200
    list_resp.json.return_value = {
        "resultCode": "0",
        "resultMsg": "success",
        "resultObject": {"data": [{"propertyName": "status", "valueType": "string"}]},
    }
    import_resp = MagicMock()
    import_resp.status_code = 200
    import_resp.json.return_value = {"resultCode": "0", "resultMsg": "success", "resultObject": {}}
    build_resp = MagicMock()
    build_resp.status_code = 200
    build_resp.json.return_value = {"resultCode": "0", "resultMsg": "success", "resultObject": {}}

    backend = HttpKnowledgeSearchBackend({"endpoint_url": "http://kb-service"})
    request = KnowledgeWriteRequest(
        object_code="kb_object",
        datasource_alias="kb_docs",
        kb_id="kb-sales",
        file_path="/tmp/upload/meeting.docx",
        kb_directory="/sales",
        labels={"status": "active"},
        content="会议内容",
        metadata_properties=[
            {
                "propertyName": "status",
                "valueType": "string",
                "description": "状态",
            }
        ],
    )

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=[list_resp, import_resp, build_resp],
    ) as mock_post:
        result = await backend.write(request)

    calls = mock_post.call_args_list
    assert len(calls) == 3
    assert calls[1].args[0] == "http://kb-service/api/v1/knowledgeItems/import"
    assert calls[1].kwargs["data"] == {"knCode": "kb-sales", "filePath": "/sales/meeting.md"}
    filename, content, content_type = calls[1].kwargs["files"]["fileContent"]
    assert filename == "meeting.md"
    assert content_type == "text/markdown; charset=utf-8"
    assert content.decode("utf-8").startswith('---\nstatus: "active"\n---\n\n会议内容')
    assert calls[2].kwargs["json"] == {"knCode": "kb-sales", "filePath": "/sales/meeting.md"}
    assert result.records[0]["filePath"] == "/sales/meeting.md"


@pytest.mark.asyncio
async def test_http_kb_write_uses_service_discovery_when_url_missing() -> None:
    backend = HttpKnowledgeSearchBackend({"service_name": "kb-service"})
    request = KnowledgeWriteRequest(
        object_code="kb_object",
        datasource_alias="kb_docs",
        kb_id="kb-sales",
        file_path="/sales/meeting.md",
        labels={"status": "active"},
        content="会议内容",
        metadata_properties=[
            {
                "propertyName": "status",
                "valueType": "string",
                "description": "状态",
            }
        ],
    )

    with _patch_knowledge_write_discovery() as init_redis:
        result = await backend.write(request)

    init_redis.assert_called_once()
    assert result.records[0]["filePath"] == "/sales/meeting.md"
    assert result.meta["build"] == {"resultCode": "0", "resultMsg": "success"}


@pytest.mark.asyncio
async def test_kb_write_request_contains_metadata_properties_from_object_fields() -> None:
    backend = CustomSearchBackend()
    cls = OntologyClass(
        object_code="kb_object",
        object_name="知识库对象",
        description="",
        source_type="KNOWLEDGE_BASE",
        datasource_alias="kb_docs",
        ext_property={"kb_id": "kb-sales"},
        fields=[
            OntologyField(
                field_code="status",
                field_name="状态",
                field_type="STRING",
            ),
            OntologyField(
                field_code="tags",
                field_name="标签",
                field_type="ARRAY",
            ),
        ],
    )
    loader = DummyLoader(cls, DummyConfig(kb_search_backend=backend))

    await KbSearchExecutor(loader).write(
        "kb_object",
        {
            "source_path": "/sales/meeting.md",
            "labels": {"status": "active", "tags": ["sales"]},
            "content": "会议内容",
        },
    )

    assert backend.write_request is not None
    assert backend.write_request.metadata_properties == [
        {"propertyName": "status", "valueType": "string", "description": "状态"},
        {"propertyName": "tags", "valueType": "stringList", "description": "标签"},
    ]


@pytest.mark.asyncio
async def test_kb_write_uses_default_registered_backend() -> None:
    backend = CustomSearchBackend()
    cls = OntologyClass(
        object_code="kb_object",
        object_name="知识库对象",
        description="",
        source_type="KNOWLEDGE_BASE",
        datasource_alias="kb_docs",
        ext_property={"kb_id": "kb-sales"},
    )
    loader = DummyLoader(
        cls,
        DummyConfig(
            kb_backends={"http_knowledge_import": backend},
            default_kb_backend="http_knowledge_import",
        ),
    )

    result = await KbSearchExecutor(loader).write(
        "kb_object",
        {
            "source_path": "/sales/meeting.md",
            "labels": {"status": "active"},
            "content": "会议内容",
        },
    )

    assert backend.write_request is not None
    assert backend.write_request.datasource_alias == "kb_docs"
    assert result["records"][0]["filePath"] == "/sales/meeting.md"


@pytest.mark.asyncio
async def test_kb_binding_comes_from_object_ext_property_only() -> None:
    backend = CustomSearchBackend()
    cls = OntologyClass(
        object_code="kb_object",
        object_name="知识库对象",
        description="",
        source_type="KNOWLEDGE_BASE",
        datasource_alias="kb_docs",
    )
    loader = DummyLoader(
        cls,
        DummyConfig(
            kb_source_configs={"kb_docs": {"knCode": "legacy-kb", "kb_directory": "/legacy"}},
            kb_search_backend=backend,
        ),
    )

    await KbSearchExecutor(loader).execute("kb_object", {"query": "测试"})
    write_result = await KbSearchExecutor(loader).write(
        "kb_object",
        {
            "source_path": "/sales/meeting.md",
            "labels": {"status": "active"},
            "content": "会议内容",
        },
    )

    assert backend.request is not None
    assert backend.request.kb_id is None
    assert backend.request.kb_directory is None
    assert backend.write_request is None
    assert write_result["total"] == 0
    assert write_result["meta"]["note"] == "knowledge base id not configured"


@pytest.mark.asyncio
async def test_invoke_write_action_uses_default_registered_backend() -> None:
    backend = CustomSearchBackend()
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "objects": [
                {
                    "object_code": "meeting_doc",
                    "object_name": "会议文档",
                    "source_type": "KNOWLEDGE_BASE",
                    "datasource_alias": "kb_docs",
                    "ext_property": {"kb_id": "kb-sales"},
                    "fields": [
                        {
                            "field_code": "status",
                            "field_name": "状态",
                            "field_type": "STRING",
                        }
                    ],
                }
            ]
        }
    )
    loader.configure(
        kb_backends={"http_knowledge_import": backend},
        default_kb_backend="http_knowledge_import",
    )
    inject_virtual_actions(loader)

    obj = loader.get_object("meeting_doc")
    result = await obj.invoke_action(
        "write_meeting_doc",
        {
            "source_path": "/sales/meeting.md",
            "labels": {"status": "active"},
            "content": "会议内容",
        },
    )

    assert backend.write_request is not None
    assert backend.write_request.datasource_alias == "kb_docs"
    assert backend.write_request.kb_id == "kb-sales"
    assert result["records"][0]["filePath"] == "/sales/meeting.md"


@pytest.mark.asyncio
async def test_invoke_write_action_allows_empty_datasource_alias() -> None:
    backend = CustomSearchBackend()
    loader = OntologyLoader()
    loader.load_from_content(
        {
            "objects": [
                {
                    "object_code": "meeting_doc",
                    "object_name": "会议文档",
                    "source_type": "KNOWLEDGE_BASE",
                    "ext_property": {"kb_id": "kb-sales", "kb_directory": "/sales"},
                    "fields": [
                        {
                            "field_code": "status",
                            "field_name": "状态",
                            "field_type": "STRING",
                        }
                    ],
                }
            ]
        }
    )
    loader.configure(
        kb_backends={"http_knowledge_import": backend},
        default_kb_backend="http_knowledge_import",
    )
    inject_virtual_actions(loader)

    obj = loader.get_object("meeting_doc")
    result = await obj.invoke_action(
        "write_meeting_doc",
        {
            "source_path": "/sales/meeting.md",
            "labels": {"status": "active"},
            "content": "会议内容",
        },
    )

    assert backend.write_request is not None
    assert backend.write_request.datasource_alias == "meeting_doc"
    assert backend.write_request.kb_id == "kb-sales"
    assert backend.write_request.kb_directory == "/sales"
    assert result["records"][0]["filePath"] == "/sales/meeting.md"


@contextmanager
def _patch_knowledge_write_discovery() -> Iterator[MagicMock]:
    class _MockInstance:
        metadata = {"token": "instance-token"}

    class _MockDiscoveryClient:
        def __init__(self, cache_interval: int) -> None:
            self.cache_interval = cache_interval

        async def discover(self, service_name: str, health_threshold_ms: int) -> _MockInstance:
            assert service_name == "kb-service"
            assert health_threshold_ms == -1
            return _MockInstance()

        async def close(self) -> None:
            return None

    class _MockRetryConfig:
        def __init__(self, max_attempts: int, retry_on_status_codes: set[int]) -> None:
            self.max_attempts = max_attempts
            self.retry_on_status_codes = retry_on_status_codes

    class _MockDiscoveryResponse:
        def __init__(self, data: dict[str, Any]) -> None:
            self.data = data

    class _MockDiscoveryHttpClient:
        def __init__(
            self,
            discovery_client: _MockDiscoveryClient,
            *,
            retry_config: _MockRetryConfig,
            health_threshold_ms: int,
        ) -> None:
            self.discovery_client = discovery_client
            self.retry_config = retry_config
            self.health_threshold_ms = health_threshold_ms

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        async def post(
            self,
            service_name: str,
            path: str,
            *,
            headers: dict[str, str],
            data: dict[str, str] | None = None,
            files: dict[str, tuple[str, bytes, str]] | None = None,
            json: dict[str, Any] | None = None,
        ) -> Any:
            assert service_name == "kb-service"
            if path == "/api/v1/metadataProperties/list":
                assert headers["Authorization"] == "Bearer instance-token"
                assert json == {"propertyNameList": ["status"]}
                return _MockDiscoveryResponse(
                    {
                        "resultCode": "0",
                        "resultMsg": "success",
                        "resultObject": {"data": []},
                    }
                )
            if path == "/api/v1/metadataProperties/batchCreate":
                assert headers["Authorization"] == "Bearer instance-token"
                assert json == {
                    "propertyList": [
                        {
                            "propertyName": "status",
                            "valueType": "string",
                            "description": "状态",
                        }
                    ]
                }
                return _MockDiscoveryResponse(
                    {
                        "resultCode": "0",
                        "resultMsg": "success",
                        "resultObject": {"data": []},
                    }
                )
            if path == "/api/v1/knowledgeItems/import":
                assert headers["Authorization"] == "Bearer instance-token"
                assert data == {"knCode": "kb-sales", "filePath": "/sales/meeting.md"}
                assert files is not None and files["fileContent"][0] == "meeting.md"
                return _MockDiscoveryResponse(
                    {
                        "resultCode": "0",
                        "resultMsg": "success",
                        "resultObject": {},
                    }
                )
            if path == "/api/v1/fileToMarkdownIndex":
                assert headers["Authorization"] == "Bearer instance-token"
                assert json == {"knCode": "kb-sales", "filePath": "/sales/meeting.md"}
                return _MockDiscoveryResponse(
                    {
                        "resultCode": "0",
                        "resultMsg": "success",
                        "resultObject": {},
                    }
                )
            raise AssertionError(f"unexpected path: {path}")

    root_module = ModuleType("by_framework")
    common_module = ModuleType("by_framework.common")
    redis_module = ModuleType("by_framework.common.redis_client")
    core_module = ModuleType("by_framework.core")
    discovery_module = ModuleType("by_framework.core.discovery")
    util_module = ModuleType("by_framework.util")
    discovery_http_module = ModuleType("by_framework.util.discovery_http_client")
    http_client_module = ModuleType("by_framework.util.http_client")

    init_redis = MagicMock()
    redis_module.init_redis = init_redis  # type: ignore[attr-defined]
    discovery_module.DiscoveryClient = _MockDiscoveryClient  # type: ignore[attr-defined]
    discovery_http_module.DiscoveryHttpClient = _MockDiscoveryHttpClient  # type: ignore[attr-defined]
    http_client_module.RetryConfig = _MockRetryConfig  # type: ignore[attr-defined]

    modules = {
        "by_framework": root_module,
        "by_framework.common": common_module,
        "by_framework.common.redis_client": redis_module,
        "by_framework.core": core_module,
        "by_framework.core.discovery": discovery_module,
        "by_framework.util": util_module,
        "by_framework.util.discovery_http_client": discovery_http_module,
        "by_framework.util.http_client": http_client_module,
    }
    with patch.dict(sys.modules, modules):
        yield init_redis
