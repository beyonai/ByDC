"""ExecutionBackend Protocol — Action execution, tool generation, plan generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable


class ExecutionBackend(Protocol):
    """Action execution, tool generation, plan generation."""

    async def execute_action(
        self,
        loader: Any,
        object_code: str,
        action_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single Action (SQL / API / Script).

        Matches server-side ActionExecutor.execute(object_code, action_code, arguments).
        """
        ...

    def generate_action_tools(
        self,
        loader: Any,
        object_code: str,
    ) -> list[dict[str, Any]]:
        """Generate LangChain Tools for a single ontology object.

        Matches server-side ActionToolGenerator.generate_tools(object_code).
        Returns list[dict] not typed model: Tool descriptors are serialized
        LangChain format data.
        """
        ...

    def generate_dynamic_query_tools(
        self,
        loader: Any,
        object_code: str,
    ) -> list[dict[str, Any]]:
        """Generate dynamic query tools for a single ontology object.

        Matches server-side DynamicQueryToolGenerator.generate_ontology_action(object_code).
        """
        ...

    def generate_virtual_actions(
        self,
        loader: OntologyQueryable,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Generate virtual Actions."""
        ...

    def inject_virtual_actions(self, loader: Any) -> None:
        """Inject virtual Actions into a loader in-place (query_*, compute_*, search_*, etc.)."""
        ...

    def generate_plan(
        self,
        query: str,
        loader: OntologyQueryable,
        context: Any,
    ) -> Any:
        """Generate query plan (LangGraph Plan)."""
        ...

    def build_filters_schema(self, fields: list[Any]) -> dict[str, Any]:
        """Build a JSON Schema object for virtual-action filter fields."""
        ...
