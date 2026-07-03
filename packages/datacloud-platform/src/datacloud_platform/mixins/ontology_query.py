"""OntologyQueryMixin — read-only ontology query methods."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from datacloud_platform.backends._contracts import _HasOntologyBackend
from datacloud_platform.ontology_store import CacheMode

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
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> OntologyQueryable:
        """Load ontology from a base_path, returning a queryable handle.

        Respects *cache_mode* for OntologyStore index priming before loading.
        """
        _ = base_path  # passed for backward API compatibility; internally derived
        return self._load_ontology_cached(base_id, cache_mode=cache_mode)

    def get_objects(
        self: _HasOntologyBackend,
        base_id: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[ObjectSummary]:
        """Get all ontology object summaries under a base."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_objects(loader, base_id)

    def get_object_detail(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> dict[str, Any] | None:
        """Get a single object's full detail (ObjectType with properties and actions)."""
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_object_detail(loader, object_code)

    # ── Property Term Bindings ─────────────────────────────────────

    def get_object_property_term_bindings(
        self: _HasOntologyBackend,
        base_id: str,
        object_code: str,
        *,
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[dict[str, Any]]:
        """查询对象下属性绑定的术语类型。

        返回只含绑定了 terminology 的属性，未绑定的不出现在结果中。
        """
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_object_property_term_bindings(
            loader,
            [object_code],
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
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[dict[str, Any]]:
        """查询视图下属性绑定的术语类型。

        视图属性通过 source_object → source_object_property 穿透到底层
        Object 的 Property.terminology。
        """
        backend = self._ontology_for(base_id)
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return backend.get_view_property_term_bindings(
            loader,
            [view_code],
            term_master_type=term_master_type,
            property_codes=property_codes,
        )

    def resolve_property_name(
        self: _HasOntologyBackend,
        base_id: str,
        name_text: str,
        scope_code: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> tuple[str, str] | None:
        """本体元数据: 中文属性名 → (field_code, field_name)。"""
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return self._ontology_for(base_id).resolve_property_name(
            loader, name_text, scope_code
        )

    def resolve_property_names(
        self: _HasOntologyBackend,
        base_id: str,
        name_texts: list[str],
        scope_code: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> dict[str, tuple[str, str]]:
        """批量: 中文属性名列表 → {name_text: (field_code, field_name)}。"""
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return self._ontology_for(base_id).resolve_property_names(
            loader, name_texts, scope_code
        )

    def get_property_aliases(
        self: _HasOntologyBackend,
        base_id: str,
        field_code: str,
        scope_code: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[str]:
        """反向: field_code → 所有别名（含 field_name）。"""
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return self._ontology_for(base_id).get_property_aliases(
            loader, field_code, scope_code
        )

    def get_view_included_objects(
        self: _HasOntologyBackend,
        base_id: str,
        ontology_code: str,
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[str]:
        """视图包含的对象 code 列表（OWL metadata，零 DB）。"""
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return self._ontology_for(base_id).get_view_included_objects(
            loader, ontology_code
        )

    def get_joinkey_related_objects(
        self: _HasOntologyBackend,
        base_id: str,
        ontology_code: str,
        field_codes: list[str],
        *,
        cache_mode: CacheMode = CacheMode.REALTIME,
    ) -> list[str]:
        """joinkey 关联的对象 code 列表（OWL metadata，零 DB）。"""
        loader = self._load_ontology_cached(base_id, cache_mode=cache_mode)
        return self._ontology_for(base_id).get_joinkey_related_objects(
            loader, ontology_code, field_codes
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

    def search_ontology_batch(
        self: _HasOntologyBackend,
        base_id: str,
        keyword: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """跨场景批量本体检索，聚合+去重结果。"""
        return self._ontology_for(base_id).search_ontology_batch(
            base_id, keyword, limit=limit
        )

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
