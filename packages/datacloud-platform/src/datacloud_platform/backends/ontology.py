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

    def batch_import_ontology(
        self,
        base_path: Path,
        objects: list[dict[str, Any]],
        views: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        dbsources: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Batch import ontology content into the backend.

        Persists objects, views, relations, actions, and dbsources.
        Each backend determines its own storage strategy.
        Returns counts keyed by entity type.

        Raises:
            PermissionError: If the backend is read-only (e.g. REMOTE).
        """
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
        self,
        loader: OntologyQueryable,
        base_id: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[ObjectSummary]:
        """Get all object summaries under a base."""
        ...

    def get_object_detail(
        self, loader: OntologyQueryable, object_code: str
    ) -> dict[str, Any] | None:
        """Get single object detail (full ObjectType with properties and actions)."""
        ...

    def get_object_subtree(
        self, loader: Any, base_id: str, object_code: str
    ) -> dict[str, Any]:
        """Get an object's subtree — detail + related views, relations, actions."""
        ...

    def get_base_details(
        self,
        loader: Any,
        base_id: str,
        *,
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get comprehensive base detail — scenes, objects, views, relations, actions, dbsources."""
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
        type: str | None = None,
        owner_type: str | None = None,
        user_code: str | None = None,
        cross_scene: bool = False,
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

    # -- Scene reverse-lookup queries --

    def get_object_scene_count(self, base_id: str, object_code: str) -> int:
        """Return how many scenes this object belongs to."""
        ...

    def get_view_scene_count(self, base_id: str, view_code: str) -> int:
        """Return how many scenes this view belongs to."""
        ...

    def remove_object_from_all_scenes(self, base_id: str, object_code: str) -> int:
        """Remove object from all scenes. Returns count of scenes removed from."""
        ...

    def remove_view_from_all_scenes(self, base_id: str, view_code: str) -> int:
        """Remove view from all scenes. Returns count of scenes removed from."""
        ...

    def get_scenes_containing_object(self, base_id: str, object_code: str) -> list[str]:
        """Return scene_ids that contain this object."""
        ...

    # -- View CRUD --

    def get_views(
        self,
        loader: Any,
        base_id: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all views under a base from the loaded ontology."""
        ...

    def get_view_detail(
        self, loader: Any, base_id: str, view_code: str
    ) -> dict[str, Any] | None:
        """Get single view detail by code from the loaded ontology."""
        ...

    def get_objects_by_view(
        self,
        loader: Any,
        base_id: str,
        view_code: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get objects referenced by a view, with optional filtering."""
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

    def get_relations(
        self,
        loader: Any,
        base_id: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all relations under a base from the loaded ontology."""
        ...

    def get_relation_detail(
        self, loader: Any, base_id: str, rel_code: str
    ) -> dict[str, Any] | None:
        """Get single relation detail by code from the loaded ontology."""
        ...

    def get_relations_by_object(
        self,
        loader: Any,
        base_id: str,
        object_code: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all relation details involving object_code (source or target), with filtering."""
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

    def get_datasources(
        self, loader: Any, base_id: str, *, keyword: str | None = None
    ) -> list[dict[str, Any]]:
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
        self,
        loader: Any,
        base_id: str,
        object_code: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
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

    # ── Property term bindings (新增) ────────────────────────────

    def get_object_property_term_bindings(
        self,
        loader: Any,
        object_codes: list[str],
        *,
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """查询对象下属性绑定的术语类型（批量）。

        返回只含绑定了 terminology 的属性，未绑定的不出现在结果中。
        """
        ...

    def get_view_property_term_bindings(
        self,
        loader: Any,
        view_codes: list[str],
        *,
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """查询视图下属性绑定的术语类型（批量）。

        视图属性通过 source_object → source_object_property 穿透到底层
        Object 的 Property.terminology。
        """
        ...

    # ── Property name/code resolution (新增) ─────────────────────

    def resolve_property_name(
        self,
        loader: OntologyQueryable,
        name_text: str,
        scope_code: str,
    ) -> tuple[str, str] | None:
        """本体元数据: 单个中文属性名 → (field_code, field_name)。

        遍历 loader._classes[scope_code].fields，
        匹配 field_name / aliases。纯内存操作，零 DB 开销。

        Returns:
            (field_code, field_name) 或 None（未命中）。
        """
        ...

    def resolve_property_names(
        self,
        loader: OntologyQueryable,
        name_texts: list[str],
        scope_code: str,
    ) -> dict[str, tuple[str, str]]:
        """批量版。返回 {name_text: (field_code, field_name)}。

        只返回成功解析的条目，未命中的不出现在返回 dict 中。
        """
        ...

    def get_property_aliases(
        self,
        loader: OntologyQueryable,
        field_code: str,
        scope_code: str,
    ) -> list[str]:
        """反向: field_code → 所有别名列表（含 field_name）。

        遍历 loader._classes[scope_code].fields，
        找到匹配 field_code 的 OntologyField，返回其 field_name + aliases。
        """
        ...

    # ── Scope resolution helpers (used by unified recall) ──────────────────

    def get_view_included_objects(
        self, loader: OntologyQueryable, ontology_code: str
    ) -> list[str]:
        """返回 ontology_code 对应视图所包含的子对象代码列表。"""
        ...

    def get_joinkey_related_objects(
        self, loader: OntologyQueryable, ontology_code: str, field_codes: list[str]
    ) -> list[str]:
        """返回通过 join key 与指定字段关联的对象代码列表。"""
        ...

    # ── 本体搜索 & 图查询（从 KnowledgeBackend 迁入）─────────────

    def search_ontology(
        self,
        base_id: str,
        scene_ids: list[str],
        *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        ontology_type: list[str] | None = None,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        property_code: list[str] | None = None,
        limit: int = 20,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """本体元数据与实例向量检索。"""
        ...

    def search_ontology_batch(
        self,
        base_id: str,
        keyword: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """跨场景批量本体检索。"""
        ...

    def graph_query(
        self,
        base_id: str,
        scene_id: str,
        *,
        object_code: list[str],
        match_by: str = "name",
        values: list[str] | None = None,
        step: int = 1,
    ) -> dict[str, Any]:
        """本体图遍历查询。"""
        ...

    def graph_path(
        self,
        base_id: str,
        scene_id: str,
        *,
        match_by: str = "name",
        start_node: str,
        end_node: str = "",
        direction: str = "forward",
    ) -> dict[str, Any]:
        """本体图最短路径查询。"""
        ...

    def search_instances(
        self,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """本体实例搜索。"""
        ...
