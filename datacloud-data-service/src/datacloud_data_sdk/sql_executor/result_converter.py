"""ResultConverter: 查询结果 -> CSV 文件。"""
from __future__ import annotations
import csv
from pathlib import Path
from typing import Any


class ResultConverter:
    @staticmethod
    def to_csv(
        records: list[dict[str, Any]],
        path: str | Path,
        columns: list[str] | None = None,
    ) -> int:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not records:
            if columns:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=columns)
                    writer.writeheader()
            else:
                path.write_text("")
            return 0
        fieldnames = list(records[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
        return len(records)
