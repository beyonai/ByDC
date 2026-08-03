"""No-op backends — return empty/null results, write operations raise PermissionError.

Used as fallback when a backend type has no implementation configured for a base.
"""

from __future__ import annotations

from typing import Any


class _NoopOntologyBackend:
    """Ontology backend where all reads return empty and all writes are forbidden."""

    def parse_owl(self, directory: Any) -> Any:
        """Return empty ParsedOwlContent."""
        from datacloud_platform.models.shared import ParsedOwlContent

        return ParsedOwlContent(objects=[], views=[], relations=[])

    def load_ontology(self, base_path: Any) -> Any:
        """Raise PermissionError — no ontology available."""
        raise PermissionError("Ontology not available")

    def load_terms(self, *, base_id: str = "", library_id: str = "PERSONAL_LIB") -> Any:
        """Return None."""
        _ = base_id
        return None

    def batch_import_ontology(
        self,
        base_path: Any,
        objects: list[dict[str, Any]],
        views: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        dbsources: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def create_table(self, object_code: str, fields: list[dict[str, Any]]) -> None:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def drop_table(self, object_code: str) -> None:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def get_objects(
        self,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return empty list."""
        _ = base_id, owner_type, user_code, keyword
        return [], 0

    def get_object_detail(
        self, object_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Return None."""
        return None

    def get_object_detail_from_raw(
        self, raw: dict[str, Any], object_code: str
    ) -> dict[str, Any] | None:
        """Return None — noop backend has no entity data."""
        return None

    def get_object_subtree(
        self, object_code: str, *, base_id: str = ""
    ) -> dict[str, Any]:
        """Return empty dict."""
        _ = object_code, base_id
        return {}

    def get_base_details(
        self,
        *,
        base_id: str = "",
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return empty base details."""
        _ = base_id, view_code, object_code
        return {
            "scene": None,
            "views": [],
            "objects": [],
            "actions": [],
            "relations": [],
            "dbsources": [],
            "version": None,
        }

    # -- Object CRUD (no-op) --

    def create_object(self, base_id: str, obj: Any) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def update_object(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def delete_object(self, base_id: str, object_code: str) -> None:
        """No-op — delete is safe to be idempotent."""

    # -- Scene management (no-op) --

    def list_scenes(self, base_id: str) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        """Return 0."""
        return 0

    def get_scene_details(
        self,
        scene_id: str,
        *,
        base_id: str = "",
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return empty scene details."""
        _ = scene_id, base_id, view_code, object_code
        return {
            "scene": None,
            "views": [],
            "objects": [],
            "actions": [],
            "relations": [],
            "dbsources": [],
            "version": None,
        }

    def get_scene_members(
        self, base_id: str, scene_id: str
    ) -> tuple[list[str], list[str]]:
        """Return empty members."""
        _ = base_id, scene_id
        return [], []

    def extract_objects_detail(
        self, object_codes: list[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        _ = object_codes, base_id
        return []

    def extract_views_detail(
        self, view_codes: list[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        _ = view_codes, base_id
        return []

    def extract_relations(
        self, object_codes_set: set[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        _ = object_codes_set, base_id
        return []

    def get_term_scope_info(self, base_id: str, object_code: str) -> dict[str, Any]:
        """Return default scope info — no ontology available."""
        return {"library_id": "PERSONAL_LIB", "scene_id": ""}

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
        """Return empty result."""
        _ = (
            scene_id,
            base_id,
            page,
            page_size,
            keyword,
            type,
            owner_type,
            user_code,
            cross_scene,
            ext_property_filters,
        )
        return {"data": {"objects": [], "views": []}, "totalCount": 0}

    # -- Scene CRUD (no-op) --

    def create_scene(self, base_id: str, scene: Any) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def update_scene(self, base_id: str, scene_id: str, updates: Any) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def delete_scene(self, base_id: str, scene_id: str) -> None:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def add_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def remove_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    # -- Scene reverse-lookup queries (no-op) --

    def get_object_scene_count(self, base_id: str, object_code: str) -> int:
        """Return 0."""
        _ = base_id
        _ = object_code
        return 0

    def get_view_scene_count(self, base_id: str, view_code: str) -> int:
        """Return 0."""
        _ = base_id
        _ = view_code
        return 0

    def remove_object_from_all_scenes(self, base_id: str, object_code: str) -> int:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def remove_view_from_all_scenes(self, base_id: str, view_code: str) -> int:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def get_scenes_containing_object(self, base_id: str, object_code: str) -> list[str]:
        """Return empty list."""
        _ = base_id
        _ = object_code
        return []

    # -- View CRUD (no-op) --

    def get_views(
        self,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return empty list."""
        _ = base_id, owner_type, user_code, keyword
        return [], 0

    def get_view_detail(
        self, view_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Return None."""
        _ = view_code, base_id
        return None

    def get_objects_by_view(
        self,
        view_code: str,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        _ = view_code, base_id, owner_type, user_code, keyword
        return []

    def create_view(self, base_id: str, view: Any) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def update_view(self, base_id: str, view_code: str, view: Any) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def delete_view(self, base_id: str, view_code: str) -> None:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    # -- Relation CRUD (no-op) --

    def get_relations(
        self,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return empty list."""
        _ = base_id, owner_type, user_code, keyword
        return [], 0

    def get_relation_detail(
        self, rel_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Return None."""
        _ = rel_code, base_id
        return None

    def get_relations_by_object(
        self,
        object_code: str,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        _ = object_code, base_id, owner_type, user_code
        return []

    def create_relation(self, base_id: str, rel: Any) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def update_relation(self, base_id: str, rel_code: str, rel: Any) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def delete_relation(self, base_id: str, rel_code: str) -> None:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    # -- Action CRUD (no-op) --

    def get_actions(
        self,
        object_code: str,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return empty list."""
        _ = object_code, base_id, owner_type, user_code, keyword
        return [], 0

    def get_action_detail(
        self,
        object_code: str,
        action_code: str,
        *,
        base_id: str = "",
    ) -> dict[str, Any] | None:
        """Return None."""
        _ = object_code, action_code, base_id
        return None

    def create_action(self, base_id: str, object_code: str, action: Any) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def update_action(
        self,
        base_id: str,
        object_code: str,
        action_code: str,
        action: Any,
    ) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def delete_action(self, base_id: str, object_code: str, action_code: str) -> None:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    # -- Datasource CRUD (no-op) --

    def get_datasources(
        self, *, base_id: str = "", keyword: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Return empty list."""
        _ = base_id, keyword
        return [], 0

    def get_datasource_detail(
        self, db_id: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Return None."""
        _ = db_id, base_id
        return None

    def create_datasource(self, base_id: str, ds: Any) -> Any:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Ontology not available")

    # -- Property term bindings (no-op) --

    def get_object_property_term_bindings(
        self,
        object_codes: list[str],
        *,
        base_id: str = "",
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return empty list — no ontology available."""
        _ = object_codes, base_id, term_master_type, property_codes
        return []

    def get_view_property_term_bindings(
        self,
        view_codes: list[str],
        *,
        base_id: str = "",
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return empty list — no ontology available."""
        _ = view_codes, base_id, term_master_type, property_codes
        return []

    # -- Property name / alias resolution (no-op) --

    def resolve_property_name(
        self,
        name_text: str,
        scope_code: str,
        *,
        base_id: str = "",
    ) -> tuple[str, str] | None:
        """Return None — no ontology available."""
        _ = name_text, scope_code, base_id
        return None

    def resolve_property_names(
        self,
        name_texts: list[str],
        scope_code: str,
        *,
        base_id: str = "",
    ) -> dict[str, tuple[str, str]]:
        """Return empty dict — no ontology available."""
        _ = name_texts, scope_code, base_id
        return {}

    def get_property_aliases(
        self,
        field_code: str,
        scope_code: str,
        *,
        base_id: str = "",
    ) -> list[str]:
        """Return empty list — no ontology available."""
        _ = field_code, scope_code, base_id
        return []

    def get_view_included_objects(
        self,
        ontology_code: str,
        *,
        base_id: str = "",
    ) -> list[str]:
        """Return empty list."""
        _ = ontology_code, base_id
        return []

    def get_joinkey_related_objects(
        self,
        ontology_code: str,
        field_codes: list[str],
        *,
        base_id: str = "",
    ) -> list[str]:
        """Return empty list."""
        _ = ontology_code, field_codes, base_id
        return []

    # -- Ontology search & graph (no-op) --

    def resolve_scope_term_codes(
        self,
        base_id: str,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
    ) -> list[str] | None:
        """No-op."""
        _ = base_id, object_code, view_code
        return None

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
        """Return empty keyword-keyed result: ``{kw: {metadata:[], instances:[], totalCount:{...}}}``."""
        empty: dict[str, Any] = {
            "metadata": [],
            "instances": [],
            "totalCount": {"metadata": 0, "instances": 0},
        }
        keywords: list[str] = [keyword] if isinstance(keyword, str) else list(keyword)
        keywords = [k for k in keywords if k and k.strip()]
        if not keywords:
            return {}
        return {kw: dict(empty) for kw in keywords}

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
        """Return empty result."""
        return {"data": [], "totalCount": 0}

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
        """Return empty result."""
        return {"data": [], "totalCount": 0}

    def search_instances(
        self,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return empty result."""
        return {"data": [], "totalCount": 0}

    def search_object_instances_unstructured(
        self,
        *,
        base_id: str,
        object_codes: list[str] | None = None,
        query: str | None = None,
        queries: list[str] | None = None,
        top_k: int = 20,
        enable_chunk_recall: bool = True,
    ) -> Any:  # ObjectInstanceSearchResult
        """返回空结果 — 非结构化对象实例检索在当前后端无数据。"""
        from datacloud_platform.models.shared import ObjectInstanceSearchResult

        _ = (
            base_id,
            object_codes,
            query,
            queries,
            top_k,
            enable_chunk_recall,
        )
        return ObjectInstanceSearchResult(results={})


class _NoopTermBackend:
    """Term backend where all reads return empty/null and mutations are no-ops."""

    # ── Term ────────────────────────────────────────────────────────────

    def search_terms(
        self,
        *,
        dataset_ids: list[str] | None = None,
        keyword: str | None = None,
        term_name: str | None = None,
        term_type: str | None = None,
        query_type: str = "fulltext",
        parent_term_code: str | None = None,
        label_filters: list[dict[str, Any]] | None = None,
        label_condition: str = "and",
        term_ids: list[str] | None = None,
        top_k: int = 20,
        offset: int = 0,
        query_vector: list[float] | None = None,
    ) -> dict[str, Any]:
        """Return empty search result."""
        return {"data": [], "totalCount": 0}

    def search_terms_batch(
        self,
        *,
        keywords: list[str],
        dataset_ids: list[str] | None = None,
        term_type_codes: list[str] | None = None,
        query_type: str = "mixed",
        parent_term_code: str | None = None,
        label_filters: list[dict[str, Any]] | None = None,
        label_condition: str = "and",
        ext_attrs: dict[str, Any] | None = None,
        top_k: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return empty batch results."""
        return {kw: {"data": [], "totalCount": 0} for kw in keywords}

    def get_term_detail(
        self, *, library_id: str, term_id: str
    ) -> dict[str, Any] | None:
        """Return None."""
        _ = library_id
        return None

    def list_terms(
        self,
        *,
        library_id: str,
        term_type: str | None = None,
        domain_code: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Return empty list."""
        _ = library_id, domain_code, keyword
        return {
            "data": [],
            "totalCount": 0,
            "pageIndex": page_index,
            "pageSize": page_size,
        }

    def create_term(self, *, term: dict[str, Any]) -> dict[str, Any]:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Term backend not available")

    def import_terms(
        self, *, library_id: str, terms: list[dict[str, Any]], backfill: bool = False
    ) -> dict[str, Any]:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Term backend not available")

    def update_term(
        self, *, library_id: str = "", term_id: str, updates: dict[str, Any]
    ) -> None:
        """Raise PermissionError — write forbidden."""
        _ = term_id, updates
        raise PermissionError("Term backend not available")

    def delete_term(self, *, term_id: str) -> None:
        """Raise PermissionError — write forbidden."""
        raise PermissionError("Term backend not available")

    def query_term_relations(
        self,
        *,
        term_id: str,
        relation_category: str | None = None,
        direction: str = "both",
        depth: int = 1,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Return empty result."""
        _ = term_id, relation_category, direction, depth, keyword, page_index, page_size
        return {"data": [], "totalCount": 0}

    def query_term_relations_tree(
        self,
        *,
        term_id: str,
        max_depth: int = 3,
        relation_category: str | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Return empty result."""
        _ = term_id, max_depth, relation_category, direction
        return {"data": [], "totalCount": 0}

    def query_term_relations_tree_batch(
        self,
        *,
        term_ids: list[str],
        max_depth: int = 3,
        direction: str = "both",
        relation_category: str | None = None,
    ) -> dict[str, Any]:
        """Return empty result."""
        _ = term_ids, max_depth, direction, relation_category
        return {"data": [], "totalCount": 0}

    def query_edges_by_kb_id(
        self,
        *,
        kb_ids: list[str],
        limit: int = 2000,
        relation_category: str | None = None,
    ) -> dict[str, Any]:
        """Return empty result."""
        _ = kb_ids, limit, relation_category
        return {"data": []}

    # ── TermRelation ────────────────────────────────────────────────────

    def list_term_relations(
        self,
        *,
        source_term_id: str | None = None,
        target_term_id: str | None = None,
        relation_category: str | None = None,
        relation_code: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
        strict: bool = False,
    ) -> dict[str, Any]:
        _ = (
            source_term_id,
            target_term_id,
            relation_category,
            relation_code,
            keyword,
            page_index,
            page_size,
        )
        if strict:
            raise PermissionError("Term backend not available")
        return {"data": [], "totalCount": 0}

    def get_term_relation(
        self,
        *,
        relation_id: str,
        strict: bool = False,
    ) -> dict[str, Any] | None:
        if strict:
            raise PermissionError("Term backend not available")
        return None

    def create_term_relation(self, *, relation: dict[str, Any]) -> dict[str, Any]:
        raise PermissionError("Term backend not available")

    def update_term_relation(
        self, *, relation_id: str, updates: dict[str, Any]
    ) -> None:
        raise PermissionError("Term backend not available")

    def delete_term_relation(self, *, relation_id: str) -> None:
        raise PermissionError("Term backend not available")

    # ── TermName ────────────────────────────────────────────────────────

    def list_term_names(
        self, *, term_id: str | None = None, name_text: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_term_name(self, *, name_id: str) -> dict[str, Any] | None:
        return None

    def create_term_name(self, *, name: dict[str, Any]) -> dict[str, Any]:
        raise PermissionError("Term backend not available")

    def update_term_name(self, *, name_id: str, updates: dict[str, Any]) -> None:
        raise PermissionError("Term backend not available")

    def delete_term_name(self, *, name_id: str) -> None:
        raise PermissionError("Term backend not available")

    # ── TermKnowledge ───────────────────────────────────────────────────

    def list_term_knowledges(
        self, *, term_id: str | None = None, ext_system: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_term_knowledge(self, *, knowledge_id: str) -> dict[str, Any] | None:
        return None

    def create_term_knowledge(self, *, knowledge: dict[str, Any]) -> dict[str, Any]:
        raise PermissionError("Term backend not available")

    def update_term_knowledge(
        self, *, knowledge_id: str, updates: dict[str, Any]
    ) -> None:
        raise PermissionError("Term backend not available")

    def delete_term_knowledge(self, *, knowledge_id: str) -> None:
        raise PermissionError("Term backend not available")

    # ── TermLibrary ─────────────────────────────────────────────────────

    def list_term_libraries(
        self,
        *,
        library_code: str | None = None,
        library_name: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

    def get_term_library(self, *, library_id: str) -> dict[str, Any] | None:
        return None

    def create_term_library(self, *, library: dict[str, Any]) -> dict[str, Any]:
        raise PermissionError("Term backend not available")

    def update_term_library(self, *, library_id: str, updates: dict[str, Any]) -> None:
        raise PermissionError("Term backend not available")

    def delete_term_library(self, *, library_id: str) -> None:
        raise PermissionError("Term backend not available")

    # ── TermType ────────────────────────────────────────────────────────

    def list_term_types(
        self,
        *,
        library_id: str,
        domain_code: str | None = None,
        type_category: int | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        _ = library_id, domain_code, type_category, keyword, page_index, page_size
        return {"items": [], "total": 0}

    def get_term_type(
        self, *, library_id: str, type_code: str
    ) -> dict[str, Any] | None:
        _ = library_id
        return None

    def list_term_type_relations(
        self,
        *,
        library_id: str,
        type_code: str,
        direction: str = "both",
        relation_category: str | None = None,
        keyword: str | None = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        return {"items": [], "total": 0}

    def create_term_type(self, *, term_type: dict[str, Any]) -> dict[str, Any]:
        raise PermissionError("Term backend not available")

    def update_term_type(
        self, *, library_id: str, type_code: str, updates: dict[str, Any]
    ) -> None:
        _ = library_id
        raise PermissionError("Term backend not available")

    def delete_term_type(self, *, library_id: str, type_code: str) -> None:
        _ = library_id
        raise PermissionError("Term backend not available")

    # ── Domain ──────────────────────────────────────────────────────────

    def list_domains(
        self, *, library_id: str, parent_id: str | None = None
    ) -> list[dict[str, Any]]:
        _ = library_id
        return []

    def get_domain(self, *, library_id: str, domain_code: str) -> dict[str, Any] | None:
        _ = library_id
        return None

    def create_domain(self, *, domain: dict[str, Any]) -> dict[str, Any]:
        raise PermissionError("Term backend not available")

    def update_domain(
        self, *, library_id: str, domain_code: str, updates: dict[str, Any]
    ) -> None:
        raise PermissionError("Term backend not available")

    def delete_domain(self, *, library_id: str, domain_code: str) -> None:
        raise PermissionError("Term backend not available")

    def list_domain_term_types(self, *, domain_id: str) -> list[dict[str, Any]]:
        return []

    # ── Vector ──────────────────────────────────────────────────────────

    def embed(self, text: str) -> list[float]:
        """Return zero vector."""
        return [0.0] * 768

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return zero vectors."""
        return [[0.0] * 768 for _ in texts]

    def search_by_embedding(
        self, vector: list[float], term_types: list[str], limit: int = 20
    ) -> list[Any]:
        """Return empty list."""
        return []

    # ── Sync ────────────────────────────────────────────────────────────

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        """No-op."""

    def remove_terms(self, entity_code: str) -> None:
        """No-op."""

    # ── TermSyncHandler ─────────────────────────────────────────────

    def ensure_term_type(self, *, base_id: str, type_code: str, type_name: str) -> None:
        """No-op."""

    def upsert_terms(self, *, base_id: str, terms: list[dict[str, Any]]) -> list[str]:
        """No-op — returns empty list."""
        return []

    def delete_terms(
        self,
        *,
        base_id: str,
        term_ids: list[str] | None = None,
        terms: list[dict[str, Any]] | None = None,
    ) -> None:
        """No-op."""


class _NoopExecutionBackend:
    """Execution backend where all operations are forbidden."""

    async def execute_action(
        self, loader: Any, object_code: str, action_code: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Raise PermissionError — execution not available."""
        raise PermissionError("Execution not available")

    def generate_action_tools(
        self, loader: Any, object_code: str
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def generate_dynamic_query_tools(
        self, loader: Any, object_code: str
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def generate_virtual_actions(
        self, loader: Any, mounted_objects: list[str]
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def inject_virtual_actions(self, loader: Any) -> None:
        """No-op."""

    def generate_plan(self, query: str, loader: Any, context: Any) -> Any:
        """Return empty plan."""
        return {"steps": []}

    def build_filters_schema(self, fields: list[Any]) -> dict[str, Any]:
        """Return empty schema."""
        return {}


class _NoopStorageBackend:
    """Storage backend where all operations are forbidden."""

    def store_result(
        self, key: str, data: bytes, *, metadata: dict[str, Any] | None = None
    ) -> str:
        """Raise PermissionError — storage not available."""
        raise PermissionError("Storage not available")

    def get_result(self, file_id: str) -> bytes:
        """Raise PermissionError — storage not available."""
        raise PermissionError("Storage not available")

    def delete_result(self, file_id: str) -> None:
        """Raise PermissionError — storage not available."""
        raise PermissionError("Storage not available")

    def list_results(self, prefix: str = "") -> list[Any]:
        """Return empty list."""
        return []
