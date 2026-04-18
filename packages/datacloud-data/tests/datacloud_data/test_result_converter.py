"""Tests for ResultConverter."""

from pathlib import Path

from datacloud_data_sdk.sql_executor.result_converter import ResultConverter


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


def test_to_csv_text_and_from_csv_text_roundtrip() -> None:
    content = ResultConverter.to_csv_text(
        [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}],
    )
    assert "id,name" in content
    records = ResultConverter.from_csv_text(content)
    assert records == [
        {"id": "1", "name": "alice"},
        {"id": "2", "name": "bob"},
    ]
