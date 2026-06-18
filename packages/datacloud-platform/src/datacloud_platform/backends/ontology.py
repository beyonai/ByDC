"""OntologyBackend Protocol — ontology parsing, loading, DDL management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from datacloud_platform.models import ObjectSummary, ParsedOwlContent


class OntologyQueryable(Protocol):
    """Ontology query protocol — replaces datacloud_data_sdk.OntologyLoader.

    Any backend-implemented ontology query object need only have
    _classes and _relations attributes.
    ExecutionBackend / KnowledgeBackend depend on this protocol, not concrete classes.
    """

    _classes: dict[str, Any]
    _relations: list[Any]
    _views: dict[str, Any] | None


class OntologyBackend(Protocol):
    """Ontology parsing, loading, DDL management."""

    def parse_owl(self, directory: Path) -> ParsedOwlContent:
        """Parse OWL directory, return structured content."""
        ...

    def load_ontology(self, base_path: Path) -> OntologyQueryable:
        """Load parsed ontology directory into queryable runtime object.

        Returns OntologyQueryable protocol, not concrete OntologyLoader class.
        """
        ...

    def load_terms(
        self, loader: OntologyQueryable, *, library_id: str = "PERSONAL_LIB"
    ) -> Any:
        """Load term index from knowledge DB."""
        ...

    def create_table(self, object_code: str, fields: list[dict[str, Any]]) -> None:
        """Create physical table for DYNAMIC_TABLE."""
        ...

    def drop_table(self, object_code: str) -> None:
        """Drop physical table."""
        ...

    def get_objects(
        self, loader: OntologyQueryable, base_id: str, scene_id: str
    ) -> list[ObjectSummary]:
        """Get all object summaries under a scene."""
        ...

    def get_object_detail(
        self, loader: OntologyQueryable, object_code: str
    ) -> ObjectSummary | None:
        """Get single object detail."""
        ...

    # -- Object CRUD --

    def create_object(self, base_id: str, scene_id: str, obj: Any) -> Any:
        """Create an ontology object. REMOTE backends raise PermissionError."""
        ...

    def update_object(
        self, base_id: str, scene_id: str, object_code: str, obj: Any
    ) -> Any:
        """Update an ontology object. REMOTE backends raise PermissionError."""
        ...

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        """Delete an ontology object. REMOTE backends raise PermissionError."""
        ...
