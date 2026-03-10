"""Executor: 统一调度执行任务。"""
from __future__ import annotations
from typing import Any

from datacloud_data_sdk.executor.api_executor import ApiExecutor
from datacloud_data_sdk.executor.kb_executor import KbExecutor
from datacloud_data_sdk.executor.models import ApiExecTask, KbExecTask, ScriptExecTask, SqlExecTask
from datacloud_data_sdk.executor.script_executor import ScriptExecutor
from datacloud_data_sdk.sql_executor.sql_executor import SqlExecutor


class Executor:
    def __init__(
        self,
        sql_executor: SqlExecutor | None = None,
        api_executor: ApiExecutor | None = None,
        script_executor: ScriptExecutor | None = None,
        kb_executor: KbExecutor | None = None,
    ) -> None:
        self._sql = sql_executor
        self._api = api_executor
        self._script = script_executor
        self._kb = kb_executor

    async def run(
        self,
        tasks: list[SqlExecTask | ApiExecTask | ScriptExecTask | KbExecTask],
        request_id: str,
        step_ids: list[str] | None = None,
    ) -> dict[str, str]:
        """Execute tasks sequentially, return step_id -> csv_path mapping.

        step_ids: 可选，与 tasks 一一对应的 step_id 列表，用于 bind_from_step 查找。
        """
        step_results: dict[str, str] = {}
        for i, task in enumerate(tasks):
            exec_key = f"step_{i}"
            step_id = step_ids[i] if step_ids and i < len(step_ids) else exec_key

            if isinstance(task, SqlExecTask):
                if self._sql is None:
                    raise RuntimeError("SqlExecutor not configured")
                result = await self._sql.execute(task, request_id, step_results)
                step_results[exec_key] = result.csv_path
                step_results[step_id] = result.csv_path
                if task.output_ref:
                    step_results[task.output_ref] = result.csv_path
            elif isinstance(task, ApiExecTask):
                if self._api is None:
                    raise RuntimeError("ApiExecutor not configured")
                result = await self._api.execute(task, request_id, step_results)
                step_results[exec_key] = result.csv_path
                step_results[step_id] = result.csv_path
                if task.output_ref:
                    step_results[task.output_ref] = result.csv_path
            elif isinstance(task, ScriptExecTask):
                if self._script is None:
                    raise RuntimeError("ScriptExecutor not configured")
                script_result = await self._script.execute(
                    task.script, task.params, action_code=task.action_code
                )
                step_results[exec_key] = str(script_result)
                step_results[step_id] = str(script_result)
                if task.output_ref:
                    step_results[task.output_ref] = str(script_result)
            elif isinstance(task, KbExecTask):
                if self._kb is None:
                    raise RuntimeError("KbExecutor not configured")
                csv_path = await self._kb.execute(task, request_id, step_results)
                step_results[exec_key] = csv_path
                step_results[step_id] = csv_path
                if task.output_ref:
                    step_results[task.output_ref] = csv_path
        return step_results
