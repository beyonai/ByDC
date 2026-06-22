"""LocalExecutionBackend — adapts platform/execution/ tools into ExecutionBackend."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.execution.action_executor import ActionExecutor
from datacloud_platform.execution.action_tool_generator import ActionToolGenerator
from datacloud_platform.execution.dynamic_query_tool_generator import (
    DynamicQueryToolGenerator,
)
from datacloud_platform.execution.virtual_action_injector import inject_virtual_actions

logger = logging.getLogger(__name__)


class LocalExecutionBackend:
    """ExecutionBackend backed by local platform execution tools."""

    async def execute_action(
        self, loader: Any, object_code: str, action_code: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        executor = ActionExecutor(loader)
        return await executor.execute(object_code, action_code, arguments)

    def generate_action_tools(
        self, loader: Any, object_code: str
    ) -> list[dict[str, Any]]:
        generator = ActionToolGenerator(loader)
        return generator.generate_tools(object_code)

    def generate_dynamic_query_tools(
        self, loader: Any, object_code: str
    ) -> list[dict[str, Any]]:
        generator = DynamicQueryToolGenerator(loader)
        action = generator.generate_ontology_action(object_code)
        return [action] if action else []

    def generate_virtual_actions(
        self, loader: Any, _mounted_objects: list[str]
    ) -> list[dict[str, Any]]:
        inject_virtual_actions(loader)
        return []

    def inject_virtual_actions(self, loader: Any) -> None:
        inject_virtual_actions(loader)

    def generate_plan(self, query: str, loader: Any, context: Any) -> Any:
        from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator

        generator = LangGraphPlanGenerator()
        return generator.generate(query, loader, context)  # type: ignore[arg-type]

    def build_filters_schema(self, fields: list[Any]) -> dict[str, Any]:
        from datacloud_data_sdk.virtual_action.generator import _build_filters_schema

        return _build_filters_schema(fields)
