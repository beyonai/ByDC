from __future__ import annotations

from pathlib import Path

from datacloud_analysis.tool_hook_plugins.manager import get_tool_hook_plugin_manager


async def test_tool_hook_manager_before_patch_updates_params(
    tmp_path: Path, monkeypatch
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
    context = {
        "tool_name": "dws_enterprise_wide_query",
        "tool_params": {"query": "企业综合分析表"},
    }
    updated_ctx, decision = await manager.run_before(context)

    assert decision is None
    assert updated_ctx["tool_params"]["query"] == "企业综合分析表"
    assert updated_ctx["tool_params"]["limit"] == 100
    get_tool_hook_plugin_manager.cache_clear()


async def test_tool_hook_manager_short_circuit_stops_before_chain(
    tmp_path: Path, monkeypatch
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
    context = {"tool_name": "any_tool", "tool_params": {}}
    _updated_ctx, decision = await manager.run_before(context)

    assert decision is not None
    assert decision["action"] == "short_circuit"
    assert decision["result"]["tool_output"] == {"code": 0}
    get_tool_hook_plugin_manager.cache_clear()
