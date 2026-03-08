import pytest
from pathlib import Path
from datacloud_data_sdk.sql_executor.models import DataSourceConfig
from datacloud_data_sdk.executor.models import SqlExecTask
from datacloud_data_sdk.sql_executor.sql_executor import SqlExecutor
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager

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
    result = await executor.execute(task, request_id="req1", step_results={})
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
    result = await executor.execute(
        task, request_id="req1", step_results={"step_1_api": str(step_csv)}
    )
    content = Path(result.csv_path).read_text()
    assert "U001" in content
