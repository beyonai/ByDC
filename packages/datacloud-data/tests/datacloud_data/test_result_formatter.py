from __future__ import annotations

from typing import Any

from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.result_formatter import build_query_response


class _DummyCsvManager:
    def __init__(self) -> None:
        self.saved_records: list[dict[str, Any]] | None = None
        self.saved_columns: list[str] | None = None
        self.saved_meta: dict[str, Any] | None = None

    def save_export(
        self,
        records: list[dict[str, Any]],
        *,
        columns: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        self.saved_records = records
        self.saved_columns = columns
        self.saved_meta = meta
        return "file-1", "/tmp/file-1.csv"


def test_build_query_response_uses_threshold_for_preview_rows() -> None:
    csv_manager = _DummyCsvManager()
    records = [
        {"id": 1, "name": "a"},
        {"id": 2, "name": "b"},
        {"id": 3, "name": "c"},
        {"id": 4, "name": "d"},
    ]

    result = build_query_response(
        {
            "records": records,
            "meta": {"columns": [{"name": "id"}, {"name": "name"}], "viewId": "view_1"},
            "trace": {"request_id": "req_1"},
        },
        csv_manager=csv_manager,
        threshold=2,
    )

    assert [row["id"] for row in result["records"]] == [1, 2]
    assert result["pagination"] == {
        "page": 1,
        "page_size": 2,
        "total": 4,
        "total_pages": 2,
        "has_next": True,
        "has_prev": False,
    }
    assert result["meta"]["preview_rows"] == 2
    assert csv_manager.saved_meta is not None
    assert csv_manager.saved_meta["preview_rows"] == 2


def test_build_query_response_without_overflow_keeps_full_records() -> None:
    csv_manager = _DummyCsvManager()
    records = [{"id": 1}, {"id": 2}]

    result = build_query_response(
        {
            "records": records,
            "meta": {"columns": [{"name": "id"}]},
            "trace": {},
        },
        csv_manager=csv_manager,
        threshold=2,
    )

    assert result["records"] == records
    assert "pagination" not in result
    assert csv_manager.saved_records is None


def test_build_query_response_uses_context_language_for_overflow_notice() -> None:
    csv_manager = _DummyCsvManager()
    records = [{"id": 1}, {"id": 2}, {"id": 3}]

    with InvocationContext(language="en-US"):
        result = build_query_response(
            {
                "records": records,
                "meta": {"columns": [{"name": "id"}]},
                "trace": {},
            },
            csv_manager=csv_manager,
            threshold=1,
        )

    assert "Only the first 1 rows are returned here" in result["overflow_notice"]
