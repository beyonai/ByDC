"""Unit-level conftest: prevent module-level side effects and add byclaw_data to path.

Several modules call get_platform()._default_base_id() at import time.
We monkey-patch get_platform so it returns a MagicMock whose
_default_base_id() returns "default", avoiding the RuntimeError.

Also adds byclaw_data/src to sys.path so worker.py tests can import byclaw_data.
Also stubs out by_framework (production dep not installed in test venv).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


def _stub_by_framework() -> None:
    """Inject by_framework stub modules into sys.modules before worker.py is imported."""
    if "by_framework" in sys.modules:
        return

    def _mod(name: str, **attrs: object) -> types.ModuleType:
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    # Root package — all top-level names imported by worker.py / byclaw_data_clarification.py
    _mod(
        "by_framework",
        AskUserEvent=MagicMock(),
        EventType=MagicMock(),
        GatewayCommand=MagicMock(),
        GatewayWorker=MagicMock(),
        ResumeCommand=MagicMock(),
        StreamChunkEvent=MagicMock(),
        AgentContext=MagicMock(),
    )

    # Intermediate namespace packages
    _mod("by_framework.common")
    _mod("by_framework.core")
    _mod("by_framework.core.protocol")
    _mod("by_framework.worker")
    _mod("by_framework.worker.sandbox")

    # Leaf modules
    _mod(
        "by_framework.common.constants",
        RedisKeys=MagicMock(),
        TASK_GROUP_FIELD_COMPLETED="completed",
        TASK_GROUP_FIELD_TOTAL="total",
        TASK_GROUP_TTL_SECONDS=3600,
    )
    _mod("by_framework.common.logger", logger=MagicMock())
    _mod(
        "by_framework.common.emitter",
        DefaultSseLayoutBuilder=MagicMock(),
        _build_sse_layout=MagicMock(),
    )
    _mod("by_framework.core.extensions", PluginRegistry=MagicMock())
    _mod("by_framework.core.protocol.agent_state", AgentState=MagicMock())
    _mod("by_framework.core.protocol.commands", AskAgentCommand=MagicMock(), ResumeCommand=MagicMock())
    _mod(
        "by_framework.core.protocol.content_type",
        SseMessageType=MagicMock(),
        SseReasonMessageType=MagicMock(),
    )
    _mod(
        "by_framework.core.protocol.results",
        AgentTaskResult=MagicMock(),
        normalize_process_result=MagicMock(),
    )
    _mod("by_framework.core.protocol.event_type", EventType=MagicMock())
    _mod("by_framework.core.protocol.events", AskUserEvent=MagicMock())
    _mod("by_framework.worker.sandbox.hook_sandbox", active_workspace=MagicMock())
    _mod("by_framework.worker._execution_tracking", RunningExecution=MagicMock())


def _add_byclaw_data_to_path() -> None:
    """Add byclaw-data/src to sys.path so byclaw_data is importable."""
    # conftest.py lives at: D:\data\code\baiying\by-datacloud\packages\datacloud-analysis\tests\dca\unit\
    # parents[6] = D:\data\code\baiying
    # byclaw-all is a sibling of by-datacloud under D:\data\code\baiying
    here = Path(__file__).resolve()
    baiying_root = here.parents[6]  # D:\data\code\baiying
    byclaw_data_src = baiying_root / "byclaw-all" / "byclaw-data" / "src"
    if byclaw_data_src.exists():
        src_str = str(byclaw_data_src)
        if src_str not in sys.path:
            sys.path.insert(0, src_str)


def _patch_get_platform() -> None:
    """Patch datacloud_platform.get_platform to return a safe stub."""
    try:
        import datacloud_platform as _dp
    except Exception:
        return

    _platform_stub = MagicMock()
    _platform_stub._default_base_id.return_value = "default"

    _dp.get_platform = lambda: _platform_stub  # type: ignore[attr-defined]


_stub_by_framework()
_add_byclaw_data_to_path()
_patch_get_platform()
