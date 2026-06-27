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
    _views: dict[str, dict[str, Any]] | None


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
        self, loader: OntologyQueryable, base_id: str
    ) -> list[ObjectSummary]:
        """Get all object summaries under a base."""
        ...

    def get_object_detail(
        self, loader: OntologyQueryable, object_code: str
    ) -> dict[str, Any] | None:
        """Get single object detail (full ObjectType with properties and actions)."""
        ...

    # -- Object CRUD --

    def create_object(self, base_id: str, obj: Any) -> Any:
        """Create an ontology object. REMOTE backends raise PermissionError."""
        ...

    def update_object(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Update an ontology object. REMOTE backends raise PermissionError."""
        ...

    def delete_object(self, base_id: str, object_code: str) -> None:
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
        loader: Any,
        base_id: str,
        scene_id: str,
        *,
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get full scene details with optional filtering by view_code or object_code."""
        ...

    # -- Atomic ontology methods (refactored from get_scene_details) --

    def get_scene_members(
        self, base_id: str, scene_id: str
    ) -> tuple[list[str], list[str]]:
        """Return (object_codes, view_codes) for a scene — pure metadata query."""
        ...

    def extract_objects_detail(
        self, base_id: str, loader: Any, object_codes: list[str]
    ) -> list[dict[str, Any]]:
        """Extract ObjectType JSON for each code from loader._classes."""
        ...

    def extract_views_detail(
        self, base_id: str, loader: Any, view_codes: list[str]
    ) -> list[dict[str, Any]]:
        """Extract View JSON for each code from loader._views."""
        ...

    def extract_relations(
        self, base_id: str, loader: Any, object_codes_set: set[str]
    ) -> list[dict[str, Any]]:
        """Extract bidirectional Relation JSON where both ends are in object_codes_set."""
        ...

    def get_term_scope_info(self, base_id: str, object_code: str) -> dict[str, Any]:
        """Return {library_id, scene_id} identifying which scene contains object_code."""
        ...

    def query_ontologies_by_scene(
        self,
        loader: Any,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """Query ontologies (objects) in a scene with pagination and keyword filter."""
        ...

    # -- Scene CRUD --

    def create_scene(self, base_id: str, scene: Any) -> Any:
        """Create a scene (grouping container)."""
        ...

    def update_scene(self, base_id: str, scene_id: str, updates: Any) -> Any:
        """Update scene metadata."""
        ...

    def delete_scene(self, base_id: str, scene_id: str) -> None:
        """Delete a scene — does NOT delete member resources."""
        ...

    # -- Scene member management --

    def add_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Add objects/views to a scene (idempotent)."""
        ...

    def remove_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Remove objects/views from a scene — does NOT delete resources."""
        ...

    # -- View CRUD --

    def get_views(self, loader: Any, base_id: str) -> list[dict[str, Any]]:
        """Get all views under a base from the loaded ontology."""
        ...

    def get_view_detail(
        self, loader: Any, base_id: str, view_code: str
    ) -> dict[str, Any] | None:
        """Get single view detail by code from the loaded ontology."""
        ...

    def create_view(self, base_id: str, obj: Any) -> Any:
        """Create a view. REMOTE backends raise PermissionError."""
        ...

    def update_view(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Update a view. REMOTE backends raise PermissionError."""
        ...

    def delete_view(self, base_id: str, object_code: str) -> None:
        """Delete a view. REMOTE backends raise PermissionError."""
        ...

    # -- Relation CRUD --

    def get_relations(self, loader: Any, base_id: str) -> list[dict[str, Any]]:
        """Get all relations under a base from the loaded ontology."""
        ...

    def get_relation_detail(
        self, loader: Any, base_id: str, rel_code: str
    ) -> dict[str, Any] | None:
        """Get single relation detail by code from the loaded ontology."""
        ...

    def create_relation(self, base_id: str, obj: Any) -> Any:
        """Create a relation. REMOTE backends raise PermissionError."""
        ...

    def update_relation(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Update a relation. REMOTE backends raise PermissionError."""
        ...

    def delete_relation(self, base_id: str, object_code: str) -> None:
        """Delete a relation. REMOTE backends raise PermissionError."""
        ...

    # -- Datasource CRUD --

    def get_datasources(self, loader: Any, base_id: str) -> list[dict[str, Any]]:
        """Get all datasources under a base from the loaded ontology."""
        ...

    def get_datasource_detail(
        self, loader: Any, base_id: str, db_id: str
    ) -> dict[str, Any] | None:
        """Get single datasource detail by db_id from the loaded ontology."""
        ...

    def create_datasource(self, base_id: str, obj: Any) -> Any:
        """Create a datasource. REMOTE backends raise PermissionError."""
        ...

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Delete a datasource. REMOTE backends raise PermissionError."""
        ...

    # -- Action CRUD --

    def get_actions(
        self, loader: Any, base_id: str, object_code: str
    ) -> list[dict[str, Any]]:
        """Get all actions on an object from the loaded ontology."""
        ...

    def get_action_detail(
        self,
        loader: Any,
        base_id: str,
        object_code: str,
        action_code: str,
    ) -> dict[str, Any] | None:
        """Get single action detail by code from the loaded ontology."""
        ...

    def create_action(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Create an action. REMOTE backends raise PermissionError."""
        ...

    def update_action(
        self,
        base_id: str,
        object_code: str,
        action_code: str,
        obj: Any,
    ) -> Any:
        """Update an action. REMOTE backends raise PermissionError."""
        ...

    def delete_action(self, base_id: str, object_code: str, action_code: str) -> None:
        """Delete an action. REMOTE backends raise PermissionError."""
        ...
