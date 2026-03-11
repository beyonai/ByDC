import csv
import pytest
from pathlib import Path
from datacloud_data_sdk.plan.models import PlanAggregation
from datacloud_data_sdk.aggregator.direct_aggregator import DirectAggregator
from datacloud_data_sdk.aggregator.sqlite_aggregator import SqliteAggregator


def make_csv(tmp_path: Path, filename: str, rows: list[dict]) -> str:
    p = tmp_path / filename
    with p.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return str(p)


@pytest.mark.asyncio
async def test_direct_aggregator_returns_records(tmp_path: Path) -> None:
    csv_path = make_csv(tmp_path, "result.csv", [{"bo_id": "B001", "bo_name": "5G项目"}])
    agg = PlanAggregation(
        strategy="DIRECT",
        final_step_id="step_1",
        columns=[
            {"name": "bo_id", "label": "商机ID", "type": "string"},
            {"name": "bo_name", "label": "商机名称", "type": "string"},
        ],
    )
    records = await DirectAggregator().aggregate(agg, {"step_1": csv_path})
    assert records == [{"bo_id": "B001", "bo_name": "5G项目"}]


@pytest.mark.asyncio
async def test_sqlite_aggregator_joins_csvs(tmp_path: Path) -> None:
    emp_csv = make_csv(tmp_path, "api_emp.csv", [{"emp_id": "U001", "emp_name": "test_user"}])
    bo_csv = make_csv(tmp_path, "db_bo.csv", [{"emp_id": "U001", "bo_name": "5G项目"}])
    agg = PlanAggregation(
        strategy="SQLITE_MEM",
        sqlite_sql="SELECT e.emp_name, b.bo_name FROM api_emp e JOIN db_bo b ON e.emp_id = b.emp_id",
        columns=[
            {"name": "emp_name", "label": "员工姓名", "type": "string"},
            {"name": "bo_name", "label": "商机名称", "type": "string"},
        ],
    )
    records = await SqliteAggregator().aggregate(
        agg,
        {"step_api_emp": emp_csv, "step_db_bo": bo_csv},
        csv_table_names={"step_api_emp": "api_emp", "step_db_bo": "db_bo"},
    )
    assert records[0]["emp_name"] == "test_user"
    assert records[0]["bo_name"] == "5G项目"
