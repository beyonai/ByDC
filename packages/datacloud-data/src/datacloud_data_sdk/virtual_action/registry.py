"""虚拟动作统一索引注册表。

维护 tool_name → (scope_type, scope_code, action_family) 的路由索引。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ActionRoute:
    """工具名称对应的路由信息。"""
    scope_type: str   # "object" | "view"
    scope_code: str   # 对象编码或视图编码
    action_family: str | None = None  # "lookup" | "analyze" | "search"


class VirtualActionRegistry:
    """全局虚拟动作路由索引。由 VirtualActionInjector 在注入时填充。"""

    def __init__(self) -> None:
        self._index: dict[str, ActionRoute] = {}

    def register(self, tool_name: str, route: ActionRoute) -> None:
        self._index[tool_name] = route

    def get(self, tool_name: str) -> ActionRoute | None:
        return self._index.get(tool_name)

    def all_tools(self) -> list[str]:
        return list(self._index.keys())

    def clear(self) -> None:
        self._index.clear()


# 全局单例（由 inject_virtual_actions 在服务启动时填充）
_global_registry = VirtualActionRegistry()


def get_registry() -> VirtualActionRegistry:
    return _global_registry
