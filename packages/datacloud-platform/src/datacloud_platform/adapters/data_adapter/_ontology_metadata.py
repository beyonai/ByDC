"""Property resolution, terminology bindings, ontology search & graph."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable

from datacloud_platform.adapters.data_adapter._base import DataCloudDataBackendBase

logger = logging.getLogger(__name__)


class OntologyMetadataMixin(DataCloudDataBackendBase):
    """Property resolution, terminology bindings, ontology search & graph."""

    # ── OntologyBackend: Terminology bindings ──────────────────────────────

    def get_object_property_term_bindings(
        self,
        loader: OntologyQueryable,
        object_codes: list[str],
    ) -> list[dict[str, Any]]:
        """Extract terminology binding info for properties of given objects.

        Iterates ``loader._classes[code].fields`` and extracts binding code
        and name for each property with terminology configuration.
        """
        result: list[dict[str, Any]] = []
        for code in object_codes:
            cls = loader._classes.get(code)
            if cls is None:
                continue
            for f in cls.fields:
                term_code: str = getattr(f, "field_code", "") or ""
                term_name: str = getattr(f, "field_name", "") or ""
                if not term_code:
                    continue
                result.append(
                    {
                        "objectCode": code,
                        "objectName": getattr(cls, "object_name", ""),
                        "propertyCode": term_code,
                        "propertyName": term_name,
                        "dataType": getattr(f, "field_type", ""),
                        "bindingType": "property",
                    }
                )
        return result

    def get_view_property_term_bindings(
        self,
        loader: OntologyQueryable,
        view_codes: list[str],
    ) -> list[dict[str, Any]]:
        """Extract terminology binding info for view property mappings.

        Iterates ``loader._views[code].mappings``, resolves source object
        and property information via ``loader._classes``.
        """
        result: list[dict[str, Any]] = []
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        for vc in view_codes:
            view_data = raw_views.get(vc)
            if view_data is None:
                continue
            for m in view_data.get("mappings", []):
                prop_code = m.get("property_code", "")
                src_obj_code = m.get("source_object_code", "")
                src_col_code = m.get("source_object_column_code", "")
                if not prop_code:
                    continue
                src_obj = loader._classes.get(src_obj_code)
                src_obj_name = src_obj.object_name if src_obj else src_obj_code
                result.append(
                    {
                        "viewCode": vc,
                        "viewName": view_data.get("view_name", ""),
                        "propertyCode": prop_code,
                        "propertyName": m.get("property_name", ""),
                        "sourceObjectCode": src_obj_code,
                        "sourceObjectName": src_obj_name,
                        "sourceColumnCode": src_col_code,
                        "bindingType": "view_property",
                    }
                )
        return result

    def get_view_included_objects(
        self,
        loader: OntologyQueryable,
        ontology_code: str,
    ) -> list[str]:
        """视图包含的对象 code 列表（OWL metadata，零 DB）。

        在 loader._relations 中查询 HAS_OBJECT / MANY_TO_ONE 关系，
        找到该视图所包含的底层对象。用于确定 value recall 的跨本体 scope。

        替代 _collect_view_included_objects() 的 SQL 查询:
          SELECT target.term_code FROM term JOIN term_relation ...
          WHERE relation_category IN ('HAS_OBJECT','MANY_TO_ONE')
        """
        relations = getattr(loader, "_relations", None) or []
        result: list[str] = []
        for rel in relations:
            source = (
                getattr(rel, "source_object_code", "")
                or getattr(rel, "source_code", "")
                or ""
            )
            category = getattr(rel, "relation_category", "") or ""
            if source != ontology_code:
                continue
            if category not in ("HAS_OBJECT", "MANY_TO_ONE"):
                continue
            target = (
                getattr(rel, "target_object_code", "")
                or getattr(rel, "target_code", "")
                or ""
            )
            if target and target not in result:
                result.append(target)
        return result

    def get_joinkey_related_objects(
        self,
        loader: OntologyQueryable,
        ontology_code: str,
        field_codes: list[str],
    ) -> list[str]:
        """joinkey 关联的对象 code 列表（OWL metadata，零 DB）。

        在 loader._relations 中查询 HAS_OBJECT / MANY_TO_ONE 关系，
        筛选 ext_attrs.joinkeys.sourceField 匹配已确认字段的关联对象。

        替代 _collect_joinkey_related_objects() 的 SQL 查询。
        """
        if not field_codes:
            return []
        field_set = frozenset(field_codes)
        relations = getattr(loader, "_relations", None) or []
        result: list[str] = []
        for rel in relations:
            source = (
                getattr(rel, "source_object_code", "")
                or getattr(rel, "source_code", "")
                or ""
            )
            category = getattr(rel, "relation_category", "") or ""
            if source != ontology_code:
                continue
            if category not in ("HAS_OBJECT", "MANY_TO_ONE"):
                continue
            ext_attrs = getattr(rel, "ext_attrs", None) or {}
            jks = ext_attrs.get("joinkeys") or []
            if not jks:
                continue
            for jk in jks:
                if isinstance(jk, dict) and jk.get("sourceField") in field_set:
                    target = (
                        getattr(rel, "target_object_code", "")
                        or getattr(rel, "target_code", "")
                        or ""
                    )
                    if target and target not in result:
                        result.append(target)
                    break
        return result

    def resolve_property_name(
        self,
        loader: OntologyQueryable,
        name_text: str,
        scope_code: str,
    ) -> tuple[str, str] | None:
        """本体元数据: 单个中文属性名 → (field_code, field_name)。

        遍历 loader._classes[scope_code].fields，
        匹配 field_name / aliases。纯内存操作，零 DB 开销。
        """
        cls = loader._classes.get(scope_code)
        if cls is None:
            return None
        for f in cls.fields:
            field_name: str = getattr(f, "field_name", "") or ""
            aliases: list[str] = list(getattr(f, "aliases", []) or [])
            if name_text == field_name or name_text in aliases:
                return (getattr(f, "field_code", "") or "", field_name)
        return None

    def resolve_property_names(
        self,
        loader: OntologyQueryable,
        name_texts: list[str],
        scope_code: str,
    ) -> dict[str, tuple[str, str]]:
        """批量版。只返回成功解析的条目。"""
        result: dict[str, tuple[str, str]] = {}
        for name_text in name_texts:
            resolved = self.resolve_property_name(loader, name_text, scope_code)
            if resolved is not None:
                result[name_text] = resolved
        return result

    def get_property_aliases(
        self,
        loader: OntologyQueryable,
        field_code: str,
        scope_code: str,
    ) -> list[str]:
        """反向: field_code → 所有别名（含 field_name）。"""
        cls = loader._classes.get(scope_code)
        if cls is None:
            return []
        for f in cls.fields:
            if (getattr(f, "field_code", "") or "") == field_code:
                result: list[str] = [getattr(f, "field_name", "") or ""]
                result.extend(getattr(f, "aliases", []) or [])
                return result
        return []

    # ── OntologyBackend: Search & graph (new) ──────────────────────────────

    _ONTOLOGY_TYPE_TO_TERM: dict[str, str] = {
        "object": "object",
        "action": "ontology_action",
        "view": "view",
        "property": "property",
        "dimension": "dimension",
    }

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
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Unified vector search across metadata and instance terms.

        Uses the knowledge SDK embedding service and search engine to
        perform cosine-similarity vector search across metadata and
        instance term types.
        """
        _ = base_id, scene_ids, query_type, kwargs

        if not keyword:
            return {
                "metadata": [],
                "instances": [],
                "totalCount": {"metadata": 0, "instances": 0},
            }

        svc = self._get_embedding()
        vec = svc.get_text_embedding(keyword)

        result: dict[str, Any] = {
            "metadata": [],
            "instances": [],
            "totalCount": {"metadata": 0, "instances": 0},
        }

        engine = self._get_search_engine()

        _ALL_METADATA_TYPES = list(self._ONTOLOGY_TYPE_TO_TERM.values())
        if ontology_type:
            metadata_types = [
                self._ONTOLOGY_TYPE_TO_TERM[t]
                for t in ontology_type
                if t in self._ONTOLOGY_TYPE_TO_TERM
            ]
            if not metadata_types:
                metadata_types = _ALL_METADATA_TYPES
        else:
            metadata_types = _ALL_METADATA_TYPES

        view_code_set: set[str] | None = set(view_code) if view_code else None
        property_code_set: set[str] | None = (
            set(property_code) if property_code else None
        )

        limit = kwargs.get("limit", 20)

        if search_scope in ("metadata", "all"):
            metadata_hits = engine.search_terms_by_embedding(
                vector=vec,
                term_types=metadata_types,
                term_codes=object_code,
                limit=limit,
            )
            for hit in metadata_hits:
                term_code = str(hit.get("term_code", ""))
                term_type = str(hit.get("term_type_code", ""))
                if view_code_set is not None and term_code not in view_code_set:
                    continue
                if property_code_set is not None and term_code not in property_code_set:
                    continue
                entry: dict[str, Any] = {
                    "termCode": term_code,
                    "termType": term_type,
                    "nameText": str(hit.get("name_text", hit.get("term_name", ""))),
                    "score": round(float(hit["score"]), 4),
                }
                result["metadata"].append(entry)
            result["totalCount"]["metadata"] = len(result["metadata"])

        if search_scope in ("instance", "all"):
            reader = self._get_knowledge_reader()
            instance_type_codes: list[str] = []
            try:
                instance_type_codes = sorted(
                    reader.get_type_codes_by_category(categories={3, 4, 5})
                )
            except Exception:
                logger.exception(
                    "Failed to get instance type codes for search_ontology"
                )

            if instance_type_codes:
                instance_hits = engine.search_terms_by_embedding(
                    vector=vec,
                    term_types=instance_type_codes,
                    limit=limit,
                )
                result["instances"] = [
                    {
                        "termCode": hit["term_code"],
                        "termType": hit["term_type_code"],
                        "nameText": hit.get("name_text", hit.get("term_name", "")),
                        "score": round(float(hit["score"]), 4),
                    }
                    for hit in instance_hits
                ]
                result["totalCount"]["instances"] = len(result["instances"])

        return result

    def search_ontology_batch(
        self,
        base_id: str,
        keyword: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Batch search across all scenes of a base via vector search."""
        _ = base_id

        if not keyword:
            return {
                "metadata": [],
                "instances": [],
                "totalCount": {"metadata": 0, "instances": 0},
            }

        svc = self._get_embedding()
        vec = svc.get_text_embedding(keyword)

        result: dict[str, Any] = {
            "metadata": [],
            "instances": [],
            "totalCount": {"metadata": 0, "instances": 0},
        }

        engine = self._get_search_engine()

        _METADATA_TERM_TYPES = {
            "object",
            "view",
            "dimension",
            "property",
            "ontology_action",
        }
        metadata_hits = engine.search_terms_by_embedding(
            vector=vec,
            term_types=list(_METADATA_TERM_TYPES),
            limit=limit,
        )
        seen_metadata: set[tuple[str, str]] = set()
        for hit in metadata_hits:
            key = (str(hit["term_code"]), str(hit["term_type_code"]))
            if key in seen_metadata:
                continue
            seen_metadata.add(key)
            result["metadata"].append(
                {
                    "termCode": str(hit["term_code"]),
                    "termType": str(hit["term_type_code"]),
                    "nameText": str(hit.get("name_text", hit.get("term_name", ""))),
                    "score": round(float(hit["score"]), 4),
                }
            )
        result["totalCount"]["metadata"] = len(result["metadata"])

        reader = self._get_knowledge_reader()
        instance_type_codes: list[str] = []
        try:
            instance_type_codes = sorted(
                reader.get_type_codes_by_category(categories={3, 4, 5})
            )
        except Exception:
            logger.exception(
                "Failed to get instance type codes for search_ontology_batch"
            )

        if instance_type_codes:
            instance_hits = engine.search_terms_by_embedding(
                vector=vec,
                term_types=instance_type_codes,
                limit=limit,
            )
            seen_instances: set[tuple[str, str]] = set()
            for hit in instance_hits:
                key = (str(hit["term_code"]), str(hit["term_type_code"]))
                if key in seen_instances:
                    continue
                seen_instances.add(key)
                result["instances"].append(
                    {
                        "termCode": str(hit["term_code"]),
                        "termType": str(hit["term_type_code"]),
                        "nameText": str(hit.get("name_text", hit.get("term_name", ""))),
                        "score": round(float(hit["score"]), 4),
                    }
                )
            result["totalCount"]["instances"] = len(result["instances"])

        return result

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
        """Graph traversal query — not yet implemented."""
        _ = base_id, scene_id, object_code, match_by, values, step
        return {"nodes": [], "edges": []}

    def search_instances(
        self,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search instances in a base — not yet implemented."""
        _ = base_id, object_code, select, where
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
        """Find shortest path between two objects — not yet implemented."""
        _ = base_id, scene_id, match_by, start_node, end_node, direction
        return {"path": [], "edges": [], "hops": -1}
