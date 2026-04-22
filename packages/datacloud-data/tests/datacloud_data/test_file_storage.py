from __future__ import annotations

from pathlib import Path

from datacloud_data_sdk.context import InvocationContext
from datacloud_data_sdk.csv_storage.manager import CsvStorageManager
from datacloud_data_sdk.file_storage.local import LocalResultFileStorage


def test_local_result_file_storage_scopes_by_user_and_session(tmp_path: Path) -> None:
    storage = LocalResultFileStorage(tmp_path)

    with InvocationContext(user_id="u1", session_id="s1"):
        stored_path = storage.write_text("/datacloud/exports/demo.csv", "id\n1\n")
        content = storage.read_text("/datacloud/exports/demo.csv")
        actual_path = storage.resolve_path("/datacloud/exports/demo.csv")

    assert stored_path == "/datacloud/exports/demo.csv"
    assert content == "id\n1\n"
    assert actual_path.exists()
    assert actual_path.relative_to(tmp_path).parts[:3] == ("u1", "sessions", "s1")


def test_csv_storage_manager_save_export_uses_result_file_storage(tmp_path: Path) -> None:
    storage = LocalResultFileStorage(tmp_path / "result")
    manager = CsvStorageManager(str(tmp_path / "temp"), result_file_storage=storage)

    with InvocationContext(user_id="u2", session_id="s2"):
        file_id, file_path = manager.save_export(
            [{"id": 1, "name": "alice"}],
            columns=["id", "name"],
            meta={"viewId": "demo_view"},
        )
        csv_content = manager.read_export_csv(file_id)
        meta = manager.get_export_meta(file_id)

    assert str(file_path) == f"/datacloud/exports/{file_id}.csv"
    assert csv_content is not None
    assert csv_content.splitlines() == ["id,name", "1,alice"]
    assert meta is not None
    assert meta["viewId"] == "demo_view"
    assert meta["file_url"] == str(file_path)
    assert meta["storage_type"] == "local"
