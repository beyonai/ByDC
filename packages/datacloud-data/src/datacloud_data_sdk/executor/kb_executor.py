"""
知识库执行器模块

本模块提供知识库检索的执行能力，通过 HTTP 调用知识元数据服务执行检索。
支持将检索结果写入 CSV 文件供后续步骤使用。

核心功能：
- 调用知识元数据服务的 /api/v1/knowledgeItems/searchFile 接口执行检索
- 支持元数据过滤和 topK 参数
- 将检索结果转换为 CSV 格式存储

使用示例：
    kb_configs = {"kb_main": {"endpoint": "http://rag-service:8000"}}
    executor = KbExecutor(kb_configs)
    csv_path = await executor.execute(task, request_id, step_results)
"""

from __future__ import annotations

from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
from datacloud_data_sdk.executor.kb_search_backend import (
    HttpKnowledgeSearchBackend,
    KnowledgeSearchBackend,
    KnowledgeSearchRequest,
)
from datacloud_data_sdk.executor.models import KbExecTask
from datacloud_data_sdk.executor.step_results import StepResults
from datacloud_data_sdk.sql_executor.result_converter import ResultConverter


class KbExecutor:
    """
    知识库文件级检索执行器

    通过 HTTP POST 调用知识元数据服务的 searchFile 接口执行知识库检索。

    Attributes:
        _configs: 知识库配置字典，key 为数据源别名，value 包含 endpoint
        _csv: CSV 存储管理器

    Example:
        kb_configs = {"kb_main": {"endpoint": "http://localhost:8000"}}
        executor = KbExecutor(kb_configs)
        csv_path = await executor.execute(task, "req_001", step_results)
    """

    def __init__(
        self,
        kb_configs: dict[str, dict] | None = None,
        csv_base_dir: str = "/tmp/datacloud_csv",
        search_backend: KnowledgeSearchBackend | None = None,
    ) -> None:
        """
        初始化知识库执行器

        Args:
            kb_configs: 知识库配置字典
                key: 数据源别名
                value: {"endpoint": str} 知识元数据服务 base URL
            csv_base_dir: CSV 临时文件根目录
            search_backend: 自定义知识库检索后端；不传时使用默认 HTTP 实现
        """
        self._search_backend = search_backend or HttpKnowledgeSearchBackend(kb_configs)
        self._csv = CsvStorageManager(csv_base_dir)

    async def execute(
        self,
        task: KbExecTask,
        request_id: str,
        step_results: StepResults,
    ) -> str:
        """
        执行知识库检索

        执行流程：
        1. 验证数据源配置
        2. 构建 RAG 请求体
        3. 调用知识元数据服务 searchFile 接口
        4. 将检索结果写入 CSV 文件

        Args:
            task: 知识库执行任务
            request_id: 请求 ID
            step_results: 前置步骤结果（预留用于参数绑定）

        Returns:
            str: 写入的 CSV 文件路径

        Raises:
            DataSourceUnavailableError: 数据源未配置时抛出
            KbExecutionError: RAG 调用失败时抛出
        """
        result = await self._search_backend.search(
            KnowledgeSearchRequest(
                object_code=task.datasource_alias,
                datasource_alias=task.datasource_alias,
                query=task.query,
                filters=task.tags,
                limit=10,
            )
        )

        path = self._csv.get_path(request_id, task.output_ref)
        ResultConverter.to_csv(result.records, path)
        return str(path)
