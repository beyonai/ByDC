"""ExecutionBackend Protocol — Action execution, tool generation, plan generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable


class ExecutionBackend(Protocol):
    """Action execution, tool generation, plan generation."""

    def execute_action(self, action: Any, context: Any, **params: Any) -> Any:
        """Execute a single Action (SQL / API / Script).

        'action' and 'context' are not yet abstracted (defined in datacloud-data SDK,
        consumer side already imports directly). Can be narrowed to Protocol later.
        """
        ...

    def generate_action_tools(
        self,
        loader: OntologyQueryable,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Generate LangChain Tools for ontology objects.

        Returns list[dict] not typed model: Tool descriptors are serialized
        LangChain format data.
        """
        ...

    def generate_dynamic_query_tools(
        self,
        loader: OntologyQueryable,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Generate dynamic query tools."""
        ...

    def generate_virtual_actions(
        self,
        loader: OntologyQueryable,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Generate virtual Actions."""
        ...

    def generate_plan(
        self,
        query: str,
        loader: OntologyQueryable,
        context: Any,
    ) -> Any:
        """Generate query plan (LangGraph Plan)."""
        ...
