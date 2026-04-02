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
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from datacloud_data_sdk.sql_executor.result_converter import ResultConverter


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
    
    def __init__(self, base_dir: str = "/tmp/datacloud_csv") -> None:
        """
        初始化 CSV 存储管理器
        
        Args:
            base_dir: 基础存储目录
        """
        self._base = Path(base_dir)

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
        if workspace_dir:
            return self._shared_workspace_dir(Path(workspace_dir))
        return self._base

    @staticmethod
    def _shared_workspace_dir(workspace_dir: Path) -> Path:
        """Normalize to the nearest shared ``private/public`` workspace root."""
        resolved = workspace_dir.resolve()
        for candidate in (resolved, *resolved.parents):
            if candidate.name in {"private", "public"}:
                return candidate
        return resolved

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
        dir_path = self._effective_base_dir() / request_id
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
        exports_dir = self._effective_base_dir() / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        file_id = str(uuid.uuid4())
        path = exports_dir / f"{file_id}.csv"
        ResultConverter.to_csv(records, path, columns=columns)

        if meta:
            meta_path = exports_dir / f"{file_id}_meta.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, default=str)

        return file_id, path

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
        base_dir = self._effective_base_dir()
        path = (base_dir / "exports" / f"{file_id}.csv").resolve()
        base_resolved = base_dir.resolve()
        if not path.exists() or not path.is_file():
            return None
        try:
            path.relative_to(base_resolved)
        except ValueError:
            return None
        return path

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
        meta_path = self._effective_base_dir() / "exports" / f"{file_id}_meta.json"
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def cleanup(self, request_id: str) -> None:
        """
        清理请求目录
        
        删除指定请求的所有 CSV 文件。
        
        Args:
            request_id: 请求 ID
        """
        dir_path = self._effective_base_dir() / request_id
        if dir_path.exists():
            shutil.rmtree(dir_path, ignore_errors=True)
