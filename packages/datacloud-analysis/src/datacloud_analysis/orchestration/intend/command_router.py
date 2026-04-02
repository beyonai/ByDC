from __future__ import annotations
import logging
from typing import Any
from datacloud_analysis.command_plugins.manager import CommandPluginManager

logger = logging.getLogger(__name__)
_manager: CommandPluginManager | None = None

def _get_manager() -> CommandPluginManager:
    global _manager
    if _manager is None:
        _manager = CommandPluginManager.from_defaults()
    return _manager

class CommandRouter:
    async def try_dispatch(
        self,
        *,
        user_query: str,
        state: Any,
        config: Any,
        gateway_context: Any = None,
    ) -> dict[str, Any]:
        """Try to dispatch as a command. Returns {"handled": bool, "payload": Any}."""
        import json
        # ext_params 从 state 或 config 中取
        configurable = (config.get("configurable") or {}) if config else {}
        ext_params: dict[str, Any] | None = None
        # 尝试从 state messages 中识别 ext_params
        messages = state.get("messages") or []
        if messages:
            last = messages[-1]
            content = last.content if hasattr(last, "content") else str(last)
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "command" in parsed:
                        ext_params = parsed
                except (json.JSONDecodeError, ValueError):
                    pass

        if ext_params is None:
            return {"handled": False, "payload": None}

        manager = _get_manager()
        session_id = str(configurable.get("thread_id") or state.get("agent_id") or "")
        workspace_dir = state.get("workspace_dir")

        try:
            handled, payload = await manager.handle_ext_command(
                ext_params=ext_params,
                session_id=session_id,
                workspace_dir=workspace_dir,
                gateway_context=gateway_context,
            )
            return {"handled": handled, "payload": payload}
        except Exception as exc:
            logger.warning("CommandRouter.try_dispatch failed: %s", exc)
            return {"handled": False, "payload": None}
