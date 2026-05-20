import csv
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datacloud_data_sdk.exceptions import DataSourceUnavailableError, KbExecutionError
from datacloud_data_sdk.executor.kb_executor import KbExecutor
from datacloud_data_sdk.executor.kb_search_backend import (
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)
from datacloud_data_sdk.executor.models import KbExecTask
from datacloud_data_sdk.executor.step_results import StepResults


class CustomSearchBackend:
    def __init__(self) -> None:
        self.request: KnowledgeSearchRequest | None = None

    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        self.request = request
        return KnowledgeSearchResult(
            records=[{"content": "自定义内容", "source": request.datasource_alias}],
            total=1,
            meta={"provider": "custom"},
        )


def _read_csv_records(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.asyncio
async def test_kb_executor_returns_csv_path() -> None:
    """成功检索时写入 CSV 并返回 csv_path。"""
    with tempfile.TemporaryDirectory() as tmp:
        task = KbExecTask(
            datasource_alias="kb_docs",
            query="如何配置数据源",
            tags={"category": "config"},
            output_ref="kb_out",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"content": "文档1内容", "score": 0.95},
                {"content": "文档2内容", "score": 0.88},
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            executor = KbExecutor(
                kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}},
                csv_base_dir=tmp,
            )
            csv_path = await executor.execute(task, "req1", StepResults())

        assert isinstance(csv_path, str)
        assert Path(csv_path).exists()
        records = _read_csv_records(csv_path)
        assert len(records) == 2
        assert records[0]["content"] == "文档1内容"
        assert records[0]["score"] == "0.95"
        assert records[1]["content"] == "文档2内容"
        assert records[1]["score"] == "0.88"


@pytest.mark.asyncio
async def test_kb_executor_uses_custom_search_backend() -> None:
    """执行计划 KB step 可通过协议接入第三方检索实现。"""
    with tempfile.TemporaryDirectory() as tmp:
        backend = CustomSearchBackend()
        task = KbExecTask(
            datasource_alias="kb_docs",
            query="自定义检索",
            tags={"category": "manual"},
            output_ref="kb_out",
        )
        executor = KbExecutor(
            kb_configs={"kb_docs": {"endpoint": "http://unused"}},
            csv_base_dir=tmp,
            search_backend=backend,
        )

        csv_path = await executor.execute(task, "req1", StepResults())

        assert backend.request == KnowledgeSearchRequest(
            object_code="kb_docs",
            datasource_alias="kb_docs",
            query="自定义检索",
            filters={"category": "manual"},
            limit=10,
        )
        records = _read_csv_records(csv_path)
        assert records == [{"content": "自定义内容", "source": "kb_docs"}]


@pytest.mark.asyncio
async def test_kb_executor_returns_records_with_metadata() -> None:
    """结果含 metadata 时合并到 record 并写入 CSV。"""
    with tempfile.TemporaryDirectory() as tmp:
        task = KbExecTask(datasource_alias="kb_docs", query="test", output_ref="out")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "content": "内容",
                    "score": 0.9,
                    "metadata": {"doc_id": "d1", "source": "manual"},
                }
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            executor = KbExecutor(
                kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}},
                csv_base_dir=tmp,
            )
            csv_path = await executor.execute(task, "req1", StepResults())

        records = _read_csv_records(csv_path)
        assert records[0]["content"] == "内容"
        assert records[0]["score"] == "0.9"
        assert records[0]["doc_id"] == "d1"
        assert records[0]["source"] == "manual"


@pytest.mark.asyncio
async def test_kb_executor_simple_content_when_no_metadata() -> None:
    """metadata 为空时仅写入 content 列。"""
    with tempfile.TemporaryDirectory() as tmp:
        task = KbExecTask(datasource_alias="kb_docs", query="test", output_ref="out")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"content": "简单内容"}]}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            executor = KbExecutor(
                kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}},
                csv_base_dir=tmp,
            )
            csv_path = await executor.execute(task, "req1", StepResults())

        records = _read_csv_records(csv_path)
        assert records == [{"content": "简单内容"}]


@pytest.mark.asyncio
async def test_kb_executor_request_body() -> None:
    """请求体包含 query、where、topK、searchMode。"""
    with tempfile.TemporaryDirectory() as tmp:
        task = KbExecTask(
            datasource_alias="kb_docs",
            query="检索词",
            tags={"tag1": "v1"},
            output_ref="out",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}

        mock_post = AsyncMock(return_value=mock_resp)
        with patch("httpx.AsyncClient.post", mock_post):
            executor = KbExecutor(
                kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}},
                csv_base_dir=tmp,
            )
            await executor.execute(task, "req1", StepResults())

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["json"]["query"] == "检索词"
    assert call_kwargs["json"]["where"] == {"eq": {"fieldName": "tag1", "value": "v1"}}
    assert call_kwargs["json"]["topK"] == 10
    assert call_kwargs["json"]["searchMode"] == "mixedRecall"


@pytest.mark.asyncio
async def test_kb_executor_raises_on_missing_datasource() -> None:
    """datasource 不在 config 时抛出 DataSourceUnavailableError。"""
    task = KbExecTask(datasource_alias="unknown_kb", query="test", output_ref="out")
    executor = KbExecutor(kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}})

    with pytest.raises(DataSourceUnavailableError) as exc_info:
        await executor.execute(task, "req1", StepResults())

    assert exc_info.value.alias == "unknown_kb"


@pytest.mark.asyncio
async def test_kb_executor_uses_service_discovery_when_endpoint_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """config 中无 endpoint 时走 Redis 服务发现。"""
    task = KbExecTask(datasource_alias="kb_docs", query="test", output_ref="out")

    monkeypatch.setenv("REDIS_HOST", "redis.local")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DATABASE", "2")
    executor = KbExecutor(kb_configs={"kb_docs": {}})

    with _patch_knowledge_discovery(
        expected_service_name="kb_docs",
        expected_path="/api/v1/knowledgeItems/searchFile",
        expected_payload={
            "query": "test",
            "topK": 10,
            "searchMode": "mixedRecall",
        },
        response_body={
            "resultCode": "0",
            "resultMsg": "success",
            "resultObject": {"data": [{"content": "发现内容"}]},
        },
    ) as init_redis:
        csv_path = await executor.execute(task, "req1", StepResults())

    init_redis.assert_called_once_with(
        host="redis.local",
        port=6380,
        db=2,
        password=None,
        username=None,
    )
    assert _read_csv_records(csv_path) == [{"content": "发现内容"}]


@pytest.mark.asyncio
async def test_kb_executor_raises_on_http_error() -> None:
    """HTTP 4xx/5xx 时抛出 KbExecutionError。"""
    task = KbExecTask(datasource_alias="kb_docs", query="test", output_ref="out")
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        executor = KbExecutor(kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}})
        with pytest.raises(KbExecutionError) as exc_info:
            await executor.execute(task, "req1", StepResults())

    assert exc_info.value.datasource_alias == "kb_docs"
    assert "500" in exc_info.value.cause


@pytest.mark.asyncio
async def test_kb_executor_post_url() -> None:
    """POST 到 {endpoint}/api/v1/knowledgeItems/searchFile。"""
    with tempfile.TemporaryDirectory() as tmp:
        task = KbExecTask(datasource_alias="kb_docs", query="test", output_ref="out")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}

        mock_post = AsyncMock(return_value=mock_resp)
        with patch("httpx.AsyncClient.post", mock_post):
            executor = KbExecutor(
                kb_configs={"kb_docs": {"endpoint": "http://rag:8000/"}},
                csv_base_dir=tmp,
            )
            await executor.execute(task, "req1", StepResults())

    assert mock_post.call_args[0][0] == "http://rag:8000/api/v1/knowledgeItems/searchFile"


@pytest.mark.asyncio
async def test_kb_executor_normalizes_search_file_response() -> None:
    """按 metadata_api.md 的 searchFile 响应归一化文件级结果。"""
    with tempfile.TemporaryDirectory() as tmp:
        task = KbExecTask(datasource_alias="kb_docs", query="续签流程", output_ref="out")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "resultCode": "0",
            "resultMsg": "success",
            "resultObject": {
                "data": [
                    {
                        "knCode": "2",
                        "filePath": "/制度/人事/续签流程.md",
                        "score": 94.2,
                        "metadata": {
                            "status": {"valueType": "string", "value": "active"},
                            "tags": {"valueType": "stringList", "value": ["hr", "contract"]},
                        },
                    }
                ]
            },
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            executor = KbExecutor(
                kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}},
                csv_base_dir=tmp,
            )
            csv_path = await executor.execute(task, "req1", StepResults())

        records = _read_csv_records(csv_path)
        assert records[0]["knCode"] == "2"
        assert records[0]["filePath"] == "/制度/人事/续签流程.md"
        assert records[0]["status"] == "active"


@pytest.mark.asyncio
async def test_kb_executor_empty_records_still_writes_csv() -> None:
    """records 为空时仍写入空 CSV 并返回 path。"""
    with tempfile.TemporaryDirectory() as tmp:
        task = KbExecTask(datasource_alias="kb_docs", query="test", output_ref="empty_out")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            executor = KbExecutor(
                kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}},
                csv_base_dir=tmp,
            )
            csv_path = await executor.execute(task, "req1", StepResults())

        assert isinstance(csv_path, str)
        assert Path(csv_path).exists()
        assert Path(csv_path).read_text() == ""


@contextmanager
def _patch_knowledge_discovery(
    *,
    expected_service_name: str,
    expected_path: str,
    expected_payload: dict[str, Any],
    response_body: dict[str, Any],
) -> Iterator[MagicMock]:
    class _MockInstance:
        metadata = {"token": "instance-token"}

    class _MockDiscoveryClient:
        def __init__(self, cache_interval: int) -> None:
            self.cache_interval = cache_interval

        async def discover(self, service_name: str, health_threshold_ms: int) -> _MockInstance:
            assert service_name == expected_service_name
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
            json: dict[str, Any],
        ) -> Any:
            assert service_name == expected_service_name
            assert path == expected_path
            assert json == expected_payload
            assert headers["Authorization"] == "Bearer instance-token"
            return _MockDiscoveryResponse(response_body)

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
