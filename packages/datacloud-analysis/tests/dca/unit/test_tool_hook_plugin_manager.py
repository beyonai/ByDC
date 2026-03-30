from __future__ import annotations

from pathlib import Path

import pytest

from datacloud_analysis.tool_hook_plugins.manager import get_tool_hook_plugin_manager
from datacloud_analysis.tool_hook_plugins.types import HookContext


async def test_tool_hook_manager_before_patch_updates_params(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_dir = tmp_path / "tool_plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "patch_params.py"
    plugin_file.write_text(
        "\n".join(
            [
                "PRIORITY = 1",
                "def before_call_back(ctx):",
                "    return {'action': 'patch', 'patch': {'tool_params': {'limit': 100}}}",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DATACLOUD_TOOL_HOOK_PLUGIN_DIRS", str(plugin_dir))
    get_tool_hook_plugin_manager.cache_clear()
    manager = get_tool_hook_plugin_manager()
    context: HookContext = {
        "tool_name": "dws_enterprise_wide_query",
        "tool_params": {"query": "企业综合分析表"},
    }
    updated_ctx, decision = await manager.run_before(context)

    assert decision is None
    assert updated_ctx["tool_params"]["query"] == "企业综合分析表"
    assert updated_ctx["tool_params"]["limit"] == 100
    get_tool_hook_plugin_manager.cache_clear()


async def test_tool_hook_manager_short_circuit_stops_before_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_dir = tmp_path / "tool_plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "short_circuit.py"
    plugin_file.write_text(
        "\n".join(
            [
                "PRIORITY = 1",
                "def before_call_back(ctx):",
                "    return {'action': 'short_circuit', 'result': {'tool_output': {'code': 0}}}",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DATACLOUD_TOOL_HOOK_PLUGIN_DIRS", str(plugin_dir))
    get_tool_hook_plugin_manager.cache_clear()
    manager = get_tool_hook_plugin_manager()
    context: HookContext = {"tool_name": "any_tool", "tool_params": {}}
    _updated_ctx, decision = await manager.run_before(context)

    assert decision is not None
    assert decision["action"] == "short_circuit"
    assert decision["result"]["tool_output"] == {"code": 0}
    get_tool_hook_plugin_manager.cache_clear()


async def test_tool_hook_manager_legacy_before_patch_schema_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_dir = tmp_path / "tool_plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "legacy_before_patch.py"
    plugin_file.write_text(
        "\n".join(
            [
                "PRIORITY = 1",
                "def before_call_back(ctx):",
                "    return {'tool_params': {'limit': 42}}",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DATACLOUD_TOOL_HOOK_PLUGIN_DIRS", str(plugin_dir))
    get_tool_hook_plugin_manager.cache_clear()
    manager = get_tool_hook_plugin_manager()
    context: HookContext = {"tool_name": "any", "tool_params": {"query": "q"}}
    updated_ctx, decision = await manager.run_before(context)

    assert decision is None
    assert updated_ctx["tool_params"]["query"] == "q"
    assert updated_ctx["tool_params"]["limit"] == 42
    get_tool_hook_plugin_manager.cache_clear()


async def test_tool_hook_manager_legacy_after_tool_output_schema_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_dir = tmp_path / "tool_plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "legacy_after_output.py"
    plugin_file.write_text(
        "\n".join(
            [
                "PRIORITY = 1",
                "def after_call_back(ctx):",
                "    return {'tool_output': {'ok': True, 'rewritten': True}}",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DATACLOUD_TOOL_HOOK_PLUGIN_DIRS", str(plugin_dir))
    get_tool_hook_plugin_manager.cache_clear()
    manager = get_tool_hook_plugin_manager()
    context: HookContext = {"tool_name": "any", "tool_params": {}, "tool_output": {"ok": True}}
    _updated_ctx, decision = await manager.run_after(context)

    assert decision is not None
    assert decision["action"] == "recover"
    assert decision["result"]["tool_output"] == {"ok": True, "rewritten": True}
    get_tool_hook_plugin_manager.cache_clear()
