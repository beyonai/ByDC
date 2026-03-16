"""ApiExecutor: 委托 Action 执行 API，封装 step 绑定与 CSV 输出。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
from datacloud_data_sdk.executor.models import ApiExecTask
from datacloud_data_sdk.executor.step_results import StepResults
from datacloud_data_sdk.sql_executor.result_converter import ResultConverter

@dataclass
class ApiExecResult:
    csv_path: str
    row_count: int = 0


class ApiExecutor:
    def __init__(
        self,
        loader: Any,
        csv_base_dir: str = "/tmp/datacloud_csv",
    ) -> None:
        self._loader = loader
        self._csv = CsvStorageManager(csv_base_dir)

    async def execute(
        self,
        task: ApiExecTask,
        request_id: str,
        step_results: StepResults | None = None,
    ) -> ApiExecResult:
        params = dict(task.params)
        if task.bind_from_step and task.bind_key and step_results:
            bind_path = step_results.get_path(task.bind_from_step)
            if bind_path and Path(bind_path).exists():
                values = self._read_bind_values(bind_path, task.bind_key)
                if values:
                    params[task.bind_key] = values[0]

        obj = self._loader.get_object(task.object_code)
        result = await obj.invoke_action(task.action_code, params)

        records = result.get("records", [])
        meta = result.get("meta", {})
        columns = meta.get("columns")

        csv_path = self._csv.get_path(request_id, task.output_ref)
        row_count = ResultConverter.to_csv(records, csv_path, columns=columns)
        return ApiExecResult(csv_path=str(csv_path), row_count=row_count)

    def _read_bind_values(self, csv_path: str, key: str) -> list[str]:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row[key] for row in reader if key in row]
