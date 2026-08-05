"""Property resolution, terminology bindings, ontology search & graph."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    pass

from datacloud_platform.adapters.data_adapter._base import DataCloudDataBackendBase

logger = logging.getLogger(__name__)

# Lazy imports for RRF fusion
_rrf_fuse: Any = None


def _get_rrf_fuse() -> Any:
    """Lazy import rrf_fuse to avoid hard dependency at module load time."""
    global _rrf_fuse
    if _rrf_fuse is None:
        from datacloud_knowledge.contracts.rrf import rrf_fuse as _f

        _rrf_fuse = _f
    return _rrf_fuse


def _map_get_or_fetch(
    preloaded: dict[str, dict[str, Any]] | None,
    store: Any,
    entity_type: str,
    code: str,
) -> dict[str, Any] | None:
    """Look up *code* in *preloaded* dict; fall back to ``store.get()`` if missing.

    Used by ``_enrich_metadata_hits`` to support both pre-loaded bulk queries
    (caller passes ``object_map``/``view_map``) and individual store fetches
    (backward compatibility when maps are ``None``).
    """
    if preloaded is not None:
        return preloaded.get(code)
    return cast("dict[str, Any] | None", store.get(entity_type, code))


class OntologyMetadataMixin(DataCloudDataBackendBase):
    """Property resolution, terminology bindings, ontology search & graph."""

    # ── OntologyBackend: Terminology bindings ──────────────────────────────

    def get_object_property_term_bindings(
        self,
        object_codes: list[str],
        *,
        base_id: str = "",
    ) -> list[dict[str, Any]]:
        """Extract terminology binding info — stub (shadowed by OntologyBackendMixin)."""
        _ = object_codes, base_id
        return []

    def get_view_property_term_bindings(
        self,
        view_codes: list[str],
        *,
        base_id: str = "",
    ) -> list[dict[str, Any]]:
        """Extract terminology binding info for view properties — stub (shadowed by OntologyBackendMixin)."""
        _ = view_codes, base_id
        return []

    def get_view_included_objects(
        self,
        ontology_code: str,
        *,
        base_id: str = "",
    ) -> list[str]:
        """View included object codes — stub (shadowed by OntologyBackendMixin)."""
        _ = ontology_code, base_id
        return []

    def get_joinkey_related_objects(
        self,
        ontology_code: str,
        field_codes: list[str],
        *,
        base_id: str = "",
    ) -> list[str]:
        """Joinkey related objects — stub (shadowed by OntologyBackendMixin)."""
        _ = ontology_code, field_codes, base_id
        return []

    def resolve_property_name(
        self,
        name_text: str,
        scope_code: str,
        *,
        base_id: str = "",
    ) -> tuple[str, str] | None:
        """Resolve single property name — stub (shadowed by OntologyBackendMixin)."""
        _ = name_text, scope_code, base_id
        return None

    def resolve_property_names(
        self,
        name_texts: list[str],
        scope_code: str,
        *,
        base_id: str = "",
    ) -> dict[str, tuple[str, str]]:
        """Batch resolve property names — stub (shadowed by OntologyBackendMixin)."""
        _ = name_texts, scope_code, base_id
        return {}

    def get_property_aliases(
        self,
        field_code: str,
        scope_code: str,
        *,
        base_id: str = "",
    ) -> list[str]:
        """Get property aliases — stub (shadowed by OntologyBackendMixin)."""
        _ = field_code, scope_code, base_id
        return []

    # ── OntologyBackend: Search & graph (new) ──────────────────────────────

    _ONTOLOGY_TYPE_TO_TERM: dict[str, str] = {
        "object": "object",
        "action": "ontology_action",
        "view": "view",
        "property": "prop",
    }

    def resolve_scope_term_codes(
        self,
        base_id: str,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
    ) -> list[str] | None:
        """Resolve property codes for object/view codes, with existence check.

        Returns a union of object_codes, view_codes, and their resolved property
        codes.  Returns ``None`` when all requested codes are invalid (not found).
        The caller can pass the result to :meth:`search_ontology` as
        ``pre_resolved_term_codes`` to skip repeated resolution in a batch loop.
        """
        store = self._entity_store.sub_store(base_id)
        valid_object_codes: list[str] = []
        if object_code:
            for oc in object_code:
                if store.get("objects", oc) is None:
                    logger.warning(
                        "resolve_scope_term_codes: object_code=%r not found in base_id=%s",
                        oc,
                        base_id,
                    )
                else:
                    valid_object_codes.append(oc)
        valid_view_codes: list[str] = []
        if view_code:
            for vc in view_code:
                if store.get("views", vc) is None:
                    logger.warning(
                        "resolve_scope_term_codes: view_code=%r not found in base_id=%s",
                        vc,
                        base_id,
                    )
                else:
                    valid_view_codes.append(vc)

        if (
            (object_code or view_code)
            and not valid_object_codes
            and not valid_view_codes
        ):
            return None

        resolved: set[str] = set(valid_object_codes) | set(valid_view_codes)
        if valid_object_codes:
            bindings = self.get_object_property_term_bindings(
                valid_object_codes, base_id=base_id
            )
            for b in bindings:
                pc = b.get("propertyCode", "")
                if pc:
                    resolved.add(pc)
        if valid_view_codes:
            bindings = self.get_view_property_term_bindings(
                valid_view_codes, base_id=base_id
            )
            for b in bindings:
                pc = b.get("propertyCode", "")
                if pc:
                    resolved.add(pc)
        return list(resolved) if resolved else None

    # ── Scope resolution helpers ───────────────────────────────────────────

    _REVERSE_TYPE_MAP: dict[str, str] = {
        "object": "object",
        "view": "view",
        "ontology_action": "action",
        "prop": "property",
    }

    def _expand_object_metadata(
        self, object_codes: list[str], base_id: str
    ) -> dict[str, set[str]]:
        """Expand object codes into term-type → term-code groups for metadata scope.

        For each object, collects its own code (object), its properties (prop),
        and its actions (ontology_action).
        """
        store = self._entity_store.sub_store(base_id)
        group: dict[str, set[str]] = {
            "object": set(),
            "prop": set(),
            "ontology_action": set(),
        }
        for code in object_codes:
            obj = store.get("objects", code)
            if obj is None:
                continue
            group["object"].add(code)
            for f in obj.get("fields", []):
                prop_code = f.get("field_code", f.get("fieldCode", "")) or ""
                if prop_code:
                    group["prop"].add(f"o.{code}.{prop_code}")
            for act in obj.get("actions", []):
                act_code = act.get("action_code", act.get("actionCode", "")) or ""
                if act_code:
                    group["ontology_action"].add(act_code)
        return group

    def _expand_view_metadata(
        self, view_codes: list[str], base_id: str
    ) -> dict[str, set[str]]:
        """Expand view codes into term-type → term-code groups for metadata scope.

        Includes the view itself, its own properties, the included objects,
        their properties, and their actions.
        """
        store = self._entity_store.sub_store(base_id)
        group: dict[str, set[str]] = {
            "view": set(),
            "object": set(),
            "prop": set(),
            "ontology_action": set(),
        }
        for code in view_codes:
            view = store.get("views", code)
            if view is None:
                continue
            group["view"].add(code)
            # View's own properties
            for m in view.get("mappings", []):
                prop_code = m.get("property_code", "") or ""
                if prop_code:
                    group["prop"].add(f"v.{code}.{prop_code}")
            # Included objects and their properties/actions
            v_objects = self.get_view_included_objects(code, base_id=base_id)
            for oc in v_objects:
                group["object"].add(oc)
                obj = store.get("objects", oc)
                if obj is None:
                    continue
                for f in obj.get("fields", []):
                    pc = f.get("field_code", f.get("fieldCode", "")) or ""
                    if pc:
                        group["prop"].add(f"o.{oc}.{pc}")
                for act in obj.get("actions", []):
                    act_code = act.get("action_code", act.get("actionCode", "")) or ""
                    if act_code:
                        group["ontology_action"].add(act_code)
        return group

    @staticmethod
    def _union_groups(
        *expansions: dict[str, set[str]],
    ) -> dict[str, set[str]]:
        """Merge multiple expansion results by union-ing term-code sets per term type."""
        result: dict[str, set[str]] = {}
        for exp in expansions:
            for key, values in exp.items():
                if key not in result:
                    result[key] = set()
                result[key] |= values
        return result

    def _apply_metadata_type_filter(
        self,
        group: dict[str, set[str]],
        metadata_type: list[str] | None,
    ) -> dict[str, set[str]]:
        """Filter a term-type → code group to only include requested metadata types.

        Maps metadata_type values through _ONTOLOGY_TYPE_TO_TERM.
        Returns unfiltered group when metadata_type is None or empty.
        """
        if not metadata_type:
            return dict(group)
        allowed_terms = {
            self._ONTOLOGY_TYPE_TO_TERM[t]
            for t in metadata_type
            if t in self._ONTOLOGY_TYPE_TO_TERM
        }
        if not allowed_terms:
            return dict(group)
        return {k: v for k, v in group.items() if k in allowed_terms}

    def resolve_metadata_scope(
        self,
        base_id: str,
        object_code: list[str] | None,
        view_code: list[str] | None,
        property_code: list[str] | None,
        metadata_type: list[str] | None,
    ) -> tuple[set[str] | None, set[str] | None]:
        """Resolve metadata search scope per rules 1-6.

        Returns (term_types, term_codes):
        - term_types: set of term type codes to search, or None for all types.
        - term_codes: set of specific term codes to filter on, or None for all codes.

        Rules:
        1-2: object_code → expand object metadata (property_code ignored).
        3,5: view_code → expand view metadata (property_code ignored).
        4:   object_code + view_code → union of both.
        6:   only property_code or no filters → no code-level restriction.
        """
        _ = property_code  # handled via object/view expansion

        groups: list[dict[str, set[str]]] = []
        if object_code:
            groups.append(self._expand_object_metadata(object_code, base_id))
        if view_code:
            groups.append(self._expand_view_metadata(view_code, base_id))

        if groups:
            combined = self._union_groups(*groups)
            filtered = self._apply_metadata_type_filter(combined, metadata_type)
            term_types: set[str] = set(filtered.keys())
            term_codes: set[str] = set()
            for codes in filtered.values():
                term_codes |= codes
            return (term_types, term_codes if term_codes else None)

        # Rule 6: no object/view code — return type filter only, no code filter
        if metadata_type:
            term_types = {
                self._ONTOLOGY_TYPE_TO_TERM[t]
                for t in metadata_type
                if t in self._ONTOLOGY_TYPE_TO_TERM
            }
            return (term_types if term_types else None, None)
        return (None, None)

    # ── Instance scope helpers (§5.2) ──────────────────────────────────────

    @staticmethod
    def _resolve_property_term_type(field: dict[str, Any]) -> str | None:
        """Extract the instance ``term_type_code`` bound to a property.

        Reads the ``terminology`` or older ``termMeta`` key that is stored on
        every object field / view mapping dict in the EntityStore.

        Returns ``None`` when the property has no terminology binding.
        """
        for key in ("terminology", "termMeta"):
            meta: dict[str, Any] | None = field.get(key)
            if isinstance(meta, dict):
                tc: str | None = meta.get("termTypeCode") or meta.get("term_type_code")
                if tc:
                    return tc
        return None

    def _expand_object_term_types(
        self, object_codes: list[str], base_id: str
    ) -> set[str]:
        """Rule 7: collect instance term_type_codes for all properties of given objects."""
        store = self._entity_store.sub_store(base_id)
        result: set[str] = set()
        for code in object_codes:
            obj = store.get("objects", code)
            if obj is None:
                continue
            for field in obj.get("fields", []):
                tt = self._resolve_property_term_type(field)
                if tt:
                    result.add(tt)
        return result

    def _expand_view_term_types(self, view_codes: list[str], base_id: str) -> set[str]:
        """Rule 8: collect instance term_type_codes for view mappings.

        Two sources:
        - view-owned mappings that reference a source object property
          (trace → source object → sourceColumnCode → term_type_code)
        - view-only mappings (direct term_type_code on the mapping itself).
        """
        store = self._entity_store.sub_store(base_id)
        result: set[str] = set()
        for code in view_codes:
            view = store.get("views", code)
            if view is None:
                continue
            for mapping in view.get("mappings", []):
                src_obj_code = mapping.get("sourceObjectCode") or mapping.get(
                    "source_object_code", ""
                )
                src_col_code = (
                    mapping.get("sourceColumnCode")
                    or mapping.get("sourceColumnCode")
                    or mapping.get("source_object_column_code", "")
                )
                if src_obj_code and src_col_code:
                    # Trace to source object property
                    src_obj = store.get("objects", src_obj_code)
                    if src_obj:
                        for field in src_obj.get("fields", []):
                            fc = field.get("fieldCode") or field.get("field_code", "")
                            if fc == src_col_code:
                                tt = self._resolve_property_term_type(field)
                                if tt:
                                    result.add(tt)
                                break
                else:
                    # View-only property — check mapping itself for terminology
                    tt = self._resolve_property_term_type(mapping)
                    if tt:
                        result.add(tt)
        return result

    def _expand_property_term_types_standalone(
        self, property_codes: list[str], base_id: str
    ) -> set[str]:
        """Rule 10: resolve ``"owner_code.prop_name"`` format.

        Since object and view codes share a namespace, both sides are tried
        and the results are unioned.
        """
        store = self._entity_store.sub_store(base_id)
        result: set[str] = set()
        for pc in property_codes:
            parts = pc.split(".", 1)
            if len(parts) != 2:
                continue
            owner, prop_name = parts[0], parts[1]

            # 1. Try as object
            obj = store.get("objects", owner)
            if obj:
                for field in obj.get("fields", []):
                    fc = field.get("fieldCode") or field.get("field_code", "")
                    fn = field.get("fieldName") or field.get("field_name", "")
                    if fc == prop_name or fn == prop_name:
                        tt = self._resolve_property_term_type(field)
                        if tt:
                            result.add(tt)

            # 2. Try as view
            view = store.get("views", owner)
            if view:
                for mapping in view.get("mappings", []):
                    mc = mapping.get("propertyCode") or mapping.get("property_code", "")
                    mn = mapping.get("propertyName") or mapping.get("property_name", "")
                    if mc == prop_name or mn == prop_name:
                        src_obj_code = mapping.get("sourceObjectCode") or mapping.get(
                            "source_object_code", ""
                        )
                        if src_obj_code:
                            # View property references a source object property
                            src_col = (
                                mapping.get("sourceColumnCode")
                                or mapping.get("sourceColumnCode")
                                or mapping.get("source_object_column_code", "")
                            )
                            src_obj = store.get("objects", src_obj_code)
                            if src_obj and src_col:
                                for field in src_obj.get("fields", []):
                                    fc = field.get("fieldCode") or field.get(
                                        "field_code", ""
                                    )
                                    if fc == src_col:
                                        tt = self._resolve_property_term_type(field)
                                        if tt:
                                            result.add(tt)
                                        break
                        else:
                            # View-only property
                            tt = self._resolve_property_term_type(mapping)
                            if tt:
                                result.add(tt)
        return result

    def resolve_instance_scope(
        self,
        base_id: str,
        object_code: list[str] | None,
        view_code: list[str] | None,
        property_code: list[str] | None,
    ) -> list[str] | None:
        """Resolve instance term type codes per rules 7-10 (§5.3).

        Returns a sorted list of instance term_type_codes, or None for no filter.

        Rules:
        7:  object_code → expand per-object property term types.
        8:  view_code   → expand per-view mapping term types (unioned with rule 7).
        9:  property_code ignored when object_code or view_code present.
        10: property_code standalone → resolve "owner_code.prop_name" format.
        Fallback: when no filters at all, return all instance type codes (global).
        """
        tt_sets: list[set[str]] = []

        if object_code:
            tt_sets.append(self._expand_object_term_types(object_code, base_id))
        if view_code:
            tt_sets.append(self._expand_view_term_types(view_code, base_id))
        if property_code and not object_code and not view_code:
            tt_sets.append(
                self._expand_property_term_types_standalone(property_code, base_id)
            )

        if not tt_sets:
            # No filter — global fallback (§5.3 line 461-464)
            return self._resolve_global_instance_types(base_id)

        # Union per-entity expansions
        result: set[str] = set()
        for s in tt_sets:
            result |= s

        # P0 fallback: when entity store fields lack ``terminology.termTypeCode``
        # (not yet populated from OWL import), the per-entity expansion yields
        # nothing.  Fall back to global instance types instead of returning None.
        if not result:
            return self._resolve_global_instance_types(base_id)

        return sorted(result)

    def _resolve_global_instance_types(self, base_id: str) -> list[str] | None:
        """P0 global fallback: all instance term types from the knowledge DB.

        TODO: use proper instance type_category once the DB schema is
        finalised; 0 is a placeholder that currently reaches the right
        internal branch.
        """
        reader = self._get_knowledge_reader()
        try:
            page = reader.list_term_types(
                library_id=base_id, type_category=0, page_size=500
            )
            type_codes = sorted(
                t.get("typeCode", t.get("type_code", "")) for t in page.get("data", [])
            )
            type_codes = [tc for tc in type_codes if tc]
            return type_codes if type_codes else None
        except Exception:
            logger.exception("Failed to get instance type codes")
        return None

    def resolve_search_scope(
        self,
        base_id: str,
        search_scope: str,
        object_code: list[str] | None,
        view_code: list[str] | None,
        property_code: list[str] | None,
        metadata_type: list[str] | None,
    ) -> dict[str, Any]:
        """Combine metadata and instance scope resolution into a single dict.

        Returns:
            {
                "metadata_term_types": set|None,
                "metadata_term_codes": set|None,
                "instance_term_types": list|None,
            }
        """
        result: dict[str, Any] = {
            "metadata_term_types": None,
            "metadata_term_codes": None,
            "instance_term_types": None,
        }

        if search_scope in ("metadata", "all"):
            md_types, md_codes = self.resolve_metadata_scope(
                base_id,
                object_code,
                view_code,
                property_code,
                metadata_type,
            )
            result["metadata_term_types"] = md_types
            result["metadata_term_codes"] = md_codes

        if search_scope in ("instance", "all"):
            result["instance_term_types"] = self.resolve_instance_scope(
                base_id,
                object_code,
                view_code,
                property_code,
            )

        return result

    _ref_props_index: dict[str, dict[str, list[dict[str, str]]]] | None = None

    def _build_ref_props_index_sql(
        self, engine: Any, base_id: str
    ) -> dict[str, list[dict[str, str]]]:
        """Build reverse index from ``ontology_object_fields`` (fast path) or
        fall back to CTE on ``ontology_objects`` JSONB (slow path).

        The fast path uses a dedicated table populated by the backfill script
        (``db/scripts/backfill_ontology_object_fields.py``).  The slow path
        exists for environments where the table hasn't been created yet.
        """
        from sqlalchemy import text
        from sqlalchemy.orm import Session

        _md_codes = frozenset(self._ONTOLOGY_TYPE_TO_TERM.values())
        index: dict[str, list[dict[str, str]]] = {}

        with Session(engine) as session:
            try:
                result = session.execute(
                    text("""
                        SELECT
                            f.term_type_code,
                            f.object_code,
                            COALESCE(o.object_name, '') AS object_name,
                            f.field_code,
                            f.field_name
                        FROM ontology_object_fields f
                        JOIN ontology_objects o
                          ON o.base_id = f.base_id
                         AND o.object_code = f.object_code
                        WHERE f.base_id = :bid
                          AND f.term_type_code IS NOT NULL
                    """),
                    {"bid": base_id},
                )
            except Exception:
                # Fallback: table doesn't exist → use slow JSONB CTE
                logger.info(
                    "ontology_object_fields not available, falling back to JSONB CTE"
                )
                result = session.execute(
                    text("""
                        WITH expanded AS (
                            SELECT
                                jsonb_array_elements(data -> 'fields') AS field,
                                object_code,
                                object_name
                            FROM ontology_objects
                            WHERE base_id = :bid
                        )
                        SELECT
                            COALESCE(
                                jsonb_extract_path_text(field, 'termMeta', 'termTypeCode'),
                                jsonb_extract_path_text(field, 'terminology', 'termTypeCode')
                            ) AS tt_code,
                            object_code,
                            COALESCE(object_name, '') AS object_name,
                            jsonb_extract_path_text(field, 'field_code') AS field_code,
                            jsonb_extract_path_text(field, 'field_name') AS field_name
                        FROM expanded
                        WHERE COALESCE(
                            jsonb_extract_path_text(field, 'termMeta', 'termTypeCode'),
                            jsonb_extract_path_text(field, 'terminology', 'termTypeCode')
                        ) IS NOT NULL
                    """),
                    {"bid": base_id},
                )

            for row in result:
                tt: str = row[0] or ""
                oc: str = row[1] or ""
                on: str = row[2] or ""
                fc: str = row[3] or ""
                fn: str = row[4] or ""
                if tt in _md_codes:
                    continue
                index.setdefault(tt, []).append(
                    {
                        "objectCode": oc,
                        "objectName": on,
                        "propertyCode": fc,
                        "propertyName": fn,
                    }
                )

        return index

    def _build_ref_props_index_from_store(
        self, store: Any, base_id: str
    ) -> dict[str, list[dict[str, str]]]:
        """Build reverse index by iterating the entity store (JSON / generic path)."""
        _md_codes: frozenset[str] = frozenset(self._ONTOLOGY_TYPE_TO_TERM.values())
        index: dict[str, list[dict[str, str]]] = {}
        page = 1
        page_size = 1000
        while True:
            items, total = store.search("objects", page=page, page_size=page_size)
            for obj in items:
                obj_code = obj.get("object_code", obj.get("objectCode", "")) or ""
                obj_name = obj.get("object_name", obj.get("objectName", "")) or ""
                for f in obj.get("fields", []):
                    tt = self._resolve_property_term_type(f)
                    if tt is None or tt in _md_codes:
                        continue
                    pc = f.get("field_code", f.get("fieldCode", "")) or ""
                    pn = f.get("field_name", f.get("fieldName", "")) or ""
                    index.setdefault(tt, []).append(
                        {
                            "objectCode": obj_code,
                            "objectName": obj_name,
                            "propertyCode": pc,
                            "propertyName": pn,
                        }
                    )
            if page * page_size >= total:
                break
            page += 1
        return index

    def _resolve_referenced_properties(
        self, base_id: str, term_type_code: str, scope_codes: set[str] | None = None
    ) -> list[dict[str, str]]:
        """Return the list of object properties that reference *term_type_code*.

        Builds a reverse index (``term_type_code → [{objectCode, ...}, ...]``)
        from all objects in the entity store on first call and caches it per
        *base_id*.  When *scope_codes* is provided, only object codes in that
        set are returned.

        Uses raw SQL CTE when the underlying store is OpenGauss; falls back
        to Python iteration for JsonEntityStore.
        """
        _md_codes: frozenset[str] = frozenset(self._ONTOLOGY_TYPE_TO_TERM.values())
        if term_type_code in _md_codes:
            return []

        # Lazy-init the reverse index for this base_id
        if self._ref_props_index is None:
            self._ref_props_index = {}
        _index_container = self._ref_props_index

        if base_id not in _index_container:
            store = self._entity_store.sub_store(base_id)
            # Unwrap _ScopedEntityStore to reach OpenGaussEntityStore or JsonEntityStore
            parent = store._parent if hasattr(store, "_parent") else store
            if hasattr(parent, "_engine"):
                _index_container[base_id] = self._build_ref_props_index_sql(
                    parent._engine, base_id
                )
            else:
                _index_container[base_id] = self._build_ref_props_index_from_store(
                    store, base_id
                )

        items = _index_container[base_id].get(term_type_code, [])
        if scope_codes:
            items = [r for r in items if r.get("objectCode", "") in scope_codes]
        return items

    # ── Result helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _try_int(value: object) -> int:
        """Safely parse an int; returns 0 on failure."""
        try:
            return int(str(value))
        except (ValueError, TypeError):
            return 0

    def _resolve_scene_id(
        self, term_code: str, term_type: str, scene_ids: list[str]
    ) -> str:
        """Resolve a term to its scene ID.

        Uses the explicit scene_ids list when available, otherwise falls
        back to _object_scene_map / _view_scene_map.
        """
        if scene_ids and scene_ids != ["-1"]:
            return scene_ids[0]
        if term_type == "object":
            for scene_id, objects in self._object_scene_map.items():
                if term_code in objects:
                    return scene_id
        elif term_type == "view":
            for scene_id, views in self._view_scene_map.items():
                if term_code in views:
                    return scene_id
        return ""

    @staticmethod
    def _resolve_result_type(term_type: str) -> str:
        """Map internal term_type_code to user-facing resultType string."""
        return OntologyMetadataMixin._REVERSE_TYPE_MAP.get(term_type, term_type)

    @staticmethod
    def _truncate_per_type(
        hits: list[dict[str, Any]], result_per_type: int
    ) -> list[dict[str, Any]]:
        """Truncate hits to at most *result_per_type* per resultType, sorted by score desc.

        Deduplicates by ``termCode`` (bare ``opp_code`` and prefixed
        ``o.by_opportunity.opp_code`` may both match the same property during
        the §2.4 migration window — keep the highest-scoring occurrence).
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        seen: set[str] = set()
        for h in hits:
            tc = h.get("termCode", "")
            if tc in seen:
                continue
            seen.add(tc)
            rt = h.get("resultType", "")
            grouped.setdefault(rt, []).append(h)

        result: list[dict[str, Any]] = []
        for _rt, items in grouped.items():
            items.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
            result.extend(items[:result_per_type])
        result.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
        return result

    def _enrich_metadata_hits(
        self,
        base_id: str,
        hits: list[dict[str, Any]],
        scene_ids: list[str],
        *,
        action_map: dict[str, dict[str, str]] | None = None,
        object_map: dict[str, dict[str, Any]] | None = None,
        view_map: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Enrich metadata search hits with pre-loaded entity data.

        All entity lookups come from the pre-built *action_map*, *object_map*,
        and *view_map* dicts, which the caller is expected to populate via
        targeted ``store.search(..., codes=[...])`` queries.  When a map is
        ``None``, falls back to individual ``store.get()`` calls (backward
        compatibility for callers that don't pre-load).

        Args:
            base_id: Base identifier.
            hits: Raw metadata search hits from search engine.
            scene_ids: Scene IDs for context resolution.
            action_map: Pre-built dict of action_code → {actionName, actionDesc, belongObjectCode}.
            object_map: Pre-built dict of object_code → full object data dict.
            view_map: Pre-built dict of view_code → full view data dict.
        """
        store = self._entity_store.sub_store(base_id)
        enriched: list[dict[str, Any]] = []

        # Backward-compat: load actions if hits contain action types but no map
        _actions: list[dict[str, Any]] | None = None
        if action_map is None and any(
            str(h.get("term_type_code", "")) == "ontology_action" for h in hits
        ):
            _actions = store.list_all("actions")

        for hit in hits:
            term_code = str(hit.get("term_code", ""))
            term_type = str(hit.get("term_type_code", ""))
            score = round(float(hit["score"]), 4)
            result_type = self._resolve_result_type(term_type)

            entry: dict[str, Any] = {
                "sceneId": self._resolve_scene_id(term_code, term_type, scene_ids),
                "resultType": result_type,
                "matchedField": "name",
                "score": score,
                "termCode": term_code,
            }

            if term_type == "object":
                obj = _map_get_or_fetch(object_map, store, "objects", term_code)
                if obj:
                    entry["objectCode"] = term_code
                    entry["objectName"] = obj.get(
                        "object_name", obj.get("objectName", "")
                    )
                    entry["objectDesc"] = (
                        obj.get(
                            "object_desc",
                            obj.get("objectDesc", obj.get("description", "")),
                        )
                        or ""
                    )
                    entry["objectSource"] = (
                        obj.get("object_source", obj.get("objectSource", "")) or ""
                    )

            elif term_type == "view":
                view = _map_get_or_fetch(view_map, store, "views", term_code)
                if view:
                    entry["viewCode"] = term_code
                    entry["viewName"] = view.get("view_name", view.get("viewName", ""))
                    entry["description"] = view.get("description", "") or ""

            elif term_type == "ontology_action":
                entry["actionCode"] = term_code
                entry["belongObjectCode"] = ""
                if action_map is not None:
                    act_info = action_map.get(term_code)
                    if act_info is not None:
                        entry["actionName"] = act_info.get("actionName", "")
                        entry["actionDesc"] = act_info.get("actionDesc", "")
                        entry["belongObjectCode"] = act_info.get("belongObjectCode", "")
                elif _actions is not None:
                    for act in _actions:
                        ac = act.get("action_code", act.get("actionCode", ""))
                        if ac == term_code:
                            entry["actionName"] = act.get(
                                "action_name", act.get("actionName", "")
                            )
                            entry["actionDesc"] = (
                                act.get(
                                    "action_desc",
                                    act.get("actionDesc", act.get("description", "")),
                                )
                                or ""
                            )
                            entry["belongObjectCode"] = (
                                act.get(
                                    "belong_object_code",
                                    act.get("belongObjectCode", ""),
                                )
                                or ""
                            )
                            break

            elif term_type == "prop":
                entry["propertyCode"] = term_code
                parts = term_code.split(".", 2)
                if len(parts) >= 3 and parts[0] == "o":
                    owner = parts[1]
                    obj = _map_get_or_fetch(object_map, store, "objects", owner)
                    if obj:
                        entry["objectCode"] = owner
                        entry["objectName"] = obj.get(
                            "object_name", obj.get("objectName", "")
                        )
                        for f in obj.get("fields", []):
                            fc = f.get("field_code", f.get("fieldCode", ""))
                            if fc == parts[2]:
                                entry["propertyName"] = f.get(
                                    "field_name", f.get("fieldName", "")
                                )
                                break
                elif len(parts) >= 3 and parts[0] == "v":
                    owner = parts[1]
                    view = _map_get_or_fetch(view_map, store, "views", owner)
                    if view:
                        entry["viewCode"] = owner
                        entry["viewName"] = view.get(
                            "view_name", view.get("viewName", "")
                        )
                        for m in view.get("mappings", []):
                            mc = m.get("property_code", m.get("propertyCode", ""))
                            if mc == parts[2]:
                                entry["propertyName"] = m.get(
                                    "property_name", m.get("propertyName", "")
                                )
                                break

            enriched.append(entry)

        return enriched

    def _is_metadata_entity(
        self,
        base_id: str,
        term_code: str,
        term_type_code: str,
        *,
        action_code_set: frozenset[str] | None = None,
    ) -> bool:
        """Check whether a (term_code, term_type_code) pair is a known metadata entity.

        Used to post-filter instance search results.  Instance terms may share
        ``term_type_code`` with metadata types (e.g. ``"object"`` appears in both
        metadata and instance categories), so we must exclude hits whose
        ``term_code`` corresponds to a metadata entity stored in the EntityStore.

        Args:
            base_id: Base identifier.
            term_code: Term code from search result.
            term_type_code: Term type code from search result.
            action_code_set: Pre-built set of action codes. When provided,
                avoids repeated ``list_all("actions")`` calls.
        """
        if term_type_code not in frozenset(self._ONTOLOGY_TYPE_TO_TERM.values()):
            return False

        store = self._entity_store.sub_store(base_id)

        if term_type_code == "object":
            return store.get("objects", term_code) is not None

        if term_type_code == "view":
            return store.get("views", term_code) is not None

        if term_type_code == "ontology_action":
            if action_code_set is not None:
                return term_code in action_code_set
            for act in store.list_all("actions"):
                if act.get("action_code", act.get("actionCode", "")) == term_code:
                    return True
            return False

        # "prop": structured codes (o.owner.pc / v.owner.pc) are metadata if
        # the owner entity exists in the store.  Bare prop_codes are instance-level.
        if term_type_code == "prop":
            parts = term_code.split(".", 2)
            if len(parts) >= 3:
                prefix, owner, _pc = parts[0], parts[1], parts[2]
                if prefix == "o":
                    return store.get("objects", owner) is not None
                if prefix == "v":
                    return store.get("views", owner) is not None
            return False

        return False  # unreachable: all _ONTOLOGY_TYPE_TO_TERM values covered above

    # ── search_ontology (rewritten) ────────────────────────────────────────

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
        """Unified vector search across metadata and instance terms, batched by keyword.

        Supports both single-keyword (str) and multi-keyword (list[str]) queries.
        Returns results grouped by keyword with EntityStore enrichment for metadata hits.

        Performance optimizations:
        - Batch embedding via ``get_text_embedding_batch`` (single API call).
        - UNION ALL batch DB search via ``search_terms_by_embedding_batch`` (single SQL).
        - Pre-loaded action code set avoids repeated ``list_all("actions")`` calls.

        Args:
            base_id: Base / project identifier.
            scene_ids: Scene IDs for context resolution (use ["-1"] for cross-scene).
            keyword: Single keyword string or list of keyword strings.
            query_type: Always "vector" in current implementation.
            search_scope: "metadata", "instance", or "all".
            metadata_type: Metadata type filter (object, view, action, property, dimension).
            object_code: Object codes for scope resolution.
            view_code: View codes for scope resolution.
            property_code: Property codes for scope resolution.
            result_per_type: Maximum hits per result type after enrichment.
            top_k: Maximum raw hits per keyword per search scope.

        Returns:
            Dict keyed by keyword string, each containing metadata/instances/totalCount.
        """
        _ = base_id, query_type

        # Backward compat: accept old `limit` kwarg as fallback for `top_k`.
        effective_top_k: int = kwargs.get("limit", top_k)

        keywords: list[str] = [keyword] if isinstance(keyword, str) else list(keyword)
        keywords = [k for k in keywords if k and k.strip()]
        if not keywords:
            return {}

        scope = self.resolve_search_scope(
            base_id,
            search_scope,
            object_code,
            view_code,
            property_code,
            metadata_type,
        )

        _ALL_MD_TYPES = list(self._ONTOLOGY_TYPE_TO_TERM.values())
        md_types: set[str] | None = scope["metadata_term_types"]
        md_codes: set[str] | None = scope["metadata_term_codes"]
        inst_types: list[str] | None = scope["instance_term_types"]

        # Compute scope object codes for referencedByProperties filtering
        _scope_obj_codes: set[str] | None = None
        if object_code or view_code:
            _scope_obj_codes = set(object_code or [])
            if view_code:
                for vc in view_code:
                    _scope_obj_codes.update(
                        self.get_view_included_objects(vc, base_id=base_id)
                    )

        svc = self._get_embedding()
        engine = self._get_search_engine()

        # ── Batch embedding (single API call) ──
        vectors = svc.get_text_embedding_batch(keywords)

        # ── Pre-compute effective types ──
        effective_md_types: list[str] = (
            list(md_types) if md_types is not None else _ALL_MD_TYPES
        )
        effective_md_codes: list[str] | None = (
            list(md_codes) if md_codes is not None else None
        )

        # ── UNION ALL batch search (single SQL) ──
        # Each keyword gets 2 subqueries (metadata + instance), each with own LIMIT.
        # Results keyed by "{idx}_md" / "{idx}_inst".
        batch_kwargs: dict[str, Any] = {
            "vectors": vectors,
            "per_keyword_limit": effective_top_k,
        }
        if search_scope in ("metadata", "all"):
            batch_kwargs["metadata_term_types"] = effective_md_types
            batch_kwargs["metadata_term_codes"] = effective_md_codes
        if search_scope in ("instance", "all") and inst_types:
            batch_kwargs["instance_term_types"] = inst_types

        raw_grouped: dict[str, list[dict[str, Any]]] = (
            engine.search_terms_by_embedding_batch(**batch_kwargs)
        )

        # ── Collect needed entity codes from ALL metadata hits ──
        # Then query object/view/action in bulk (3 SQL queries max), pass
        # pre-built dicts to _enrich_metadata_hits — zero per-hit store.get().
        _needed_action_codes: set[str] = set()
        _needed_object_codes: set[str] = set()
        _needed_view_codes: set[str] = set()

        for key, hits in raw_grouped.items():
            is_md = key.endswith("_md")
            for h in hits:
                tt = str(h.get("term_type_code", ""))
                tc = str(h.get("term_code", ""))
                if tt == "ontology_action":
                    if is_md:
                        _needed_action_codes.add(tc)
                    else:
                        _needed_action_codes.add(tc)
                elif tt == "object":
                    _needed_object_codes.add(tc)
                elif tt == "view":
                    _needed_view_codes.add(tc)
                elif tt == "prop" and is_md:
                    parts = tc.split(".", 2)
                    if len(parts) >= 3:
                        if parts[0] == "o":
                            _needed_object_codes.add(parts[1])
                        elif parts[0] == "v":
                            _needed_view_codes.add(parts[1])

        _action_map: dict[str, dict[str, str]] = {}
        _action_code_set: frozenset[str] = frozenset()
        _object_map: dict[str, dict[str, Any]] = {}
        _view_map: dict[str, dict[str, Any]] = {}

        store = self._entity_store.sub_store(base_id)

        if _needed_action_codes:
            action_page = store.search(
                "actions",
                base_id=base_id,
                codes=list(_needed_action_codes),
                page_size=500,
            )
            for act in action_page[0]:
                ac = act.get("action_code", act.get("actionCode", ""))
                if ac:
                    _action_map[ac] = {
                        "actionName": act.get("action_name", act.get("actionName", "")),
                        "actionDesc": (
                            act.get(
                                "action_desc",
                                act.get("actionDesc", act.get("description", "")),
                            )
                            or ""
                        ),
                        "belongObjectCode": (
                            act.get(
                                "belong_object_code", act.get("belongObjectCode", "")
                            )
                            or ""
                        ),
                    }
            _action_code_set = frozenset(_action_map.keys())

        if _needed_object_codes:
            obj_page = store.search(
                "objects",
                base_id=base_id,
                codes=list(_needed_object_codes),
                page_size=500,
            )
            for obj in obj_page[0]:
                oc = obj.get("object_code", obj.get("objectCode", ""))
                if oc:
                    _object_map[oc] = obj

        if _needed_view_codes:
            view_page = store.search(
                "views", base_id=base_id, codes=list(_needed_view_codes), page_size=500
            )
            for view in view_page[0]:
                vc = view.get(
                    "view_code", view.get("viewCode", view.get("view_id", ""))
                )
                if vc:
                    _view_map[vc] = view

        # ── Enrich and construct results per keyword ──
        # Per-call caching in _enrich_metadata_hits eliminates repeated disk
        # I/O for the same entity, so sequential processing is fast enough.
        # Group raw results by keyword index
        kw_raw: dict[int, dict[str, list[dict[str, Any]]]] = {}
        for key, hits in raw_grouped.items():
            # key format: "{idx}_md" or "{idx}_inst"
            parts = key.rsplit("_", 1)
            idx = int(parts[0])
            scope_tag = parts[1]  # "md" or "inst"
            if idx not in kw_raw:
                kw_raw[idx] = {}
            kw_raw[idx][scope_tag] = hits

        result: dict[str, Any] = {}
        for idx in range(len(keywords)):
            kw = keywords[idx]
            scopes = kw_raw.get(idx, {})

            kw_result: dict[str, Any] = {
                "metadata": [],
                "instances": [],
                "totalCount": {"metadata": 0, "instances": 0},
            }

            # ── Metadata enrichment ──
            md_hits = scopes.get("md", [])
            if md_hits:
                enriched = self._enrich_metadata_hits(
                    base_id,
                    md_hits,
                    scene_ids,
                    action_map=_action_map,
                    object_map=_object_map,
                    view_map=_view_map,
                )
                kw_result["metadata"] = self._truncate_per_type(
                    enriched, result_per_type
                )
                kw_result["totalCount"]["metadata"] = len(kw_result["metadata"])

            # ── Instance construction ──
            inst_hits = scopes.get("inst", [])
            if inst_hits:
                kw_result["instances"] = [
                    {
                        "sceneId": self._resolve_scene_id(
                            str(h["term_code"]), str(h["term_type_code"]), scene_ids
                        ),
                        "objectCode": "",
                        "objectName": "",
                        "primaryKey": self._try_int(h.get("term_code", "0")),
                        "matchedProperty": str(h["term_type_code"]),
                        "matchedValue": str(h.get("name_text", h.get("term_name", ""))),
                        "isEnumType": False,
                        "referencedByProperties": self._resolve_referenced_properties(
                            base_id, str(h["term_type_code"]), _scope_obj_codes
                        ),
                        "score": round(float(h["score"]), 4),
                        "properties": {},
                    }
                    for h in inst_hits
                    if not self._is_metadata_entity(
                        base_id,
                        str(h.get("term_code", "")),
                        str(h["term_type_code"]),
                        action_code_set=_action_code_set,
                    )
                ]
                kw_result["totalCount"]["instances"] = len(kw_result["instances"])

            result[kw] = kw_result

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

    async def search_object_instances_unstructured(
        self,
        *,
        base_id: str,
        object_codes: list[str] | None = None,
        query: str | None = None,
        queries: list[str] | None = None,
        top_k: int = 20,
        enable_chunk_recall: bool = True,
    ) -> Any:  # ObjectInstanceSearchResult
        """非结构化对象实例检索 — 双路召回 + RRF(k=60) 融合。

        sentence 模式 (query)：jieba 分词 → RRF 融合 → results[query] = [...]
        word_batch 模式 (queries)：每个词独立检索 → asyncio.gather 并发 chunk
        """
        from datacloud_platform.models.shared import ObjectInstanceSearchResult

        input_mode, keywords = _resolve_input_mode(query, queries)
        if not keywords:
            return ObjectInstanceSearchResult(results={})

        # Empty object_codes → no results
        if object_codes is not None and not object_codes:
            return ObjectInstanceSearchResult(results={})

        _run_p2 = _should_run_path2(enable_chunk_recall)

        # ── Collect ByClaw resource IDs for path 2 ─
        kb_ids: dict[str, dict[str, Any]] = {}
        if _run_p2 and object_codes is not None:
            kb_ids = self._collect_kb_ids(base_id, object_codes)

        if input_mode == "sentence":
            # ── sentence: jieba 分词 → multi-token term search → RRF ─
            tokens = _hybrid_tokenize(keywords[0])
            if not tokens:
                return ObjectInstanceSearchResult(results={})

            path1 = self._do_path1(object_codes, tokens, top_k)
            path2 = await self._do_path2(
                kb_ids,
                keywords[0],
                top_k,
            )
            hits = _fuse_path_results_rrf(path1, path2, k=60, top_k=top_k)
            return ObjectInstanceSearchResult(results={keywords[0]: list(hits)})

        # ── word_batch: 一次 batch + 并发 chunk ────
        results: dict[str, list[Any]] = {}

        # 路1：一次 batch 调用，按 keyword 分组返回
        all_path1 = self._do_path1_batched(object_codes, keywords, top_k)

        # 路2：asyncio.gather 并发
        path2_futures: dict[str, list[dict[str, Any]]] = {}
        if kb_ids:
            import asyncio

            async def _p2_for_word(w: str) -> tuple[str, list[dict[str, Any]]]:
                p2 = await self._do_path2(kb_ids, w, top_k)
                return w, p2

            chunk_tasks = [_p2_for_word(w) for w in keywords]
            chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
            for item in chunk_results:
                if isinstance(item, Exception):
                    logger.warning("word_batch chunk search failed: %s", item)
                elif isinstance(item, tuple):
                    path2_futures[item[0]] = item[1]

        for word in keywords:
            path1 = all_path1.get(word, [])
            path2 = path2_futures.get(word, [])
            hits = _fuse_path_results_rrf(path1, path2, k=60, top_k=top_k)
            results[word] = list(hits)

        return ObjectInstanceSearchResult(results=results)

    # ── Unified path helpers ──────────────────────────────────────────────

    def _do_path1(
        self,
        object_codes: list[str] | None,
        tokens: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """路1 术语实例检索：多类型原生 IN 过滤。"""
        if object_codes is not None:
            return self._path1_scoped_term_search(
                object_codes=object_codes,
                tokens=tokens,
                top_k=top_k,
            )
        return self._path1_global_term_instance_search(tokens=tokens, top_k=top_k)

    async def _do_path2(
        self,
        kb_info: dict[str, dict[str, Any]],
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """路2 KB chunk 搜索：并发搜索所有 kb_resource_id 并按收集顺序合并。

        每个 KB 一个协程任务，asyncio.gather 保序合并；
        单 KB 失败记 warning 并降级为空列表，不影响其他 KB。
        """
        if not kb_info:
            return []
        logger.info(
            "_do_path2: kb_ids=%s query=%s top_k=%s", list(kb_info.keys()), query, top_k
        )

        async def _search_one(
            kb_resource_id: str, info: dict[str, Any]
        ) -> list[dict[str, Any]]:
            """单个 KB 的 chunk 搜索，失败降级为空列表。"""
            try:
                chunk_hits = await self._do_chunk_search(
                    query=query,
                    kb_resource_id=kb_resource_id,
                    top_k=top_k,
                    kb_directory=info.get("kb_directory"),
                    term_type_codes=info.get("object_codes"),
                )
                logger.warning(
                    "_do_path2: kb_resource_id=%s → %d chunk hits",
                    kb_resource_id,
                    len(chunk_hits),
                )
                return chunk_hits
            except Exception:
                logger.warning(
                    "_do_path2: chunk search failed for kb_resource_id=%s",
                    kb_resource_id,
                    exc_info=True,
                )
                return []

        chunk_lists = await asyncio.gather(
            *(_search_one(kid, info) for kid, info in kb_info.items())
        )

        all_results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for chunk_hits in chunk_lists:
            for hit in chunk_hits:
                tid = hit.get("term_id", "")
                if tid and tid not in seen:
                    seen.add(tid)
                    all_results.append(hit)
        return all_results

    # ── kb_ids collector ────────────────────────────────────────────────

    def _collect_kb_ids(
        self,
        base_id: str,
        object_codes: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Collect kb_resource_id → scope information for ByClaw search."""
        result: dict[str, dict[str, Any]] = {}
        store = self._entity_store.sub_store(base_id)
        for oc in object_codes:
            try:
                obj = store.get("objects", oc)
            except Exception:
                logger.debug("_collect_kb_ids: store.get('objects', %s) failed", oc)
                continue
            if obj:
                ext = obj.get("ext_property", obj.get("extProperty", {}))
                if isinstance(ext, dict):
                    kb_resource_id = ext.get("kb_resource_id")
                    if kb_resource_id:
                        kid = str(kb_resource_id)
                        kb_directory = ext.get("kb_directory")
                        if kid in result:
                            if oc not in result[kid]["object_codes"]:
                                result[kid]["object_codes"].append(oc)
                        else:
                            result[kid] = {
                                "kb_directory": kb_directory
                                if isinstance(kb_directory, str)
                                else None,
                                "object_codes": [oc],
                            }
        return result

    # ── Path 1 helpers ──────────────────────────────────────────────────

    def _path1_scoped_term_search(
        self,
        *,
        object_codes: list[str],
        tokens: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """路1 多类型术语实例检索：使用 search_terms_batch 原生 IN 过滤。"""
        batch_method = getattr(self, "search_terms_batch", None)
        if not callable(batch_method):
            return self._path1_scoped_fallback(object_codes, tokens, top_k)

        try:
            batch = batch_method(
                keywords=tokens,
                term_type_codes=object_codes,
                top_k=top_k,
            )
        except Exception:
            logger.warning("_path1_scoped: search_terms_batch failed", exc_info=True)
            return self._path1_scoped_fallback(object_codes, tokens, top_k)

        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        if isinstance(batch, dict):
            for kw, qr in batch.items():
                items = _extract_items(qr)
                for item in items:
                    tid = _attr(item, "term_id", "")
                    if tid and tid not in seen:
                        seen.add(tid)
                        results.append(_make_path1_hit(item))
        return results

    def _path1_scoped_fallback(
        self,
        object_codes: list[str],
        tokens: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """降级：逐类型逐 token 调用 search_terms 再合并。"""
        reader = self._get_knowledge_reader()
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for oc in object_codes:
            for token in tokens:
                try:
                    raw = reader.search_terms(
                        term_type_code=oc, keyword=token, limit=top_k
                    )
                except Exception:
                    continue
                for item in _extract_items(raw):
                    tid = _attr(item, "term_id", "")
                    if tid and tid not in seen:
                        seen.add(tid)
                        results.append(_make_path1_hit(item))
        return results

    def _path1_term_instance_search(
        self,
        *,
        object_code: str,
        query: str,
        tokens: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """路1 单类型术语实例检索。

        对每个 token 调用 search_terms(term_type_code=object_code, keyword=token)，
        收集所有结果并去重。
        """
        reader = self._get_knowledge_reader()
        seen: set[str] = set()
        results: list[dict[str, Any]] = []

        for token in tokens:
            try:
                raw = reader.search_terms(
                    term_type_code=object_code,
                    keyword=token,
                    limit=top_k,
                )
            except Exception:
                logger.warning(
                    "_path1: search_terms failed for type=%s kw=%s",
                    object_code,
                    token,
                    exc_info=True,
                )
                continue

            items = _extract_items(raw)
            for item in items:
                tid = _attr(item, "term_id", "")
                if tid and tid not in seen:
                    seen.add(tid)
                    results.append(_make_path1_hit(item))

        return results

    def _path1_global_term_instance_search(
        self,
        *,
        tokens: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """路1 跨全类型批量术语检索。

        使用 self.search_terms_batch（TermBackendMixin 混入到同一
        DataCloudDataBackend 实例）做 UNION ALL 批量全类型检索。
        """
        # self.search_terms_batch 来自 TermBackendMixin，与 OntologyMetadataMixin
        # 同在一个 DataCloudDataBackend 实例中（_composite.py）
        batch_method = getattr(self, "search_terms_batch", None)
        if callable(batch_method):
            try:
                batch = batch_method(
                    keywords=tokens,
                    term_type_codes=None,
                    top_k=top_k,
                )
            except Exception:
                logger.warning(
                    "_path1_global: search_terms_batch failed", exc_info=True
                )
                return self._path1_global_fallback(tokens, top_k)

            seen: set[str] = set()
            results: list[dict[str, Any]] = []
            if isinstance(batch, dict):
                for kw, qr in batch.items():
                    items = _extract_items(qr)
                    for item in items:
                        tid = _attr(item, "term_id", "")
                        if tid and tid not in seen:
                            seen.add(tid)
                            results.append(_make_path1_hit(item))
            return results

        # 降级：逐 token，不带 term_type 过滤
        logger.info(
            "_path1_global: search_terms_batch unavailable, falling back to per-token"
        )
        return self._path1_global_fallback(tokens, top_k)

    def _path1_global_fallback(
        self,
        tokens: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """降级：对所有类型逐 token 调用 search_terms。"""
        reader = self._get_knowledge_reader()
        seen: set[str] = set()
        results: list[dict[str, Any]] = []

        for token in tokens:
            try:
                raw = reader.search_terms(
                    term_type_code="*",  # wildcard to trigger full-text match
                    keyword=token,
                    limit=top_k,
                )
            except Exception:
                # 空 term_type_code 也可能失败，跳过
                continue

            items = _extract_items(raw)
            for item in items:
                tid = _attr(item, "term_id", "")
                if tid and tid not in seen:
                    seen.add(tid)
                    results.append(_make_path1_hit(item))

        return results

    # ── Path 1 batched helpers ──────────────────────────────────────────

    def _do_path1_batched(
        self,
        object_codes: list[str] | None,
        tokens: list[str],
        top_k: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """路1 批量术语检索 — 按 keyword 分组返回。

        与 _do_path1 不同，此方法保留 search_terms_batch 的 per-keyword
        分组结构，用于 word_batch 模式避免 N 次 batch 调用。
        """
        if not tokens:
            return {}
        if object_codes is not None:
            return self._path1_scoped_batched(
                object_codes=object_codes, tokens=tokens, top_k=top_k
            )
        return self._path1_global_batched(tokens, top_k)

    def _path1_scoped_batched(
        self,
        *,
        object_codes: list[str],
        tokens: list[str],
        top_k: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """指定类型批量 — search_terms_batch 一次调用，按 kw 分组。"""
        batch_method = getattr(self, "search_terms_batch", None)
        if not callable(batch_method):
            return self._path1_scoped_fallback_batched(object_codes, tokens, top_k)

        try:
            batch = batch_method(
                keywords=tokens,
                term_type_codes=object_codes,
                top_k=top_k,
            )
        except Exception:
            logger.warning("_path1_scoped_batched: batch failed", exc_info=True)
            return self._path1_scoped_fallback_batched(object_codes, tokens, top_k)

        results: dict[str, list[dict[str, Any]]] = {}
        if isinstance(batch, dict):
            for kw, qr in batch.items():
                seen: set[str] = set()
                hits: list[dict[str, Any]] = []
                for item in _extract_items(qr):
                    tid = _attr(item, "term_id", "")
                    if tid and tid not in seen:
                        seen.add(tid)
                        hits.append(_make_path1_hit(item))
                results[kw] = hits
        return results

    def _path1_scoped_fallback_batched(
        self,
        object_codes: list[str],
        tokens: list[str],
        top_k: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """降级：逐类型逐 token → 按 token 分组。"""
        reader = self._get_knowledge_reader()
        results: dict[str, list[dict[str, Any]]] = {t: [] for t in tokens}

        for oc in object_codes:
            for token in tokens:
                try:
                    raw = reader.search_terms(
                        term_type_code=oc, keyword=token, limit=top_k
                    )
                except Exception:
                    continue
                seen = {h["term_id"] for h in results[token] if h.get("term_id")}
                for item in _extract_items(raw):
                    tid = _attr(item, "term_id", "")
                    if tid and tid not in seen:
                        seen.add(tid)
                        results[token].append(_make_path1_hit(item))
        return results

    def _path1_global_batched(
        self,
        tokens: list[str],
        top_k: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """全类型批量 — search_terms_batch(type=None) 一次调用，按 kw 分组。"""
        batch_method = getattr(self, "search_terms_batch", None)
        if not callable(batch_method):
            return self._path1_global_fallback_batched(tokens, top_k)

        try:
            batch = batch_method(keywords=tokens, term_type_codes=None, top_k=top_k)
        except Exception:
            logger.warning("_path1_global_batched: batch failed", exc_info=True)
            return self._path1_global_fallback_batched(tokens, top_k)

        results: dict[str, list[dict[str, Any]]] = {}
        if isinstance(batch, dict):
            for kw, qr in batch.items():
                seen: set[str] = set()
                hits: list[dict[str, Any]] = []
                for item in _extract_items(qr):
                    tid = _attr(item, "term_id", "")
                    if tid and tid not in seen:
                        seen.add(tid)
                        hits.append(_make_path1_hit(item))
                results[kw] = hits
        return results

    def _path1_global_fallback_batched(
        self,
        tokens: list[str],
        top_k: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """降级：逐 token wildcard search → 按 token 分组。"""
        reader = self._get_knowledge_reader()
        results: dict[str, list[dict[str, Any]]] = {}

        for token in tokens:
            seen: set[str] = set()
            hits: list[dict[str, Any]] = []
            try:
                raw = reader.search_terms(
                    term_type_code="*", keyword=token, limit=top_k
                )
            except Exception:
                raw = None
            for item in _extract_items(raw):
                tid = _attr(item, "term_id", "")
                if tid and tid not in seen:
                    seen.add(tid)
                    hits.append(_make_path1_hit(item))
            results[token] = hits
        return results

    # ── Path 2 helpers ──────────────────────────────────────────────────

    async def _path2_chunk_to_term_search(
        self,
        *,
        base_id: str,
        object_code: str,
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """路2 限定 KB chunk 搜索 → term 匹配。

        通过 EntityStore 获取 object_code 对应的 ext_property.kb_resource_id，
        限定在该 KB 内进行 chunk 向量搜索。
        datasource_alias 从 obj dict 直接提取。
        """
        # 获取 kb_resource_id 和 datasource_alias
        obj_data: dict[str, Any] | None = None
        try:
            obj_data = self._entity_store.get("objects", object_code)
        except Exception:
            logger.debug(
                "_path2: entity_store.get('objects', %s) failed",
                object_code,
                exc_info=True,
            )

        kb_resource_id = _resolve_kb_resource_id_for_object(obj_data)
        if not kb_resource_id:
            logger.debug("_path2: no kb_resource_id for object_code=%s", object_code)
            return []

        datasource_alias = ""
        if obj_data:
            datasource_alias = obj_data.get("datasource_alias", "")

        return await self._do_chunk_search(
            query=query,
            kb_resource_id=kb_resource_id,
            top_k=top_k,
            datasource_alias=datasource_alias,
            object_code=object_code,
        )

    async def _path2_global_chunk_to_term_search(
        self,
        *,
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """路2 不限 KB 全库 chunk 搜索 → term 匹配。

        kb_resource_id=None 表示不限定知识库，全库 chunk 向量搜索。
        object_code="" 表示不限对象类型。
        datasource_alias 使用默认值。
        """
        return await self._do_chunk_search(
            query=query,
            kb_resource_id=None,
            top_k=top_k,
            datasource_alias="",
            object_code="",
        )

    async def _do_chunk_search(
        self,
        *,
        query: str,
        kb_resource_id: str | None,
        top_k: int,
        datasource_alias: str = "",
        object_code: str = "",
        kb_directory: str | None = None,
        term_type_codes: list[str] | None = None,
        _kb_search_backend: Any = None,
    ) -> list[dict[str, Any]]:
        """执行真实 KB chunk 向量搜索 → term 匹配。

        使用 HttpKnowledgeSearchBackend.search() 调用真实 KB chunk API，
        禁止用 entity_store.search() 关键词兜底。

        流程：
        1. 调用 KB search API 获取 chunk results
        2. 按 filePath 聚合，每个文件保留最高分
        3. 提取 resource_id → search_terms → term_tags 匹配
        4. 返回 term 匹配结果列表

        Args:
            query: 搜索查询文本。
            kb_resource_id: ByClaw knowledge resource ID.
            top_k: 返回结果上限。

            datasource_alias: 数据源别名（从 obj dict 提取）。
            object_code: 对象编码。
            kb_directory: 知识库目录过滤。
            term_type_codes: 限定反查的 term 类型列表，None 不限。
            _kb_search_backend: 测试用注入的 mock backend。
        """
        # ── Step 1: KB chunk search ─────────────────────────────────
        try:
            chunk_records = await self._exec_kb_search(
                query=query,
                kb_resource_id=kb_resource_id,
                top_k=top_k * 2,  # 多召回供聚合
                datasource_alias=datasource_alias,
                object_code=object_code,
                kb_directory=kb_directory,
                _kb_search_backend=_kb_search_backend,
            )
        except Exception:
            logger.warning(
                "_do_chunk_search: KB search failed (kb_resource_id=%s, query=%s)",
                kb_resource_id,
                query,
                exc_info=True,
            )
            return []

        if not chunk_records:
            return []

        # ── Step 2: Aggregate by filePath, keep highest score ─────────
        file_best: dict[str, dict[str, Any]] = {}
        for rec in chunk_records:
            file_path = rec.get("filePath") or rec.get("file_path", "")
            score = float(rec.get("score", 0))
            if not file_path:
                continue
            if file_path not in file_best or score > float(
                file_best[file_path].get("score", 0)
            ):
                file_best[file_path] = rec

        if not file_best:
            return []
        # ── Step 3: Match filePath → ext_attrs.kb_file_path ────
        # KB chunk records contain filePath but NOT resourceId.
        # Match against TermItem.ext_attrs.kb_file_path directly.
        file_scores: dict[str, float] = {}
        for rec in file_best.values():
            fp = rec.get("filePath") or rec.get("file_path", "")
            s = float(rec.get("score", 0))
            if fp and (fp not in file_scores or s > file_scores[fp]):
                file_scores[fp] = s

        logger.info(
            "_do_chunk_search: %d unique filePaths to match",
            len(file_scores),
        )

        return self._match_chunks_to_terms_by_filepath(
            file_scores=file_scores,
            top_k=top_k,
            term_type_codes=term_type_codes,
        )

    async def _exec_kb_search(
        self,
        *,
        query: str,
        kb_resource_id: str | None,
        top_k: int,
        datasource_alias: str,
        object_code: str,
        kb_directory: str | None = None,
        _kb_search_backend: Any = None,
    ) -> list[dict[str, Any]]:
        """Execute KB chunk search via HttpKnowledgeSearchBackend (async)."""
        if _kb_search_backend is not None:
            backend = _kb_search_backend
        else:
            from datacloud_data_sdk.executor.kb_search_backend import (
                HttpKnowledgeSearchBackend,
            )

            backend = HttpKnowledgeSearchBackend(None)

        from datacloud_data_sdk.executor.kb_search_backend import (
            KnowledgeSearchRequest,
        )

        request = KnowledgeSearchRequest(
            object_code=object_code or "",
            datasource_alias=datasource_alias,
            query=query,
            limit=top_k,
            kb_resource_id=kb_resource_id if kb_resource_id else None,
            kb_directory=kb_directory,
        )

        result = await backend.search(request)

        records: list[dict[str, Any]] = []
        if hasattr(result, "records"):
            records = cast("list[dict[str, Any]]", result.records)
        elif isinstance(result, dict):
            records = cast("list[dict[str, Any]]", result.get("records", []))

        if records:
            logger.info(
                "_exec_kb_search OK: kb_resource_id=%s query=%s → %d records",
                kb_resource_id,
                query,
                len(records),
            )
        else:
            logger.warning(
                "_exec_kb_search OK: kb_resource_id=%s query=%s → 0 records (empty response)",
                kb_resource_id,
                query,
            )
        return records

    def _chunk_to_simple_hits(
        self,
        records: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """从 chunk metadata 中提取简单 term hit（resource_id 匹配失败时兜底）。"""
        results: list[dict[str, Any]] = []
        for rec in records:
            name = rec.get("fileName") or rec.get("file_name", "")
            rid = rec.get("resourceId") or rec.get("resource_id", "")
            if name or rid:
                results.append(
                    {
                        "term_id": rid or name,
                        "term_code": "",
                        "term_name": name,
                        "term_type_code": _term_type_code(rec, ""),
                        "file_name": rec.get("filePath") or rec.get("file_path"),
                        "match_type": "chunk_to_term",
                        "score": float(rec.get("score", 0.5)),
                    }
                )
                return sorted(results, key=lambda h: h["score"], reverse=True)[:top_k]
        return []

    def _match_chunks_to_terms_by_filepath(
        self,
        *,
        file_scores: dict[str, float],
        top_k: int,
        term_type_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """用 filePath 匹配 term_tags.kb_file_path。

        通过 search_terms_by_labels（纯 label_filter SQL）直接过滤，
        不需要关键词、不需要 Python 后过滤。
        """
        label_method = getattr(self, "search_terms_by_labels", None)
        if not callable(label_method):
            logger.warning(
                "_match_chunks_to_terms_by_filepath: search_terms_by_labels unavailable"
            )
            return []

        label_filters = [
            {"field_code": "kb_file_path", "filter_value": fp} for fp in file_scores
        ]

        try:
            items = label_method(
                label_filters=label_filters,
                label_condition="or",
                term_type_codes=term_type_codes,
                top_k=top_k * len(file_scores),
            )
        except Exception:
            logger.warning(
                "_match_chunks_to_terms_by_filepath: search_terms_by_labels failed",
                exc_info=True,
            )
            return []

        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for item in items:
            tid = item.get("term_id", "")
            if not tid or tid in seen:
                continue
            tp = _term_type_code(item, "")
            fp = (
                item.get("ext_attrs", {}).get("kb_file_path", "")
                if isinstance(item.get("ext_attrs"), dict)
                else ""
            )
            if fp and fp in file_scores:
                seen.add(tid)
                results.append(
                    {
                        "term_id": tid,
                        "term_code": item.get("term_code", ""),
                        "term_name": item.get("term_name", ""),
                        "term_type_code": tp,
                        "file_name": fp,
                        "match_type": "chunk_to_term",
                        "score": file_scores[fp],
                    }
                )

        logger.info(
            "_match_chunks_to_terms_by_filepath: %d filePaths × label_filter → %d term matches",
            len(file_scores),
            len(results),
        )
        return sorted(results, key=lambda h: h["score"], reverse=True)[:top_k]

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


# ============================================================================
# Module-level helpers for search_object_instances_unstructured
# ============================================================================


def _resolve_input_mode(
    query: str | None,
    queries: list[str] | None,
) -> tuple[str, list[str]]:
    """根据传入参数推断输入模式并归一化为关键词列表。

    Returns:
        ("sentence"|"word_batch", [keyword, ...])
    """
    if queries:
        keywords = [q.strip() for q in queries if q and q.strip()]
        return ("word_batch", keywords)
    if query and query.strip():
        return ("sentence", [query.strip()])
    return ("sentence", [])


def _hybrid_tokenize(query: str) -> list[str]:
    """使用 HybridTokenizer 对查询文本进行分词。

    委托到 datacloud_knowledge.retrieval.tokenizers.hybrid.hybrid_tokenize，
    自动检测中英文并选择合适的分词器。

    Returns:
        非空词元列表。
    """
    from datacloud_knowledge.retrieval.tokenizers.hybrid import hybrid_tokenize

    return hybrid_tokenize(query)


def _tokenize_query(query: str) -> list[str]:
    """向后兼容：委托给 _hybrid_tokenize。

    已弃用，新代码应使用 _hybrid_tokenize。
    """
    return _hybrid_tokenize(query)


def _attr(obj: Any, name: str, default: Any = "") -> Any:
    """从 dict 或对象中安全获取属性值。

    Args:
        obj: dict 或对象。
        name: 属性名。
        default: 缺省值。

    Returns:
        属性值或 default。
    """
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _term_type_code(item: Any, default: str = "") -> str:
    """从 TermItem 中安全获取 term_type_code，兼容 term_type 字段。"""
    val = _attr(item, "term_type_code", None)
    if val is not None and val != "":
        return str(val)
    val = _attr(item, "term_type", None)
    if val is not None:
        return str(val)
    return default


def _extract_items(raw: Any) -> list[Any]:
    """从 search_terms / QueryResult 中提取 items 列表。

    兼容 dict（含 'items' 键）、具有 .items 属性的对象、以及直接的 list。
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        return cast("list[Any]", raw.get("items", []))
    if isinstance(raw, list):
        return raw
    items = getattr(raw, "items", None)
    if items is not None and callable(items):
        return list(items())
    if items is not None:
        return cast("list[Any]", items)
    return []


def _make_path1_hit(item: Any) -> dict[str, Any]:
    """将 TermItem 转换为路1 hit dict（统一格式）。"""
    ext = _attr(item, "ext_attrs", {})
    ext_attrs = ext if isinstance(ext, dict) else {}
    labels = _attr(item, "labels", {})
    labels = labels if isinstance(labels, dict) else {}
    return {
        "term_id": _attr(item, "term_id", ""),
        "term_code": _attr(item, "term_code", ""),
        "term_name": _attr(item, "term_name", ""),
        "term_type_code": _term_type_code(item, ""),
        "file_name": ext_attrs.get("kb_file_path"),
        "kb_resource_id": ext_attrs.get("kb_resource_id")
        or ext_attrs.get("resource_id")
        or labels.get("kb_resource_id")
        or labels.get("resource_id"),
        "kb_id": ext_attrs.get("kb_id") or labels.get("kb_id"),
        "match_type": "term_instance",
        "score": float(_attr(item, "score", 0)),
    }


def _fuse_path_results(
    path1: list[dict[str, Any]],
    path2: list[dict[str, Any]],
    top_k: int = 20,
) -> list[Any]:
    """向后兼容委托：委托给 _fuse_path_results_rrf(k=60)。"""
    return _fuse_path_results_rrf(path1, path2, k=60, top_k=top_k)


def _fuse_path_results_rrf(
    path1: list[dict[str, Any]],
    path2: list[dict[str, Any]],
    k: int = 60,
    top_k: int = 20,
) -> list[Any]:
    """RRF(k=60) 双路融合，返回 ObjectInstanceHit 列表。

    公式: RRF(term) = 1/(k + rank_in_path1) + 1/(k + rank_in_path2)
    """
    from datacloud_platform.models.shared import ObjectInstanceHit

    rrf_fuse_fn = _get_rrf_fuse()

    # Per-term metadata cache: term_id → { fields }
    meta: dict[str, dict[str, Any]] = {}

    p1_tuples: list[tuple[str, str, str, str, str]] = []
    for h in path1:
        tid = h.get("term_id", "")
        if tid:
            p1_tuples.append(
                (tid, h.get("term_name", ""), "", h.get("term_type_code", ""), "")
            )
            if tid not in meta:
                meta[tid] = {
                    "instance_id": tid,
                    "instance_code": h.get("term_code", ""),
                    "instance_name": h.get("term_name", ""),
                    "object_code": h.get("term_type_code", ""),
                    "file_name": h.get("file_name"),
                    "kb_resource_id": h.get("kb_resource_id") or "",
                    "kb_id": h.get("kb_id") or "",
                    "term_instance_score": float(h.get("score", 0)),
                    "chunk_score": 0,
                }
            else:
                meta[tid]["term_instance_score"] = float(h.get("score", 0))

    p2_tuples: list[tuple[str, str, str, str, str]] = []
    for h in path2:
        tid = h.get("term_id", "")
        if tid:
            p2_tuples.append(
                (tid, h.get("term_name", ""), "", h.get("term_type_code", ""), "")
            )
            if tid not in meta:
                meta[tid] = {
                    "instance_id": tid,
                    "instance_code": h.get("term_code", ""),
                    "instance_name": h.get("term_name", ""),
                    "object_code": h.get("term_type_code", ""),
                    "file_name": h.get("file_name"),
                    "kb_resource_id": h.get("kb_resource_id") or "",
                    "kb_id": h.get("kb_id") or "",
                    "term_instance_score": 0,
                    "chunk_score": float(h.get("score", 0)),
                }
            else:
                # 双路命中：file_name 优先路2（更精确）
                meta[tid]["chunk_score"] = float(h.get("score", 0))
                if h.get("file_name"):
                    meta[tid]["file_name"] = h.get("file_name")
                if h.get("kb_resource_id"):
                    meta[tid]["kb_resource_id"] = h.get("kb_resource_id")

    ranked_lists: list[list[tuple[str, str, str, str, str]]] = []
    if p1_tuples:
        ranked_lists.append(p1_tuples)
    if p2_tuples:
        ranked_lists.append(p2_tuples)

    if not ranked_lists:
        return []

    fused = rrf_fuse_fn(ranked_lists, k=k, top_n=top_k)

    result: list[Any] = []
    for rank_idx, c in enumerate(fused):
        m = meta.get(c.term_id, {})
        result.append(
            ObjectInstanceHit(
                instance_id=m.get("instance_id", c.term_id),
                instance_code=m.get("instance_code", ""),
                instance_name=m.get("instance_name", c.term_name),
                object_code=m.get("object_code", c.term_type_code),
                file_name=m.get("file_name"),
                kb_resource_id=m.get("kb_resource_id") or None,
                kb_id=m.get("kb_id") or None,
                score=c.rrf_score,
            )
        )

    return result


def _should_run_path2(
    enable_chunk_recall: bool,
) -> bool:
    """判断是否执行路2 KB chunk 搜索。"""
    return enable_chunk_recall


def _resolve_kb_resource_id_for_object(
    obj_data: dict[str, Any] | None,
) -> str | None:
    """从 EntityStore 返回的 object dict 中提取 ext_property.kb_resource_id。

    Args:
        obj_data: store.get("objects", code) 的返回值。

    Returns:
        kb_resource_id 字符串，未找到时返回 None。
    """
    if not obj_data:
        return None
    ext = obj_data.get("ext_property", {}) or {}
    kb_resource_id = ext.get("kb_resource_id")
    if kb_resource_id:
        return str(kb_resource_id)
    return None


async def _do_chunk_search(
    query: str,
    kb_resource_id: str | None,
    top_k: int,
    datasource_alias: str = "",
    object_code: str = "",
    kb_directory: str | None = None,
    _kb_search_backend: Any = None,
) -> list[dict[str, Any]]:
    """独立函数形式的 _do_chunk_search（供测试直接调用）。"""
    try:
        from datacloud_data_sdk.executor.kb_search_backend import (
            HttpKnowledgeSearchBackend,
            KnowledgeSearchRequest,
        )
    except ImportError:
        logger.debug(
            "_do_chunk_search: datacloud_data_sdk not available", exc_info=True
        )
        return []

    backend = _kb_search_backend or HttpKnowledgeSearchBackend(None)

    try:
        request = KnowledgeSearchRequest(
            object_code=object_code or "",
            datasource_alias=datasource_alias,
            query=query,
            limit=top_k,
            kb_resource_id=kb_resource_id if kb_resource_id else None,
            kb_directory=kb_directory,
        )

        result = await backend.search(request)

        if hasattr(result, "records"):
            return cast("list[dict[str, Any]]", result.records)
        if isinstance(result, dict):
            return cast("list[dict[str, Any]]", result.get("records", []))
    except Exception:
        logger.warning(
            "_do_chunk_search: KB search failed (kb_resource_id=%s)",
            kb_resource_id,
            exc_info=True,
        )

    return []
