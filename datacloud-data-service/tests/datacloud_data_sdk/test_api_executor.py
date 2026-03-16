import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
from datacloud_data_sdk.executor.models import ApiExecTask
from datacloud_data_sdk.executor.api_executor import ApiExecutor
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.exceptions import ApiExecutionError

MOCK_RESPONSE = {
    "records": [{"userId": "U001", "userName": "test_user"}],
    "total": 1,
    "meta": {"viewId": "auto_view", "columns": ["userId", "userName"], "total": 1},
}


@pytest.mark.asyncio
async def test_api_executor_writes_csv(tmp_path: Path) -> None:
    task = ApiExecTask(
        object_code="sales_emp",
        action_code="query_emp",
        params={"names": ["test"]},
        output_ref="emp_list",
    )
    mock_obj = MagicMock()
    mock_obj.invoke_action = AsyncMock(return_value=MOCK_RESPONSE)

    mock_loader = MagicMock()
    mock_loader.get_object = MagicMock(return_value=mock_obj)

    with InvocationContext(tenant_id="t1", token="tok"):
        executor = ApiExecutor(loader=mock_loader, csv_base_dir=str(tmp_path))
        result = await executor.execute(task, request_id="req1")

    assert Path(result.csv_path).exists()
    mock_loader.get_object.assert_called_once_with("sales_emp")
    mock_obj.invoke_action.assert_called_once_with("query_emp", {"names": ["test"]})


@pytest.mark.asyncio
async def test_api_executor_raises_on_http_error(tmp_path: Path) -> None:
    task = ApiExecTask(
        object_code="sales_emp",
        action_code="query_emp",
        params={},
        output_ref="x",
    )
    mock_obj = MagicMock()
    mock_obj.invoke_action = AsyncMock(side_effect=ApiExecutionError("fn_get_emp", 500, "Internal Error"))

    mock_loader = MagicMock()
    mock_loader.get_object = MagicMock(return_value=mock_obj)

    with InvocationContext(tenant_id="t1", token="tok"):
        executor = ApiExecutor(loader=mock_loader, csv_base_dir=str(tmp_path))
        with pytest.raises(ApiExecutionError):
            await executor.execute(task, request_id="req1")
