"""OntologyBackend Protocol — ontology parsing, loading, DDL management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from datacloud_platform.models.shared import (
        ObjectInstanceHit,
        ObjectInstanceSearchResult,
        ObjectSummary,
        ParsedOwlContent,
    )


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
        *,
        base_id: str = "",
    ) -> dict[str, int]:
        """Batch import ontology content into the backend.

        Persists objects, views, relations, actions, and dbsources.
        Each backend determines its own storage strategy.
        Returns counts keyed by entity type.

        Raises:
            PermissionError: If the backend is read-only (e.g. REMOTE).
        """
        ...

    def load_ontology(self, base_path: Path, *, base_id: str = "") -> OntologyQueryable:
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
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ObjectSummary], int]:
        """Get paginated object summaries under a base."""
        ...

    def get_object_detail(
        self, object_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single object detail (full ObjectType with properties and actions)."""
        ...

    def get_object_detail_from_raw(
        self, raw: dict[str, Any], object_code: str
    ) -> dict[str, Any] | None:
        """Get single object detail from raw entity data — no full ontology load."""
        ...

    def get_object_subtree(
        self, object_code: str, *, base_id: str = ""
    ) -> dict[str, Any]:
        """Get an object's subtree — detail + related views, relations, actions."""
        ...

    def get_base_details(
        self,
        *,
        base_id: str = "",
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
        scene_id: str,
        *,
        base_id: str = "",
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
        self, object_codes: list[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract ObjectType JSON for each code from the backend."""
        ...

    def extract_views_detail(
        self, view_codes: list[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract View JSON for each code from the backend."""
        ...

    def extract_relations(
        self, object_codes_set: set[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract bidirectional Relation JSON where both ends are in object_codes_set."""
        ...

    def get_term_scope_info(self, base_id: str, object_code: str) -> dict[str, Any]:
        """Return {library_id, scene_id} identifying which scene contains object_code."""
        ...

    def query_ontologies_by_scene(
        self,
        scene_id: str,
        *,
        base_id: str = "",
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        type: str | None = None,
        owner_type: str | None = None,
        user_code: str | None = None,
        cross_scene: bool = False,
        ext_property_filters: dict[str, Any] | None = None,
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
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated views under a base."""
        ...

    def get_view_detail(
        self, view_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single view detail by code."""
        ...

    def get_objects_by_view(
        self,
        view_code: str,
        *,
        base_id: str = "",
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
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated relations under a base."""
        ...

    def get_relation_detail(
        self, rel_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single relation detail by code."""
        ...

    def get_relations_by_object(
        self,
        object_code: str,
        *,
        base_id: str = "",
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
        self, *, base_id: str = "", keyword: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated datasources under a base."""
        ...

    def get_datasource_detail(
        self, db_id: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single datasource detail by db_id."""
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
        object_code: str,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated actions on an object."""
        ...

    def get_action_detail(
        self,
        object_code: str,
        action_code: str,
        *,
        base_id: str = "",
    ) -> dict[str, Any] | None:
        """Get single action detail by code."""
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
        object_codes: list[str],
        *,
        base_id: str = "",
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """查询对象下属性绑定的术语类型（批量）。

        返回只含绑定了 terminology 的属性，未绑定的不出现在结果中。
        """
        ...

    def get_view_property_term_bindings(
        self,
        view_codes: list[str],
        *,
        base_id: str = "",
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
        name_text: str,
        scope_code: str,
        *,
        base_id: str = "",
    ) -> tuple[str, str] | None:
        """本体元数据: 单个中文属性名 → (field_code, field_name)。

        通过后端查询 scope_code 对应的 Object，遍历 fields 匹配 field_name / aliases。

        Returns:
            (field_code, field_name) 或 None（未命中）。
        """
        ...

    def resolve_property_names(
        self,
        name_texts: list[str],
        scope_code: str,
        *,
        base_id: str = "",
    ) -> dict[str, tuple[str, str]]:
        """批量版。返回 {name_text: (field_code, field_name)}。

        只返回成功解析的条目，未命中的不出现在返回 dict 中。
        """
        ...

    def get_property_aliases(
        self,
        field_code: str,
        scope_code: str,
        *,
        base_id: str = "",
    ) -> list[str]:
        """反向: field_code → 所有别名列表（含 field_name）。

        通过后端查询 scope_code 对应的 Object，遍历 fields 找到匹配项。
        """
        ...

    # ── Scope resolution helpers (used by unified recall) ──────────────────

    def get_view_included_objects(
        self, ontology_code: str, *, base_id: str = ""
    ) -> list[str]:
        """返回 ontology_code 对应视图所包含的子对象代码列表。"""
        ...

    def get_joinkey_related_objects(
        self, ontology_code: str, field_codes: list[str], *, base_id: str = ""
    ) -> list[str]:
        """返回通过 join key 与指定字段关联的对象代码列表。"""
        ...

    # ── 本体搜索 & 图查询（从 KnowledgeBackend 迁入）─────────────

    def resolve_scope_term_codes(
        self,
        base_id: str,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
    ) -> list[str] | None:
        """预解析 object_code / view_code 对应的属性码 + 自身 code 合集。

        供批量调用场景：调用方预解析一次，后续多次 search_ontology
        通过 ``pre_resolved_term_codes`` 传入，避免重复查询。
        返回 None 表示所有请求的 code 均无效。
        """
        ...

    def search_ontology(
        self,
        base_id: str,
        scene_ids: list[str],
        *,
        keyword: str | list[str],
        query_type: str = "vector",
        search_scope: str = "all",
        metadata_type: list[str] | None = None,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        property_code: list[str] | None = None,
        result_per_type: int = 5,
        top_k: int = 20,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """本体元数据与实例向量检索。"""
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

    async def search_object_instances_unstructured(
        self,
        *,
        base_id: str,
        object_code: str | None = None,
        query: str | None = None,
        queries: list[str] | None = None,
        top_k: int = 20,
        enable_chunk_recall: bool = True,
        kb_configs: dict[str, Any] | None = None,
    ) -> ObjectInstanceSearchResult:
        """非结构化对象实例检索 — 双路召回 + RRF 融合。

        输入模式（根据传参自动推断）：
        - ``query`` 非空 → sentence 模式：jieba 分词 → 多 token 匹配 + RRF
        - ``queries`` 非空 → word_batch 模式：每词作为 keyword 直接检索，并发 chunk 搜索

        **路1（术语实例检索）：**
        - object_code 非 None 时：单类型 ``search_terms(term_type_code=object_code, ...)``
        - object_code=None 时：跨全类型 ``search_terms_batch(keywords=tokens, term_type=None)``

        **路2（chunk → term 检索）：**
        - object_code 非 None 时：限定 KB（通过 EntityStore 获取 kb_id）
        - object_code=None 时：不限 KB（``kb_id=None`` 全库搜索）
        - word_batch 模式下每个词独立并发 chunk 搜索

        Args:
            base_id:         本体库 ID。
            object_code:     对象类型编码。None 表示不限类型。
            query:           sentence 模式的自然语言查询文本。
            queries:         word_batch 模式的词语列表。
            top_k:           每路最终融合返回的最大结果数。
            enable_chunk_recall: 是否启用路2（chunk 召回）。
            kb_configs:      KB 搜索配置。

        Returns:
            ObjectInstanceSearchResult(results={keyword: [hit, ...], ...})。
        """
        ...
