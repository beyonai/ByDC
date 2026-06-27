"""ExecutionMixin — action execution, tool generation, virtual actions."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.backends._contracts import _HasExecutionBackend

logger = logging.getLogger(__name__)


class ExecutionMixin:
    """Mixin for execution-backend-routed operations: actions, tools, virtual actions."""

    async def execute_action(
        self: _HasExecutionBackend,
        base_id: str,
        loader: Any,
        object_code: str,
        action_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an Action via the execution backend.

        Raises:
            PermissionError: If execution is ``"none"`` for this base.
        """
        backend = self._execution_for(base_id)
        if backend is None:
            raise PermissionError(f"Execution not available for base '{base_id}'")
        return await backend.execute_action(loader, object_code, action_code, arguments)

    def generate_action_tools(
        self: _HasExecutionBackend,
        base_id: str,
        loader: Any,
        object_code: str,
    ) -> list[dict[str, Any]]:
        """Generate LangChain Tool descriptors for a single ontology object.

        Raises:
            PermissionError: If execution is ``"none"`` for this base.
        """
        backend = self._execution_for(base_id)
        if backend is None:
            raise PermissionError(f"Execution not available for base '{base_id}'")
        return backend.generate_action_tools(loader, object_code)

    def generate_dynamic_query_tools(
        self: _HasExecutionBackend,
        base_id: str,
        loader: Any,
        object_code: str,
    ) -> list[dict[str, Any]]:
        """Generate dynamic query tool descriptors for a single ontology object.

        Raises:
            PermissionError: If execution is ``"none"`` for this base.
        """
        backend = self._execution_for(base_id)
        if backend is None:
            raise PermissionError(f"Execution not available for base '{base_id}'")
        return backend.generate_dynamic_query_tools(loader, object_code)

    def inject_virtual_actions(
        self: _HasExecutionBackend, base_id: str, loader: Any
    ) -> None:
        """Inject virtual Actions into a loader via execution backend.

        Raises:
            PermissionError: If execution is ``"none"`` for this base.
        """
        backend = self._execution_for(base_id)
        if backend is None:
            raise PermissionError(f"Execution not available for base '{base_id}'")
        backend.inject_virtual_actions(loader)

    def build_filters_schema(
        self: _HasExecutionBackend, base_id: str, fields: list[Any]
    ) -> dict[str, Any]:
        """Build a JSON Schema object for virtual-action filter fields.

        Raises:
            PermissionError: If execution is ``"none"`` for this base.
        """
        backend = self._execution_for(base_id)
        if backend is None:
            raise PermissionError(f"Execution not available for base '{base_id}'")
        return backend.build_filters_schema(fields)
