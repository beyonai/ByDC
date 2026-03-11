"""SqliteAggregator: 用 SQLite 内存库做跨步骤 JOIN。"""

from __future__ import annotations
import csv
import sqlite3
from pathlib import Path
from typing import Any
from datacloud_data_sdk.aggregator.base import BaseAggregator
from datacloud_data_sdk.executor.step_results import StepResults
from datacloud_data_sdk.plan.models import PlanAggregation


class SqliteAggregator(BaseAggregator):
    async def aggregate(
        self,
        agg: PlanAggregation,
        step_results: StepResults,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        csv_table_names = kwargs.get("csv_table_names", agg.csv_table_names or {})
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            for table_name, csv_path in step_results.csv_entries_for_aggregate(csv_table_names):
                self._load_csv_to_sqlite(conn, table_name, csv_path)
            cursor = conn.execute(agg.sqlite_sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def _load_csv_to_sqlite(self, conn: sqlite3.Connection, table_name: str, csv_path: str) -> None:
        if not Path(csv_path).exists():
            return
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return
            cols = reader.fieldnames
            col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
            conn.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_defs})')
            placeholders = ", ".join("?" for _ in cols)
            for row in reader:
                values = [row.get(c, "") for c in cols]
                conn.execute(f'INSERT INTO "{table_name}" VALUES ({placeholders})', values)
