"""
SQL 执行器模块

本模块提供 SQL 查询的执行能力，支持多种数据库类型。
执行结果自动转换为 CSV 文件格式存储。

核心功能：
- 执行 SQL 查询任务
- 支持步骤间的参数绑定
- 自动处理 SQL 别名引用
- 将结果转换为 CSV 格式

使用示例：
    executor = SqlExecutor(ds_manager, csv_base_dir="/tmp/csv")
    result = await executor.execute(task, request_id, step_results)
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
from datacloud_data_sdk.executor.models import SqlExecTask
from datacloud_data_sdk.executor.step_results import StepResults
from datacloud_data_sdk.result_term_converter import ResultTermConverter
from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager
from datacloud_data_sdk.sql_executor.models import SqlExecResult
from datacloud_data_sdk.sql_executor.result_converter import ResultConverter
from datacloud_data_sdk.sql_executor.select_column_parser import extract_select_columns
from datacloud_data_sdk.sql_executor.sql_alias_quoter import quote_aliases

if TYPE_CHECKING:
    from datacloud_data_sdk.ontology.term_loader import TermLoader
    from datacloud_data_sdk.plan.models import ObjectViewPayload

logger = logging.getLogger(__name__)


class SqlExecutor:
    """
    SQL 执行器

    执行 SQL 查询任务，支持参数绑定和结果 CSV 输出。

    Attributes:
        _ds: 数据源管理器
        _csv: CSV 存储管理器

    Example:
        executor = SqlExecutor(ds_manager)
        result = await executor.execute(sql_task, "req_001", step_results)
    """

    def __init__(
        self,
        ds_manager: DataSourceManager,
        csv_base_dir: str | None = None,
        payload: ObjectViewPayload | None = None,
        term_loader: TermLoader | None = None,
    ) -> None:
        """
        初始化 SQL 执行器

        Args:
            ds_manager: 数据源管理器实例
            csv_base_dir: CSV 文件存储目录，None 则使用系统临时目录
        """
        self._ds = ds_manager
        self._csv = CsvStorageManager(csv_base_dir)
        self._payload = payload
        self._term_result_converter = ResultTermConverter(term_loader)

    async def execute(
        self,
        task: SqlExecTask,
        request_id: str,
        step_results: StepResults,
    ) -> SqlExecResult:
        """
        执行 SQL 任务

        执行流程：
        1. 处理步骤绑定，替换 SQL 中的占位符
        2. 获取对应数据源的连接器
        3. 执行 SQL 查询
        4. 将结果写入 CSV 文件

        Args:
            task: SQL 执行任务
            request_id: 请求 ID
            step_results: 步骤结果集合，用于获取绑定值

        Returns:
            SqlExecResult: 执行结果，包含 CSV 路径和行数
        """
        sql = task.sql_template

        if task.bind_from_step and task.bind_key:
            csv_path = step_results.get_path(task.bind_from_step)
            if csv_path and Path(csv_path).exists():
                values = self._read_bind_values(csv_path, task.bind_key)
                sql = sql.replace("{bind_values}", ",".join(f"'{v}'" for v in values))

        connector = self._ds.get_connector(task.datasource_alias)
        sql = quote_aliases(sql, connector.config.db_type)
        logger.info("[SQL] step=%s ds=%s\n%s", task.output_ref, task.datasource_alias, sql)
        records = await connector.execute(sql)
        records = self._term_result_converter.convert_by_datasource_payload(
            records,
            self._payload,
            task.datasource_alias,
        )
        logger.info("[SQL] executed, got %d records", len(records))

        out_path = self._csv.get_path(request_id, task.output_ref)
        logger.info("[SQL] writing to CSV: %s", out_path)
        columns = extract_select_columns(task.sql_template) if not records else None
        row_count = ResultConverter.to_csv(records, out_path, columns=columns)
        logger.info("[SQL] wrote %d rows to CSV", row_count)
        return SqlExecResult(csv_path=str(out_path), row_count=row_count)

    def _read_bind_values(self, csv_path: str, key: str) -> list[str]:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row[key] for row in reader if key in row]
