"""CSV 临时存储管理。"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from datacloud_data_sdk.sql_executor.result_converter import ResultConverter


class CsvStorageManager:
    def __init__(self, base_dir: str = "/tmp/datacloud_csv") -> None:
        self._base = Path(base_dir)

    def get_path(self, request_id: str, output_ref: str) -> Path:
        dir_path = self._base / request_id
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / f"{output_ref}.csv"

    def save_export(
        self,
        records: list[dict[str, Any]],
        columns: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> tuple[str, Path]:
        """保存 records 到导出目录，返回 (file_id, path)。file_id 用于下载路由。"""
        exports_dir = self._base / "exports"
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
        """根据 file_id 获取导出文件路径，校验防止路径穿越。"""
        if not re.match(r"^[a-f0-9\-]{36}$", file_id):
            return None
        path = (self._base / "exports" / f"{file_id}.csv").resolve()
        base_resolved = self._base.resolve()
        if not path.exists() or not path.is_file():
            return None
        try:
            path.relative_to(base_resolved)
        except ValueError:
            return None
        return path

    def get_export_meta(self, file_id: str) -> dict[str, Any] | None:
        """根据 file_id 获取导出的元数据。"""
        if not re.match(r"^[a-f0-9\-]{36}$", file_id):
            return None
        meta_path = self._base / "exports" / f"{file_id}_meta.json"
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def cleanup(self, request_id: str) -> None:
        dir_path = self._base / request_id
        if dir_path.exists():
            shutil.rmtree(dir_path, ignore_errors=True)
