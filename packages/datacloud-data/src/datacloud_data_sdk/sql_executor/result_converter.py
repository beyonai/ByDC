"""ResultConverter: 查询结果 -> CSV 文件。"""

from __future__ import annotations

import csv
import io
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

    @staticmethod
    def to_csv_text(
        records: list[dict[str, Any]],
        columns: list[str] | None = None,
    ) -> str:
        """Render records to CSV text."""
        buffer = io.StringIO()
        if not records:
            if columns:
                writer = csv.DictWriter(buffer, fieldnames=columns)
                writer.writeheader()
            return buffer.getvalue()

        fieldnames = list(records[0].keys())
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
        return buffer.getvalue()

    @staticmethod
    def from_csv(path: str | Path) -> list[dict[str, Any]]:
        """
        从 CSV 文件读取记录

        Args:
            path: CSV 文件路径

        Returns:
            list[dict[str, Any]]: 记录列表
        """
        import logging

        logger = logging.getLogger(__name__)

        path = Path(path)
        logger.info("ResultConverter.from_csv: reading from %s", path)
        if not path.exists():
            logger.warning("ResultConverter.from_csv: file does not exist: %s", path)
            return []

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = list(reader)
            logger.info("ResultConverter.from_csv: loaded %d records", len(records))
            return records

    @staticmethod
    def from_csv_text(content: str) -> list[dict[str, Any]]:
        """Parse CSV text into records."""
        if not content:
            return []
        reader = csv.DictReader(io.StringIO(content))
        return [dict(row) for row in reader]
