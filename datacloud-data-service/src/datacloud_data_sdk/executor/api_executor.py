"""ApiExecutor: HTTP API 调用 + CSV 输出。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from datacloud_data_sdk.context import get_current_context
from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
from datacloud_data_sdk.utils.curl_logger import log_curl
from datacloud_data_sdk.exceptions import ApiExecutionError
from datacloud_data_sdk.executor.models import ApiExecTask
from datacloud_data_sdk.executor.response_mapping import extract_by_mapping_path
from datacloud_data_sdk.executor.step_results import StepResults
from datacloud_data_sdk.sql_executor.result_converter import ResultConverter


@dataclass
class ApiExecResult:
    csv_path: str
    row_count: int = 0


class ApiExecutor:
    def __init__(
        self,
        function_configs: dict[str, dict[str, Any]],
        csv_base_dir: str = "/tmp/datacloud_csv",
    ) -> None:
        self._configs = function_configs
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

        config = self._configs.get(task.function_code, {})
        url = self._build_url(config)
        headers = self._build_headers()

        log_curl("POST", url, headers=headers, body=params)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=params, headers=headers)

        if resp.status_code >= 400:
            raise ApiExecutionError(task.function_code, resp.status_code, resp.text)

        data = resp.json()
        if task.output_params:
            records = extract_by_mapping_path(
                data if isinstance(data, dict) else {},
                task.output_params,
            )
            columns = [p[0] for p in task.output_params] if not records else None
        else:
            records = self._extract_records(data)
            columns = None
        csv_path = self._csv.get_path(request_id, task.csv_table_name or task.output_ref)
        row_count = ResultConverter.to_csv(records, csv_path, columns=columns)
        return ApiExecResult(csv_path=str(csv_path), row_count=row_count)

    def _build_url(self, config: dict[str, Any]) -> str:
        servers = config.get("servers", [])
        base_url = servers[0]["url"] if servers else "http://localhost:8080"
        paths = config.get("paths", {})
        path = next(iter(paths), "")
        return f"{base_url}{path}"

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        try:
            ctx = get_current_context()
            if ctx.token:
                headers["Authorization"] = f"Bearer {ctx.token}"
            if ctx.tenant_id:
                headers["X-Tenant-Id"] = ctx.tenant_id
        except Exception:
            pass
        return headers

    def _read_bind_values(self, csv_path: str, key: str) -> list[str]:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row[key] for row in reader if key in row]

    def _extract_records(self, data: Any) -> list[dict[str, Any]]:
        """Extract list of records from API response."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "records", "items", "list", "users", "results"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [data]
        return [{"value": data}]
