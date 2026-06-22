"""OntologyBackend Protocol — ontology parsing, loading, DDL management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from datacloud_platform.models.shared import ObjectSummary, ParsedOwlContent


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

    # -- Scene management --

    def list_scenes(self, base_id: str) -> list[dict[str, Any]]:
        """List all scene directories under a base."""
        ...

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict[str, Any]]:
        """Query scenes with optional keyword filter."""
        ...

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        """Count scenes matching optional keyword filter."""
        ...

    def get_scene_details(
        self,
        base_id: str,
        scene_id: str,
        *,
        view_code: str | None = None,
        object_code: str | None = None,
    ) -> dict[str, Any]:
        """Get full scene details with optional filtering by view_code or object_code."""
        ...

    def query_ontologies_by_scene(
        self,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """Query ontologies (objects) in a scene with pagination and keyword filter."""
        ...

    # -- View CRUD --

    def get_views(self, base_id: str, scene_id: str) -> list[dict[str, Any]]:
        """Get all views under a scene."""
        ...

    def get_view_detail(
        self, base_id: str, scene_id: str, view_code: str
    ) -> dict[str, Any] | None:
        """Get single view detail by code."""
        ...

    def create_view(self, base_id: str, scene_id: str, obj: Any) -> Any:
        """Create a view. REMOTE backends raise PermissionError."""
        ...

    def update_view(
        self, base_id: str, scene_id: str, object_code: str, obj: Any
    ) -> Any:
        """Update a view. REMOTE backends raise PermissionError."""
        ...

    def delete_view(self, base_id: str, scene_id: str, object_code: str) -> None:
        """Delete a view. REMOTE backends raise PermissionError."""
        ...

    # -- Relation CRUD --

    def get_relations(self, base_id: str, scene_id: str) -> list[dict[str, Any]]:
        """Get all relations under a scene."""
        ...

    def get_relation_detail(
        self, base_id: str, scene_id: str, rel_code: str
    ) -> dict[str, Any] | None:
        """Get single relation detail by code."""
        ...

    def create_relation(self, base_id: str, scene_id: str, obj: Any) -> Any:
        """Create a relation. REMOTE backends raise PermissionError."""
        ...

    def update_relation(
        self, base_id: str, scene_id: str, object_code: str, obj: Any
    ) -> Any:
        """Update a relation. REMOTE backends raise PermissionError."""
        ...

    def delete_relation(self, base_id: str, scene_id: str, object_code: str) -> None:
        """Delete a relation. REMOTE backends raise PermissionError."""
        ...

    # -- Datasource CRUD --

    def get_datasources(self, base_id: str, scene_id: str) -> list[dict[str, Any]]:
        """Get all datasources under a scene."""
        ...

    def get_datasource_detail(
        self, base_id: str, scene_id: str, db_id: str
    ) -> dict[str, Any] | None:
        """Get single datasource detail by db_id."""
        ...

    def create_datasource(self, base_id: str, scene_id: str, obj: Any) -> Any:
        """Create a datasource. REMOTE backends raise PermissionError."""
        ...

    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None:
        """Delete a datasource. REMOTE backends raise PermissionError."""
        ...

    # -- Action CRUD --

    def get_actions(
        self, base_id: str, scene_id: str, object_code: str
    ) -> list[dict[str, Any]]:
        """Get all actions on an object."""
        ...

    def get_action_detail(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
    ) -> dict[str, Any] | None:
        """Get single action detail by code."""
        ...

    def create_action(
        self, base_id: str, scene_id: str, object_code: str, obj: Any
    ) -> Any:
        """Create an action. REMOTE backends raise PermissionError."""
        ...

    def update_action(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
        obj: Any,
    ) -> Any:
        """Update an action. REMOTE backends raise PermissionError."""
        ...

    def delete_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> None:
        """Delete an action. REMOTE backends raise PermissionError."""
        ...
