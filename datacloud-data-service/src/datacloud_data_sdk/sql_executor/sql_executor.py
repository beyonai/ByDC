"""SqlExecutor: SQL 执行 + CSV 输出。"""
from __future__ import annotations
import csv
from pathlib import Path
from typing import Any
from datacloud_data_sdk.executor.models import SqlExecTask
from datacloud_data_sdk.executor.step_results import StepResults
from datacloud_data_sdk.sql_executor.models import SqlExecResult
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
from datacloud_data_sdk.sql_executor.result_converter import ResultConverter
from datacloud_data_sdk.sql_executor.select_column_parser import extract_select_columns
from datacloud_data_sdk.sql_executor.sql_alias_quoter import quote_aliases
from datacloud_data_sdk.csv_storage.manager import CsvStorageManager


class SqlExecutor:
    def __init__(self, ds_manager: DataSourceManager, csv_base_dir: str = "/tmp/datacloud_csv") -> None:
        self._ds = ds_manager
        self._csv = CsvStorageManager(csv_base_dir)

    async def execute(
        self,
        task: SqlExecTask,
        request_id: str,
        step_results: StepResults,
    ) -> SqlExecResult:
        sql = task.sql_template

        if task.bind_from_step and task.bind_key:
            csv_path = step_results.get_path(task.bind_from_step)
            if csv_path and Path(csv_path).exists():
                values = self._read_bind_values(csv_path, task.bind_key)
                sql = sql.replace("{bind_values}", ",".join(f"'{v}'" for v in values))

        connector = self._ds.get_connector(task.datasource_alias)
        sql = quote_aliases(sql, connector.config.db_type)
        records = await connector.execute(sql)

        out_path = self._csv.get_path(request_id, task.csv_table_name or task.output_ref)
        columns = extract_select_columns(task.sql_template) if not records else None
        row_count = ResultConverter.to_csv(records, out_path, columns=columns)
        return SqlExecResult(csv_path=str(out_path), row_count=row_count)

    def _read_bind_values(self, csv_path: str, key: str) -> list[str]:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row[key] for row in reader if key in row]
