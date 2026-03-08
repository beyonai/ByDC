"""KbExecutor: 知识库检索执行，返回 records。"""
from __future__ import annotations

from typing import Any

import httpx

from datacloud_data_sdk.exceptions import DataSourceUnavailableError, KbExecutionError
from datacloud_data_sdk.executor.models import KbExecTask


class KbExecutor:
    """知识库 RAG 检索执行器，通过 HTTP POST 调用 RAG 服务 /retrieve 接口。"""

    def __init__(self, kb_configs: dict[str, dict]) -> None:
        """
        Args:
            kb_configs: key 为 datasource alias，value 为 {"endpoint": str}（RAG 服务 base URL）
        """
        self._configs = kb_configs

    async def execute(
        self,
        task: KbExecTask,
        request_id: str,
        step_results: dict[str, str],
    ) -> list[dict]:
        """
        执行知识库检索，返回 records 列表。

        Args:
            task: 知识库执行任务
            request_id: 请求 ID（预留）
            step_results: 前置步骤结果（预留）

        Returns:
            list[dict]: 每个元素为 {"content": str, "score": float?, **metadata}
        """
        if task.datasource_alias not in self._configs:
            raise DataSourceUnavailableError(task.datasource_alias)

        config = self._configs[task.datasource_alias]
        endpoint = config.get("endpoint")
        if not endpoint:
            raise KbExecutionError(
                task.datasource_alias,
                "endpoint not configured in kb_configs",
            )

        url = endpoint.rstrip("/") + "/retrieve"
        body: dict[str, Any] = {
            "query": task.query,
            "tags": task.tags,
            "top_k": 10,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=body)
        except httpx.HTTPError as e:
            raise KbExecutionError(task.datasource_alias, str(e)) from e

        if resp.status_code >= 400:
            raise KbExecutionError(
                task.datasource_alias,
                f"HTTP {resp.status_code}: {resp.text}",
            )

        try:
            data = resp.json()
        except Exception as e:
            raise KbExecutionError(
                task.datasource_alias,
                f"invalid JSON response: {e}",
            ) from e

        results = data.get("results")
        if not isinstance(results, list):
            return []

        records: list[dict] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            content = item.get("content", "")
            record: dict[str, Any] = {"content": content}
            if "score" in item:
                record["score"] = item["score"]
            metadata = item.get("metadata")
            if metadata and isinstance(metadata, dict):
                record.update(metadata)
            records.append(record)

        return records
