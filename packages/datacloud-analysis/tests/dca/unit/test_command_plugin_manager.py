from __future__ import annotations

import json
from pathlib import Path

from datacloud_analysis.command_plugins import CommandPluginManager


async def test_command_plugin_manager_builtin_get_file_by_page(tmp_path: Path) -> None:
    session_id = "s1"
    session_dir = tmp_path / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    test_file = session_dir / "sample.json"
    test_file.write_text(json.dumps([{"id": 1}, {"id": 2}], ensure_ascii=False), encoding="utf-8")

    manager = CommandPluginManager.from_defaults()
    handled, payload = await manager.handle_ext_command(
        ext_params={"command": "getFileByPage", "fileId": "sample.json", "page": 1, "pagesize": 1},
        session_id=session_id,
        workspace_dir=str(tmp_path),
    )

    assert handled is True
    assert payload is not None
    assert payload["code"] == 0
    assert payload["data"]["records"] == [{"id": 1}]


async def test_command_plugin_manager_loads_extension_from_env(
    tmp_path: Path, monkeypatch
) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "my_command_plugin.py"
    plugin_file.write_text(
        "\n".join(
            [
                "PLUGIN_ID = 'ext.cmd.test'",
                "PRIORITY = 1",
                "def handle_ext_command(*, ext_params, session_id, workspace_dir, gateway_context=None):",
                "    if ext_params.get('command') == 'extOnly':",
                "        return True, {'code': 0, 'message': 'handled-by-extension', 'data': {'session': session_id}}",
                "    return False, None",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DATACLOUD_COMMAND_PLUGIN_DIRS", str(plugin_dir))
    manager = CommandPluginManager.from_defaults()
    handled, payload = await manager.handle_ext_command(
        ext_params={"command": "extOnly"},
        session_id="s-ext",
        workspace_dir=str(tmp_path),
    )

    assert handled is True
    assert payload is not None
    assert payload["message"] == "handled-by-extension"
    assert payload["data"]["session"] == "s-ext"

