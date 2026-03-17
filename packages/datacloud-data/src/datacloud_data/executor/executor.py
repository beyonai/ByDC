"""Executor: 统一调度执行任务。"""

from __future__ import annotations
from typing import Any

from datacloud_data.csv_storage.manager import CsvStorageManager
from datacloud_data.executor.api_executor import ApiExecutor
from datacloud_data.executor.kb_executor import KbExecutor
from datacloud_data.executor.models import ApiExecTask, KbExecTask, ScriptExecTask, SqlExecTask
from datacloud_data.executor.script_executor import ScriptExecutor
from datacloud_data.executor.step_results import StepResult, StepResults
from datacloud_data.sql_executor.result_converter import ResultConverter
from datacloud_data.sql_executor.sql_executor import SqlExecutor


class Executor:
    def __init__(
        self,
        sql_executor: SqlExecutor | None = None,
        api_executor: ApiExecutor | None = None,
        script_executor: ScriptExecutor | None = None,
        kb_executor: KbExecutor | None = None,
        csv_base_dir: str = "/tmp/datacloud_csv",
    ) -> None:
        self._sql = sql_executor
        self._api = api_executor
        self._script = script_executor
        self._kb = kb_executor
        self._csv_base_dir = csv_base_dir

    async def run(
        self,
        tasks: list[SqlExecTask | ApiExecTask | ScriptExecTask | KbExecTask],
        request_id: str,
        step_ids: list[str] | None = None,
    ) -> StepResults:
        """Execute tasks sequentially, return StepResults."""
        step_results = StepResults()
        for i, task in enumerate(tasks):
            exec_key = f"step_{i}"
            step_id = step_ids[i] if step_ids and i < len(step_ids) else exec_key
            tbl = getattr(task, "output_ref", "") or step_id

            if isinstance(task, SqlExecTask):
                if self._sql is None:
                    raise RuntimeError("SqlExecutor not configured")
                result = await self._sql.execute(task, request_id, step_results)
                step_results.add(
                    StepResult(step_id, exec_key, task.output_ref, result.csv_path, tbl)
                )
            elif isinstance(task, ApiExecTask):
                if self._api is None:
                    raise RuntimeError("ApiExecutor not configured")
                result = await self._api.execute(task, request_id, step_results)
                step_results.add(
                    StepResult(step_id, exec_key, task.output_ref, result.csv_path, tbl)
                )
            elif isinstance(task, ScriptExecTask):
                if self._script is None:
                    raise RuntimeError("ScriptExecutor not configured")
                script_result = await self._script.execute(
                    task.script, task.params, action_code=task.action_code
                )
                records = script_result.get("records") if isinstance(script_result, dict) else None
                if isinstance(records, list) and records and isinstance(records[0], dict):
                    pass
                else:
                    records = [script_result] if isinstance(script_result, dict) else [{"value": str(script_result)}]
                csv_mgr = CsvStorageManager(self._csv_base_dir)
                out_path = csv_mgr.get_path(request_id, task.output_ref or step_id)
                ResultConverter.to_csv(records, out_path)
                csv_path = str(out_path)
                step_results.add(
                    StepResult(step_id, exec_key, task.output_ref, csv_path, tbl)
                )
            elif isinstance(task, KbExecTask):
                if self._kb is None:
                    raise RuntimeError("KbExecutor not configured")
                csv_path = await self._kb.execute(task, request_id, step_results)
                step_results.add(
                    StepResult(step_id, exec_key, task.output_ref, csv_path, tbl)
                )
        return step_results
