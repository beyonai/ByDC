"""OntologyQueryMixin — read-only ontology query methods."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from datacloud_platform.backends._contracts import _HasOntologyBackend

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable
    from datacloud_platform.models.shared import ObjectSummary

logger = logging.getLogger(__name__)


class OntologyQueryMixin:
    """Mixin for read-only ontology loading and object queries."""

    def load_ontology(
        self: _HasOntologyBackend,
        base_id: str,
        base_path: str | Path,
    ) -> OntologyQueryable:
        """Load ontology from a base_path, returning a queryable handle."""
        _ = base_path  # passed for backward API compatibility; internally derived
        return self._load_ontology_cached(base_id)

    def get_objects(
        self: _HasOntologyBackend,
        base_id: str,
        *,
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ObjectSummary], int]:
        """Get paginated ontology object summaries under a base with optional filtering.

        Returns:
            Tuple of (items list, total count).
        """
        return self._ontology_for(base_id).get_objects(
            base_id=base_id,
            owner_type=owner_type,
            user_code=user_code,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )

    def get_object_detail(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
    ) -> dict[str, Any] | None:
        """Get a single object's full detail (ObjectType with properties and actions).

        Tries direct entity-store lookup first, falling back to full ontology load
        for backends without entity-store support.
        """
        backend = self._ontology_for(base_id)
        # Direct path: read single object from entity store, parse locally
        try:
            store = backend._entity_store.sub_store(base_id)  # type: ignore[attr-defined]
            raw = store.get("objects", object_code)
            if raw is not None:
                return backend.get_object_detail_from_raw(raw, object_code)
        except (AttributeError, Exception):
            pass  # entity_store not available → fall through to full load
        # Fallback: full ontology load via backend
        return backend.get_object_detail(object_code, base_id=base_id)

    # ── Property Term Bindings ─────────────────────────────────────

    def get_object_property_term_bindings(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        *,
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """查询对象下属性绑定的术语类型。

        返回只含绑定了 terminology 的属性，未绑定的不出现在结果中。
        """
        return self._ontology_for(base_id).get_object_property_term_bindings(
            [object_code],
            base_id=base_id,
            term_master_type=term_master_type,
            property_codes=property_codes,
        )

    def get_view_property_term_bindings(
        self: _HasOntologyBackend,
        base_id: str,
        view_code: str,
        *,
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """查询视图下属性绑定的术语类型。

        视图属性通过 source_object → source_object_property 穿透到底层
        Object 的 Property.terminology。
        """
        return self._ontology_for(base_id).get_view_property_term_bindings(
            [view_code],
            base_id=base_id,
            term_master_type=term_master_type,
            property_codes=property_codes,
        )

    def resolve_property_name(
        self: _HasOntologyBackend,
        base_id: str,
        name_text: str,
        scope_code: str,
    ) -> tuple[str, str] | None:
        """本体元数据: 中文属性名 → (field_code, field_name)。"""
        return self._ontology_for(base_id).resolve_property_name(
            name_text, scope_code, base_id=base_id
        )

    def resolve_property_names(
        self: _HasOntologyBackend,
        base_id: str,
        name_texts: list[str],
        scope_code: str,
    ) -> dict[str, tuple[str, str]]:
        """批量: 中文属性名列表 → {name_text: (field_code, field_name)}。"""
        return self._ontology_for(base_id).resolve_property_names(
            name_texts, scope_code, base_id=base_id
        )

    def get_property_aliases(
        self: _HasOntologyBackend,
        base_id: str,
        field_code: str,
        scope_code: str,
    ) -> list[str]:
        """反向: field_code → 所有别名（含 field_name）。"""
        return self._ontology_for(base_id).get_property_aliases(
            field_code, scope_code, base_id=base_id
        )

    def get_view_included_objects(
        self: _HasOntologyBackend,
        base_id: str,
        ontology_code: str,
    ) -> list[str]:
        """视图包含的对象 code 列表（OWL metadata，零 DB）。"""
        return self._ontology_for(base_id).get_view_included_objects(
            ontology_code, base_id=base_id
        )

    def get_joinkey_related_objects(
        self: _HasOntologyBackend,
        base_id: str,
        ontology_code: str,
        field_codes: list[str],
    ) -> list[str]:
        """joinkey 关联的对象 code 列表（OWL metadata，零 DB）。"""
        return self._ontology_for(base_id).get_joinkey_related_objects(
            ontology_code, field_codes, base_id=base_id
        )

    # ── Ontology Search & Graph (from KnowledgeBackend → OntologyBackend) ──

    def search_ontology(
        self: _HasOntologyBackend,
        base_id: str,
        scene_ids: list[str],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """本体元数据与实例向量/关键词检索。"""
        return self._ontology_for(base_id).search_ontology(base_id, scene_ids, **kwargs)

    def graph_query(
        self: _HasOntologyBackend,
        base_id: str,
        scene_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """本体图遍历查询，返回 nodes + edges。"""
        return self._ontology_for(base_id).graph_query(base_id, scene_id, **kwargs)

    def graph_path(
        self: _HasOntologyBackend,
        base_id: str,
        scene_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """本体图最短路径查询。"""
        return self._ontology_for(base_id).graph_path(base_id, scene_id, **kwargs)

    def search_instances(
        self: _HasOntologyBackend,
        base_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """本体实例搜索。"""
        return self._ontology_for(base_id).search_instances(base_id, **kwargs)
