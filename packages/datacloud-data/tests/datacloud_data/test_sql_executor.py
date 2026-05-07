from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.executor.models import SqlExecTask
from datacloud_data_sdk.executor.step_results import StepResult, StepResults
from datacloud_data_sdk.ontology.term_loader import KbTermLoader
from datacloud_data_sdk.plan.models import (
    ObjectViewField,
    ObjectViewObject,
    ObjectViewPayload,
    ObjectViewSource,
)
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
from datacloud_data_sdk.sql_executor.models import DataSourceConfig
from datacloud_data_sdk.sql_executor.sql_executor import SqlExecutor

SQLITE_CONFIG = DataSourceConfig(
    alias="test_db",
    db_type="SQLITE",
    jdbc_url="jdbc:sqlite::memory:",
    user="",
    password="",
)


@pytest.mark.asyncio
async def test_sql_executor_returns_csv(tmp_path: Path) -> None:
    manager = DataSourceManager({"test_db": SQLITE_CONFIG})
    executor = SqlExecutor(manager, csv_base_dir=str(tmp_path))
    task = SqlExecTask(
        datasource_alias="test_db",
        sql_template="SELECT 1 AS id, 'hello' AS name",
        output_ref="result",
    )
    result = await executor.execute(task, request_id="req1", step_results=StepResults())
    csv_path = Path(result.csv_path)
    assert csv_path.exists()
    content = csv_path.read_text()
    assert "id" in content
    assert "hello" in content


@pytest.mark.asyncio
async def test_sql_executor_bind_from_step(tmp_path: Path) -> None:
    csv_content = "emp_id\nU001\nU002\n"
    step_csv = tmp_path / "req1" / "step_1_api.csv"
    step_csv.parent.mkdir(parents=True)
    step_csv.write_text(csv_content)

    manager = DataSourceManager({"test_db": SQLITE_CONFIG})
    executor = SqlExecutor(manager, csv_base_dir=str(tmp_path))
    task = SqlExecTask(
        datasource_alias="test_db",
        sql_template="SELECT {bind_values} AS ids",
        bind_from_step="step_1_api",
        bind_key="emp_id",
        output_ref="result",
    )
    sr = StepResults()
    sr.add(StepResult("step_1_api", "step_1_api", "", str(step_csv), ""))
    result = await executor.execute(task, request_id="req1", step_results=sr)
    content = Path(result.csv_path).read_text()
    assert "U001" in content


@pytest.mark.asyncio
async def test_sql_executor_supports_http_sql_connector(tmp_path: Path) -> None:
    config = DataSourceConfig(
        alias="domain_model",
        db_type="HTTP_SQL",
        datasource_id=86039,
        endpoint_url="http://localhost:8000/knowledgeService/callDomainModel/executeSql",
    )
    manager = DataSourceManager({"domain_model": config})
    executor = SqlExecutor(manager, csv_base_dir=str(tmp_path))
    task = SqlExecTask(
        datasource_alias="domain_model",
        sql_template="select * from prt339179_sankai_new_day_z_view_a limit 5",
        output_ref="result",
    )

    class MockResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "resultCode": "0",
                "resultMsg": "",
                "resultObject": {
                    "datasourceId": 86039,
                    "resultData": [
                        {
                            "DATE_CD": "20250823",
                            "AREA_NAME_LV3": "杭州分公司",
                            "CDMA_DAY_CNT": "1.00",
                        }
                    ],
                    "total": 1,
                },
            }

    mock_post = AsyncMock(return_value=MockResponse())
    with (
        InvocationContext(
            token="token-1", tenant_id="tenant-1", user_id="user-1", cookie="session=abc123"
        ),
        patch("httpx.AsyncClient.post", mock_post),
    ):
        result = await executor.execute(task, request_id="req1", step_results=StepResults())

    mock_post.assert_awaited_once()
    assert mock_post.await_args is not None
    args, kwargs = mock_post.await_args
    posted_url = args[0] if args else kwargs.get("url")
    assert posted_url == "http://localhost:8000/knowledgeService/callDomainModel/executeSql"
    assert kwargs["json"] == {
        "datasourceId": 86039,
        "sql": "select * from prt339179_sankai_new_day_z_view_a limit 5",
    }
    assert kwargs["headers"]["Authorization"] == "Bearer token-1"
    assert kwargs["headers"]["X-Tenant-Id"] == "tenant-1"
    assert kwargs["headers"]["X-User-Id"] == "user-1"
    assert kwargs["headers"]["cookie"] == "session=abc123"

    content = Path(result.csv_path).read_text(encoding="utf-8")
    assert "DATE_CD" in content
    assert "杭州分公司" in content


@pytest.mark.asyncio
async def test_sql_executor_converts_rel_term_code_result_to_name(tmp_path: Path) -> None:
    manager = DataSourceManager({"test_db": SQLITE_CONFIG})
    payload = ObjectViewPayload(
        view_id="view_1",
        sources=[
            ObjectViewSource(
                source_id="SRC_TEST_DB",
                source_type="DB",
                datasource_alias="test_db",
                db_type="SQLITE",
            )
        ],
        objects=[
            ObjectViewObject(
                object_id="sales",
                object_name="销售",
                source_id="SRC_TEST_DB",
                table="sales",
                fields=[
                    ObjectViewField(
                        name="status",
                        type="string",
                        term_set="status.code",
                        term_field="code",
                        source_column="status_code",
                    )
                ],
            )
        ],
        relations=[],
    )
    term_loader = KbTermLoader(
        {"status.code": [{"code": "SIGNED", "label": "已签约", "aliases": []}]}
    )
    executor = SqlExecutor(
        manager,
        csv_base_dir=str(tmp_path),
        payload=payload,
        term_loader=term_loader,
    )
    task = SqlExecTask(
        datasource_alias="test_db",
        sql_template="SELECT 'SIGNED' AS status_code",
        output_ref="result",
    )

    result = await executor.execute(task, request_id="req1", step_results=StepResults())

    content = Path(result.csv_path).read_text(encoding="utf-8")
    assert "已签约" in content
    assert "SIGNED" not in content


@pytest.mark.asyncio
async def test_datasource_id_forces_http_sql_connector(tmp_path: Path) -> None:
    """当 datasource_id 不为空时，即使 db_type 是 MYSQL，也会使用 HTTP_SQL 连接器。"""
    config = DataSourceConfig(
        alias="auto_http_sql",
        db_type="MYSQL",
        jdbc_url="jdbc:mysql://localhost:3306/test",
        datasource_id=12345,
        endpoint_url="http://localhost:8000/api/sql/execute",
    )
    manager = DataSourceManager({"auto_http_sql": config})
    executor = SqlExecutor(manager, csv_base_dir=str(tmp_path))
    task = SqlExecTask(
        datasource_alias="auto_http_sql",
        sql_template="SELECT * FROM users LIMIT 10",
        output_ref="result",
    )

    class MockResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "resultCode": "0",
                "resultObject": {
                    "resultData": [
                        {"id": 1, "name": "Alice"},
                        {"id": 2, "name": "Bob"},
                    ]
                },
            }

    mock_post = AsyncMock(return_value=MockResponse())
    with patch("httpx.AsyncClient.post", mock_post):
        result = await executor.execute(task, request_id="req1", step_results=StepResults())

    mock_post.assert_awaited_once()
    assert mock_post.await_args is not None
    args, kwargs = mock_post.await_args
    posted_url = args[0] if args else kwargs.get("url")
    assert posted_url == "http://localhost:8000/api/sql/execute"
    assert kwargs["json"]["datasourceId"] == 12345
    assert kwargs["json"]["sql"] == "SELECT * FROM users LIMIT 10"

    content = Path(result.csv_path).read_text(encoding="utf-8")
    assert "Alice" in content
    assert "Bob" in content
