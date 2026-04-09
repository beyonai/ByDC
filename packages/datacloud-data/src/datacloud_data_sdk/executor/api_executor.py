"""
API 执行器模块

本模块提供 API 调用的执行能力，委托 Action 执行 API 请求。
支持步骤间的数据绑定，将执行结果输出为 CSV 文件。

核心功能：
- 执行对象上的动作 API 调用
- 支持从前置步骤绑定参数值
- 将结果转换为 CSV 格式存储

使用示例：
    executor = ApiExecutor(loader, csv_base_dir="/tmp/csv")
    result = await executor.execute(task, "req_001", step_results)
"""

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
    """
    API 执行结果

    Attributes:
        csv_path: 结果 CSV 文件路径
        row_count: 返回的记录行数
    """

    csv_path: str
    row_count: int = 0


class ApiExecutor:
    """
    API 执行器

    委托 Action 执行 API 调用，封装步骤绑定与 CSV 输出。

    Attributes:
        _loader: 本体加载器引用
        _csv: CSV 存储管理器

    Example:
        executor = ApiExecutor(loader)
        result = await executor.execute(task, request_id, step_results)
    """

    def __init__(
        self,
        loader: Any,
        csv_base_dir: str = "/tmp/datacloud_csv",
    ) -> None:
        """
        初始化 API 执行器

        Args:
            loader: 本体加载器实例
            csv_base_dir: CSV 文件存储目录
        """
        self._loader = loader
        self._csv = CsvStorageManager(csv_base_dir)

    async def execute(
        self,
        task: ApiExecTask,
        request_id: str,
        step_results: StepResults | None = None,
    ) -> ApiExecResult:
        """
        执行 API 任务

        执行流程：
        1. 处理步骤绑定，从前置步骤获取参数值
        2. 调用对象动作执行 API
        3. 将结果保存为 CSV 文件

        Args:
            task: API 执行任务
            request_id: 请求 ID
            step_results: 步骤结果集合，用于获取绑定值

        Returns:
            ApiExecResult: 执行结果，包含 CSV 路径和行数
        """
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
