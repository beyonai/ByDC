"""StepResult / StepResults: 步骤执行结果确定数据结构。"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class StepResult:
    """单步执行结果。"""
    step_id: str
    exec_key: str
    output_ref: str = ""
    csv_path: str = ""
    table_name: str = ""


class StepResults:
    """步骤结果集合，执行中可 add。"""
    def __init__(self, entries: list[StepResult] | None = None) -> None:
        self._entries = list(entries or [])

    def add(self, entry: StepResult) -> None:
        self._entries.append(entry)

    def get_path(self, ref: str) -> str:
        for e in self._entries:
            if ref in (e.step_id, e.output_ref, e.exec_key):
                return e.csv_path
        return ""

    def csv_entries_for_aggregate(
        self, csv_table_names: dict[str, str] | None = None
    ) -> list[tuple[str, str]]:
        """返回 (table_name, csv_path)，按 path 去重。csv_table_names 可覆盖表名。"""
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        override = csv_table_names or {}
        for e in self._entries:
            if not e.csv_path or e.csv_path in seen:
                continue
            seen.add(e.csv_path)
            tbl = override.get(e.step_id) or e.table_name or e.output_ref or e.step_id
            result.append((tbl, e.csv_path))
        return result

    def to_legacy_dict(self) -> dict[str, str]:
        d: dict[str, str] = {}
        for e in self._entries:
            if e.csv_path:
                d[e.exec_key] = e.csv_path
                d[e.step_id] = e.csv_path
                if e.output_ref:
                    d[e.output_ref] = e.csv_path
        return d
