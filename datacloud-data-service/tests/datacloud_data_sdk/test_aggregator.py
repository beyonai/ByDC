import csv
import pytest
from pathlib import Path
from datacloud_data_sdk.plan.models import PlanAggregation
from datacloud_data_sdk.aggregator.direct_aggregator import DirectAggregator
from datacloud_data_sdk.aggregator.sqlite_aggregator import SqliteAggregator
from datacloud_data_sdk.executor.step_results import StepResult, StepResults


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
    sr = StepResults()
    sr.add(StepResult("step_1", "step_1", "", csv_path, ""))
    records = await DirectAggregator().aggregate(agg, sr)
    assert records == [{"bo_id": "B001", "bo_name": "5G项目"}]


@pytest.mark.asyncio
async def test_direct_aggregator_uses_object_field_names_as_keys(tmp_path: Path) -> None:
    """CSV 列名（=SQL AS 别名）与 aggregation.columns[].name 一致时，输出正确。"""
    csv_path = make_csv(
        tmp_path,
        "result.csv",
        [
            {
                "completedContractAmount": "100",
                "empNo": "0027000851",
                "periodValue": "202501",
            }
        ],
    )
    agg = PlanAggregation(
        strategy="DIRECT",
        final_step_id="step_1",
        columns=[
            {"name": "completedContractAmount", "label": "完成合同金额", "type": "number"},
            {"name": "empNo", "label": "工号", "type": "string"},
            {"name": "periodValue", "label": "周期", "type": "string"},
        ],
    )
    sr = StepResults()
    sr.add(StepResult("step_1", "step_1", "", csv_path, ""))
    records = await DirectAggregator().aggregate(agg, sr)
    assert len(records) == 1
    assert records[0]["completedContractAmount"] == "100"
    assert records[0]["empNo"] == "0027000851"
    assert records[0]["periodValue"] == "202501"


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
    sr = StepResults()
    sr.add(StepResult("step_api_emp", "step_api_emp", "api_emp", emp_csv, "api_emp"))
    sr.add(StepResult("step_db_bo", "step_db_bo", "db_bo", bo_csv, "db_bo"))
    records = await SqliteAggregator().aggregate(agg, sr)
    assert records[0]["emp_name"] == "test_user"
    assert records[0]["bo_name"] == "5G项目"
