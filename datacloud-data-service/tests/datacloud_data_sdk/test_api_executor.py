import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
from datacloud_data_sdk.executor.models import ApiExecTask
from datacloud_data_sdk.executor.api_executor import ApiExecutor
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.exceptions import ApiExecutionError

API_SCHEMA = {
    "servers": [{"url": "http://mock-service:8080"}],
    "paths": {
        "/api/v1/emp/query": {
            "post": {
                "requestBody": {"content": {"application/json": {}}},
                "responses": {},
            }
        }
    },
}

MOCK_RESPONSE_DATA = {"users": [{"userId": "U001", "userName": "test_user"}]}


@pytest.mark.asyncio
async def test_api_executor_writes_csv(tmp_path: Path) -> None:
    task = ApiExecTask(
        function_code="fn_get_emp",
        params={"names": ["test"]},
        output_ref="emp_list",
        output_params=[
            ("userId", "$.users[].userId"),
            ("userName", "$.users[].userName"),
        ],
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: MOCK_RESPONSE_DATA

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with InvocationContext(tenant_id="t1", token="tok"):
            executor = ApiExecutor(
                function_configs={"fn_get_emp": API_SCHEMA},
                csv_base_dir=str(tmp_path),
            )
            result = await executor.execute(task, request_id="req1")
    assert Path(result.csv_path).exists()


@pytest.mark.asyncio
async def test_api_executor_raises_on_http_error(tmp_path: Path) -> None:
    task = ApiExecTask(
        function_code="fn_get_emp",
        params={},
        output_ref="x",
        output_params=[("id", "$.items[].id")],
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Error"
    mock_resp.json = lambda: {}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with InvocationContext(tenant_id="t1", token="tok"):
            executor = ApiExecutor(
                function_configs={"fn_get_emp": API_SCHEMA},
                csv_base_dir=str(tmp_path),
            )
            with pytest.raises(ApiExecutionError):
                await executor.execute(task, request_id="req1")
