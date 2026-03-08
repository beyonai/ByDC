import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from datacloud_data_sdk.executor.kb_executor import KbExecutor
from datacloud_data_sdk.executor.models import KbExecTask
from datacloud_data_sdk.exceptions import DataSourceUnavailableError, KbExecutionError


@pytest.mark.asyncio
async def test_kb_executor_returns_records() -> None:
    """成功检索时返回 records 列表。"""
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
        executor = KbExecutor(kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}})
        records = await executor.execute(task, "req1", {})

    assert len(records) == 2
    assert records[0] == {"content": "文档1内容", "score": 0.95}
    assert records[1] == {"content": "文档2内容", "score": 0.88}


@pytest.mark.asyncio
async def test_kb_executor_returns_records_with_metadata() -> None:
    """结果含 metadata 时合并到 record。"""
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
        executor = KbExecutor(kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}})
        records = await executor.execute(task, "req1", {})

    assert records[0] == {
        "content": "内容",
        "score": 0.9,
        "doc_id": "d1",
        "source": "manual",
    }


@pytest.mark.asyncio
async def test_kb_executor_simple_content_when_no_metadata() -> None:
    """metadata 为空时仅返回 content。"""
    task = KbExecTask(datasource_alias="kb_docs", query="test", output_ref="out")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [{"content": "简单内容"}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        executor = KbExecutor(kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}})
        records = await executor.execute(task, "req1", {})

    assert records == [{"content": "简单内容"}]


@pytest.mark.asyncio
async def test_kb_executor_request_body() -> None:
    """请求体包含 query、tags、top_k。"""
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
        executor = KbExecutor(kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}})
        await executor.execute(task, "req1", {})

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["json"]["query"] == "检索词"
    assert call_kwargs["json"]["tags"] == {"tag1": "v1"}
    assert call_kwargs["json"]["top_k"] == 10


@pytest.mark.asyncio
async def test_kb_executor_raises_on_missing_datasource() -> None:
    """datasource 不在 config 时抛出 DataSourceUnavailableError。"""
    task = KbExecTask(datasource_alias="unknown_kb", query="test", output_ref="out")
    executor = KbExecutor(kb_configs={"kb_docs": {"endpoint": "http://rag:8000"}})

    with pytest.raises(DataSourceUnavailableError) as exc_info:
        await executor.execute(task, "req1", {})

    assert exc_info.value.alias == "unknown_kb"


@pytest.mark.asyncio
async def test_kb_executor_raises_on_missing_endpoint() -> None:
    """config 中无 endpoint 时抛出 KbExecutionError。"""
    task = KbExecTask(datasource_alias="kb_docs", query="test", output_ref="out")
    executor = KbExecutor(kb_configs={"kb_docs": {}})

    with pytest.raises(KbExecutionError) as exc_info:
        await executor.execute(task, "req1", {})

    assert exc_info.value.datasource_alias == "kb_docs"
    assert "endpoint" in exc_info.value.cause.lower()


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
            await executor.execute(task, "req1", {})

    assert exc_info.value.datasource_alias == "kb_docs"
    assert "500" in exc_info.value.cause


@pytest.mark.asyncio
async def test_kb_executor_post_url() -> None:
    """POST 到 {endpoint}/retrieve。"""
    task = KbExecTask(datasource_alias="kb_docs", query="test", output_ref="out")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": []}

    mock_post = AsyncMock(return_value=mock_resp)
    with patch("httpx.AsyncClient.post", mock_post):
        executor = KbExecutor(kb_configs={"kb_docs": {"endpoint": "http://rag:8000/"}})
        await executor.execute(task, "req1", {})

    assert mock_post.call_args[0][0] == "http://rag:8000/retrieve"
