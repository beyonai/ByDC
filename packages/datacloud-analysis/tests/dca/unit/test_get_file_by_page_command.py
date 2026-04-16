from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest
from datacloud_analysis.command_plugins import get_file_by_page_command as get_file_module
from datacloud_analysis.command_plugins.ext_command_dispatcher import handle_ext_command
from datacloud_analysis.command_plugins.get_file_by_page_command import (
    handle_get_file_by_page_command,
)


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


def test_get_file_by_page_command_uses_private_workspace_root(tmp_path: Path) -> None:
    private_root = tmp_path / "10011741" / "private"
    dynamic_workspace = private_root / "10011835"
    dynamic_workspace.mkdir(parents=True, exist_ok=True)

    exports_dir = private_root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    export_file = exports_dir / "sample.csv"
    export_file.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")

    handled, payload = handle_get_file_by_page_command(
        ext_params={"command": "getFileByPage", "fileId": "sample.csv", "page": 1, "pagesize": 1},
        session_id="s3",
        workspace_dir=str(dynamic_workspace),
    )

    assert handled is True
    assert payload is not None
    assert payload["code"] == 0
    assert payload["data"]["records"] == [{"id": "1", "name": "Alice"}]
    assert payload["data"]["file"]["filePath"] == str(export_file)


def test_get_file_by_page_error_payload_uses_standard_envelope(tmp_path: Path) -> None:
    handled, payload = handle_get_file_by_page_command(
        ext_params={
            "command": "getFileByPage",
            "fileId": "not_found.csv",
            "page": 1,
            "pagesize": 10,
        },
        session_id="s4",
        workspace_dir=str(tmp_path),
    )

    assert handled is True
    assert payload is not None
    assert payload["code"] == 1
    assert isinstance(payload["message"], str)
    assert isinstance(payload["data"], dict)
    assert payload["data"]["records"] == []
    assert payload["data"]["pagination"]["total"] == 0


def test_shared_workspace_dir_coerces_purepath_to_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        get_file_module,
        "resolve_shared_workspace_dir",
        lambda _workspace_dir: PurePosixPath("/tmp/workspace"),
    )

    resolved = get_file_module._shared_workspace_dir(tmp_path)
    assert isinstance(resolved, Path)
