"""Tests for ResultConverter."""
from pathlib import Path

from datacloud_data.sql_executor.result_converter import ResultConverter


def test_to_csv_empty_with_columns_writes_header(tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    ResultConverter.to_csv([], out, columns=["a", "b"])
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 1
    assert lines[0] == "a,b"


def test_to_csv_empty_without_columns_writes_empty(tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    ResultConverter.to_csv([], out)
    assert out.read_text() == ""
