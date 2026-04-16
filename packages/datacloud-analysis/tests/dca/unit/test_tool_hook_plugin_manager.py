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


async def test_builtin_semantic_param_enhancer_patches_tool_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATACLOUD_TOOL_HOOK_PLUGIN_DIRS", raising=False)
    get_tool_hook_plugin_manager.cache_clear()
    manager = get_tool_hook_plugin_manager()
    context: HookContext = {
        "tool_name": "dws_enterprise_wide_query",
        "tool_params": {"limit": 100},
        "term_context": [
            {"semantic_type": "view", "normalized_term": "企业综合分析表"},
            {"semantic_type": "object", "normalized_term": "企业"},
            {"semantic_type": "action", "normalized_term": "查询"},
            {"semantic_type": "relation", "normalized_term": "企业-产业"},
        ],
        "knowledge_snippets": [],
    }
    updated_ctx, decision = await manager.run_before(context)

    assert decision is None
    params = updated_ctx["tool_params"]
    assert params["view_name"] == "企业综合分析表"
    assert params["object_name"] == "企业"
    assert params["action_name"] == "查询"
    assert params["relation_hint"] == "企业-产业"
    assert params["relation_strategy"] == "resolve_subject_object_first"
    assert updated_ctx["knowledge_snippets"]
    get_tool_hook_plugin_manager.cache_clear()


async def test_tool_hook_manager_strict_mode_turns_callback_exception_into_fail_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_dir = tmp_path / "tool_plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "raise_before.py"
    plugin_file.write_text(
        "\n".join(
            [
                "PRIORITY = 1",
                "def before_call_back(ctx):",
                "    raise RuntimeError('boom from plugin')",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DATACLOUD_TOOL_HOOK_PLUGIN_DIRS", str(plugin_dir))
    monkeypatch.setenv("DATACLOUD_TOOL_PLUGIN_STRICT", "true")
    get_tool_hook_plugin_manager.cache_clear()
    manager = get_tool_hook_plugin_manager()
    context: HookContext = {"tool_name": "any_tool", "tool_params": {}}
    _updated_ctx, decision = await manager.run_before(context)

    assert decision is not None
    assert decision["action"] == "fail"
    assert decision["result"]["tool_error"]["error_type"] == "RuntimeError"
    assert "boom from plugin" in decision["result"]["tool_error"]["message"]
    assert decision["audit"]["plugin_id"]


async def test_builtin_semantic_param_enhancer_does_not_override_existing_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATACLOUD_TOOL_HOOK_PLUGIN_DIRS", raising=False)
    get_tool_hook_plugin_manager.cache_clear()
    manager = get_tool_hook_plugin_manager()
    context: HookContext = {
        "tool_name": "dws_enterprise_wide_query",
        "tool_params": {
            "view_name": "已有视图",
            "relation_strategy": "custom_strategy",
        },
        "term_context": [
            {"semantic_type": "view", "normalized_term": "企业综合分析表"},
            {"semantic_type": "relation", "normalized_term": "企业-产业"},
        ],
        "knowledge_snippets": [],
    }
    updated_ctx, _decision = await manager.run_before(context)

    params = updated_ctx["tool_params"]
    assert params["view_name"] == "已有视图"
    assert params["relation_strategy"] == "custom_strategy"
    get_tool_hook_plugin_manager.cache_clear()
