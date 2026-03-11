"""CSV 临时存储管理。"""

from __future__ import annotations
import shutil
from pathlib import Path


class CsvStorageManager:
    def __init__(self, base_dir: str = "/tmp/datacloud_csv") -> None:
        self._base = Path(base_dir)

    def get_path(self, request_id: str, output_ref: str) -> Path:
        dir_path = self._base / request_id
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / f"{output_ref}.csv"

    def cleanup(self, request_id: str) -> None:
        dir_path = self._base / request_id
        if dir_path.exists():
            shutil.rmtree(dir_path, ignore_errors=True)
