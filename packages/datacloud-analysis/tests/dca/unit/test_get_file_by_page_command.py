from __future__ import annotations

import json
from pathlib import Path

from datacloud_service.commands.ext_command_dispatcher import handle_ext_command
from datacloud_service.commands.get_file_by_page_command import handle_get_file_by_page_command


def test_get_file_by_page_command_ignored_when_command_not_match() -> None:
    handled, payload = handle_get_file_by_page_command(
        ext_params={"command": "noop"},
        session_id="s1",
        workspace_dir=None,
    )
    assert handled is False
    assert payload is None


def test_get_file_by_page_command_reads_json_page(tmp_path: Path) -> None:
    session_id = "s1"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    test_file = session_dir / "sample.json"
    test_file.write_text(
        json.dumps([{"id": 1}, {"id": 2}, {"id": 3}], ensure_ascii=False),
        encoding="utf-8",
    )

    handled, payload = handle_get_file_by_page_command(
        ext_params={"command": "getFileByPage", "fileId": "sample.json", "page": 1, "pagesize": 2},
        session_id=session_id,
        workspace_dir=str(tmp_path),
    )

    assert handled is True
    assert payload is not None
    assert payload["code"] == 0
    assert payload["data"]["records"] == [{"id": 1}, {"id": 2}]
    assert payload["data"]["pagination"]["total"] == 3
    assert payload["data"]["file"]["fileId"] == "sample.json"


def test_ext_params_dispatches_get_file_by_page(tmp_path: Path) -> None:
    session_id = "s2"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    test_file = session_dir / "sample.json"
    test_file.write_text(json.dumps([{"id": 10}]), encoding="utf-8")

    handled, payload = handle_ext_command(
        ext_params={"command": "getFileByPage", "fileId": "sample.json", "page": 1, "pagesize": 10},
        session_id=session_id,
        workspace_dir=str(tmp_path),
    )

    assert handled is True
    assert payload is not None
    assert payload["code"] == 0
    assert payload["data"]["records"] == [{"id": 10}]
