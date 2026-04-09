"""
执行器模块

本模块提供统一的任务执行调度能力，支持多种执行类型的任务：
- SQL 执行：数据库查询
- API 执行：外部 API 调用
- 脚本执行：Python 脚本执行
- 知识库执行：知识库检索

执行器按顺序执行任务列表，支持步骤间的数据绑定，
并将结果统一输出为 CSV 文件格式。

使用示例：
    executor = Executor(
        sql_executor=sql_exec,
        api_executor=api_exec,
        script_executor=script_exec
    )
    results = await executor.run(tasks, request_id="req_123")
"""

from __future__ import annotations
from typing import Any

from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
from datacloud_data_sdk.executor.api_executor import ApiExecutor
from datacloud_data_sdk.executor.kb_executor import KbExecutor
from datacloud_data_sdk.executor.models import ApiExecTask, KbExecTask, ScriptExecTask, SqlExecTask
from datacloud_data_sdk.executor.script_executor import ScriptExecutor
from datacloud_data_sdk.executor.step_results import StepResult, StepResults
from datacloud_data_sdk.sql_executor.result_converter import ResultConverter
from datacloud_data_sdk.sql_executor.sql_executor import SqlExecutor


class Executor:
    """
    统一任务执行器

    协调多种类型的执行器，按顺序执行任务列表。
    支持步骤间的数据绑定，将结果统一输出为 CSV 格式。

    Attributes:
        _sql: SQL 执行器
        _api: API 执行器
        _script: 脚本执行器
        _kb: 知识库执行器
        _csv_base_dir: CSV 文件存储目录

    Example:
        executor = Executor(sql_executor=sql_exec)
        results = await executor.run([sql_task], "req_001")
        csv_path = results.get_path("step_0")
    """

    def __init__(
        self,
        sql_executor: SqlExecutor | None = None,
        api_executor: ApiExecutor | None = None,
        script_executor: ScriptExecutor | None = None,
        kb_executor: KbExecutor | None = None,
        csv_base_dir: str = "/tmp/datacloud_csv",
    ) -> None:
        """
        初始化执行器

        Args:
            sql_executor: SQL 执行器实例
            api_executor: API 执行器实例
            script_executor: 脚本执行器实例
            kb_executor: 知识库执行器实例
            csv_base_dir: CSV 文件存储的基础目录
        """
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
        timeout: float | None = None,
    ) -> StepResults:
        """
        执行任务列表

        按顺序执行所有任务，支持步骤间的数据绑定。
        每个任务的执行结果会保存为 CSV 文件。

        Args:
            tasks: 任务列表，支持 SQL、API、脚本、知识库任务
            request_id: 请求 ID，用于组织输出文件
            step_ids: 可选的步骤 ID 列表，用于标识每个任务
            timeout: 可选的超时时间（秒），默认无超时

        Returns:
            StepResults: 包含所有步骤执行结果的对象

        Raises:
            RuntimeError: 当任务类型对应的执行器未配置时抛出
            asyncio.TimeoutError: 当执行超时时抛出
        """
        import logging
        import asyncio

        logger = logging.getLogger(__name__)

        async def _run_tasks():
            logger.info(
                "Executor.run: starting with %d tasks, request_id=%s", len(tasks), request_id
            )
            step_results = StepResults()
            for i, task in enumerate(tasks):
                exec_key = f"step_{i}"
                step_id = step_ids[i] if step_ids and i < len(step_ids) else exec_key
                # tbl 用于标识输出表，优先使用 output_ref，否则使用 step_id
                tbl = getattr(task, "output_ref", "") or step_id
                logger.info(
                    "Executor.run: task %d: exec_key=%s step_id=%s output_ref=%s",
                    i,
                    exec_key,
                    step_id,
                    getattr(task, "output_ref", ""),
                )

                if isinstance(task, SqlExecTask):
                    if self._sql is None:
                        raise RuntimeError("SqlExecutor not configured")
                    result = await self._sql.execute(task, request_id, step_results)
                    logger.info(
                        "Executor.run: SqlExecTask completed, csv_path=%s row_count=%s",
                        result.csv_path,
                        result.row_count,
                    )
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
                    records = (
                        script_result.get("records") if isinstance(script_result, dict) else None
                    )
                    if isinstance(records, list) and records and isinstance(records[0], dict):
                        pass
                    else:
                        records = (
                            [script_result]
                            if isinstance(script_result, dict)
                            else [{"value": str(script_result)}]
                        )
                    csv_mgr = CsvStorageManager(self._csv_base_dir)
                    out_path = csv_mgr.get_path(request_id, task.output_ref or step_id)
                    ResultConverter.to_csv(records, out_path)
                    csv_path = str(out_path)
                    step_results.add(StepResult(step_id, exec_key, task.output_ref, csv_path, tbl))
                elif isinstance(task, KbExecTask):
                    if self._kb is None:
                        raise RuntimeError("KbExecutor not configured")
                    csv_path = await self._kb.execute(task, request_id, step_results)
                    step_results.add(StepResult(step_id, exec_key, task.output_ref, csv_path, tbl))
            return step_results

        # 如果指定了超时，使用 asyncio.wait_for
        if timeout is not None:
            return await asyncio.wait_for(_run_tasks(), timeout=timeout)
        else:
            return await _run_tasks()
