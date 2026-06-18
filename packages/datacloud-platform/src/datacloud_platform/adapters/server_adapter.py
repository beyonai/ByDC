"""LocalExecutionBackend — delegates to datacloud-server tool implementations."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LocalExecutionBackend:
    """ExecutionBackend for local datacloud-server deployments.

    All SDK imports are lazy (method-body imports) so the package does
    not hard-depend on datacloud-server or datacloud-data SDKs.
    """

    def execute_action(self, action: Any, context: Any, **params: Any) -> Any:
        """Execute an Action via :class:`ActionExecutor`.

        Args:
            action: Action descriptor (platform model).
            context: Execution context (loader, etc.).
            **params: Additional execution parameters.

        Returns:
            Execution result dict.
        """
        from datacloud_server.tools.action_executor import ActionExecutor

        executor = ActionExecutor()
        return executor.execute(action, context=context, **params)

    def generate_action_tools(
        self,
        loader: Any,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Generate LangChain tool descriptors via :class:`ActionToolGenerator`.

        Args:
            loader: Ontology queryable (loader object).
            mounted_objects: Object codes to generate tools for.

        Returns:
            List of tool descriptor dicts.
        """
        from datacloud_server.tools.action_tool_generator import ActionToolGenerator

        generator = ActionToolGenerator()
        return generator.generate(loader, mounted_objects)  # type: ignore[no-any-return]

    def generate_dynamic_query_tools(
        self,
        loader: Any,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Generate dynamic query tool descriptors via :class:`DynamicQueryToolGenerator`.

        Args:
            loader: Ontology queryable (loader object).
            mounted_objects: Object codes to generate tools for.

        Returns:
            List of tool descriptor dicts.
        """
        from datacloud_server.tools.dynamic_query_tool_generator import (
            DynamicQueryToolGenerator,
        )

        generator = DynamicQueryToolGenerator()
        return generator.generate(loader, mounted_objects)  # type: ignore[no-any-return]

    def generate_virtual_actions(
        self,
        loader: Any,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Generate virtual action descriptors via :class:`VirtualActionGenerator`.

        Args:
            loader: Ontology queryable (loader object).
            mounted_objects: Object codes to generate tools for.

        Returns:
            List of virtual action dicts.
        """
        from datacloud_server.tools.virtual_action_injector import (
            inject_virtual_actions as generate,
        )

        generate(loader)
        return []

    def generate_plan(
        self,
        query: str,
        loader: Any,
        context: Any,
    ) -> Any:
        """Generate a LangGraph execution plan via :class:`LangGraphPlanGenerator`.

        Args:
            query: Natural language query.
            loader: Ontology queryable (loader object).
            context: Additional context.

        Returns:
            Plan dict or QueryExecutionPlan.
        """
        from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator

        generator = LangGraphPlanGenerator()
        return generator.generate(query, loader, context)
