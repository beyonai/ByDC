"""
CSV 临时存储管理模块

本模块提供 CSV 文件的存储和管理功能，用于处理大数据量查询结果的导出。

核心功能：
- CSV 文件存储和读取
- 导出文件管理
- 请求目录清理
- 路径穿越防护

使用示例：
    manager = CsvStorageManager("/tmp/datacloud_csv")
    file_id, path = manager.save_export(records, columns, meta)
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from datacloud_data_sdk.file_storage.base import ResultFileStorage
from datacloud_data_sdk.file_storage.local import LocalResultFileStorage
from datacloud_data_sdk.file_storage.scoped_paths import sanitize_path_segment, shared_workspace_dir
from datacloud_data_sdk.sql_executor.result_converter import ResultConverter

logger = logging.getLogger(__name__)


class CsvStorageManager:
    """
    CSV 存储管理器

    管理 CSV 文件的存储、读取和清理。

    Attributes:
        _base: 基础存储目录

    Example:
        manager = CsvStorageManager("/tmp/datacloud_csv")
        path = manager.get_path("req_123", "step_1")
        manager.save_export(records, columns, meta)
    """

    def __init__(
        self,
        base_dir: str | None = None,
        result_file_storage: ResultFileStorage | None = None,
        export_root_dir: str = "/datacloud",
    ) -> None:
        """
        初始化 CSV 存储管理器

        Args:
            base_dir: 基础存储目录，None 则使用系统临时目录
        """
        if base_dir is None:
            # 使用系统临时目录，跨平台兼容
            base_dir = os.path.join(tempfile.gettempdir(), "datacloud_csv")
        self._base = Path(base_dir)
        self._result_file_storage = result_file_storage or LocalResultFileStorage(self._base)
        self._export_root_dir = export_root_dir.rstrip("/") or "/datacloud"

    @staticmethod
    def _sanitize_path_segment(value: str) -> str:
        """Sanitize a single path segment to avoid invalid or unsafe separators."""
        return sanitize_path_segment(value)

    def _effective_base_dir(self) -> Path:
        """Resolve the CSV base dir for the current invocation.

        When running inside the gateway/agent flow, prefer the current task
        workspace so exports and step CSVs stay inside that workspace.
        """
        try:
            from datacloud_data_sdk.context import get_current_context
        except ImportError:
            return self._base

        try:
            ctx = get_current_context()
        except Exception:
            return self._base

        workspace_dir = str(getattr(ctx, "workspace_dir", "") or "").strip()
        base_dir = self._base
        if workspace_dir:
            base_dir = self._shared_workspace_dir(Path(workspace_dir))

        user_id = self._sanitize_path_segment(str(getattr(ctx, "user_id", "") or ""))
        session_id = self._sanitize_path_segment(str(getattr(ctx, "session_id", "") or ""))
        if user_id and session_id:
            return base_dir / user_id / "sessions" / session_id
        return base_dir

    @staticmethod
    def _shared_workspace_dir(workspace_dir: Path) -> Path:
        """Normalize to the nearest shared ``private/public`` workspace root."""
        return shared_workspace_dir(workspace_dir)

    def get_path(self, request_id: str, output_ref: str) -> Path:
        """
        获取 CSV 文件路径

        为指定请求和输出引用创建 CSV 文件路径。

        Args:
            request_id: 请求 ID
            output_ref: 输出引用名称

        Returns:
            Path: CSV 文件路径
        """
        # 替换 Windows 非法字符（冒号、反斜杠等）
        safe_request_id = self._sanitize_path_segment(request_id)
        dir_path = self._effective_base_dir() / safe_request_id
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / f"{output_ref}.csv"

    def save_export(
        self,
        records: list[dict[str, Any]],
        columns: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> tuple[str, Path]:
        """
        保存导出文件

        将记录保存到导出目录，返回文件 ID 和路径。

        Args:
            records: 记录列表
            columns: 列名列表（可选）
            meta: 元数据（可选）

        Returns:
            tuple: (file_id, 文件路径)
        """
        file_id = str(uuid.uuid4())
        file_path = self._export_file_path(file_id, ".csv")
        csv_content = ResultConverter.to_csv_text(records, columns=columns)
        self._result_file_storage.write_text(file_path, csv_content)

        stored_meta = dict(meta or {})
        stored_meta.setdefault("file_url", file_path)
        stored_meta["storage_type"] = self._result_file_storage.storage_type
        meta_path = self._export_file_path(file_id, "_meta.json")
        self._result_file_storage.write_text(
            meta_path,
            json.dumps(stored_meta, ensure_ascii=False, default=str),
        )

        return file_id, Path(file_path)

    def _export_file_path(self, file_id: str, suffix: str) -> str:
        return f"{self._export_root_dir}/exports/{file_id}{suffix}"

    def get_export_path(self, file_id: str) -> Path | None:
        """
        获取导出文件路径

        根据 file_id 获取导出文件路径，包含路径穿越防护校验。

        Args:
            file_id: 文件 ID（UUID 格式）

        Returns:
            Path | None: 文件路径，校验失败返回 None
        """
        if not re.match(r"^[a-f0-9\-]{36}$", file_id):
            return None
        if isinstance(self._result_file_storage, LocalResultFileStorage):
            path = self._result_file_storage.resolve_path(self._export_file_path(file_id, ".csv"))
            if path.exists() and path.is_file():
                return path
        return None

    def get_export_meta(self, file_id: str) -> dict[str, Any] | None:
        """
        获取导出文件元数据

        根据 file_id 获取导出文件的元数据信息。

        Args:
            file_id: 文件 ID（UUID 格式）

        Returns:
            dict | None: 元数据字典，不存在则返回 None
        """
        if not re.match(r"^[a-f0-9\-]{36}$", file_id):
            return None
        meta_path = self._export_file_path(file_id, "_meta.json")
        try:
            content = self._result_file_storage.read_text(meta_path)
            if not content:
                return None
            return json.loads(content)
        except Exception as exc:
            logger.warning("get_export_meta: failed to read meta file %s: %s", meta_path, exc)
            return None

    def read_export_csv(self, file_id: str) -> str | None:
        """Read export CSV content as text."""
        if not re.match(r"^[a-f0-9\-]{36}$", file_id):
            return None
        file_path = self._export_file_path(file_id, ".csv")
        return self._result_file_storage.read_text(file_path)

    def cleanup(self, request_id: str) -> None:
        """
        清理请求目录

        删除指定请求的所有 CSV 文件。

        Args:
            request_id: 请求 ID
        """
        # 替换 Windows 非法字符（与 get_path 保持一致）
        safe_request_id = self._sanitize_path_segment(request_id)
        dir_path = self._effective_base_dir() / safe_request_id
        if dir_path.exists():
            shutil.rmtree(dir_path, ignore_errors=True)
