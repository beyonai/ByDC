"""OntologyBackend core — parse, load, CRUD (Object/View/Relation/Action/Datasource)."""

from __future__ import annotations

import json as _json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable

from datacloud_platform.adapters.json_entity_store import JsonEntityStore
from datacloud_platform.adapters.data_adapter._base import (
    DataCloudDataBackendBase,
    _normalize_object_codes,
)
from datacloud_platform.models import ObjectSummary, ParsedOwlContent
from datacloud_platform.models.action import Action, ActionParam
from datacloud_platform.models.datasource import Datasource, DbConnection
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.property import Property
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View, ViewProperty
from datacloud_platform.platform_file_storage import atomic_write_json

logger = logging.getLogger(__name__)


class OntologyBackendMixin(DataCloudDataBackendBase):
    """OntologyBackend core — parse, load, CRUD (Object/View/Relation/Action/Datasource)."""

    # ── OntologyBackend ────────────────────────────────────────────────────

    def parse_owl(self, directory: Path) -> ParsedOwlContent:
        """Parse OWL directory via OwlParser, return typed ParsedOwlContent.

        Args:
            directory: Path to the OWL resource directory.

        Returns:
            ParsedOwlContent with objects, views, relations, actions, dbsources.
        """
        from datacloud_data_sdk.ontology.owl_parser import OwlParser  # noqa: PLC0415

        raw: dict[str, Any] = OwlParser().parse_resource_directory(directory)
        objects = list(raw.get("objects", []))
        views = list(raw.get("views", []))
        relations = list(raw.get("relations", []))

        # Extract actions from embedded object.actions, adding belongObjectCode
        actions: list[dict[str, Any]] = []
        for obj in objects:
            obj_code = obj.get("object_code", "")
            for act in obj.get("actions", []):
                if isinstance(act, dict):
                    act = dict(act)
                    act.setdefault("belongObjectCode", obj_code)
                    actions.append(act)

        # Extract dbsources from datasource_configs dict
        dbsources: list[dict[str, Any]] = []
        raw_ds: dict[str, dict[str, Any]] = raw.get("datasource_configs", {}) or {}
        for alias, cfg in raw_ds.items():
            dbsources.append(dict(cfg, alias=alias))

        return ParsedOwlContent(
            objects=objects,
            views=views,
            relations=relations,
            actions=actions,
            dbsources=dbsources,
        )

    def batch_import_ontology(
        self,
        base_path: Path,
        objects: list[dict[str, Any]],
        views: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        dbsources: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Batch import ontology content — writes registry + shard files + rebuilds indexes.

        Args:
            base_path: Root directory for the ontology base.
            objects: List of object dicts to persist.
            views: List of view dicts to persist.
            relations: List of relation dicts to persist.
            actions: List of action dicts to persist.
            dbsources: List of datasource dicts to persist.

        Returns:
            Counts dict keyed by entity type.
        """
        entity_store = JsonEntityStore(base_path)

        counts: dict[str, int] = {
            "objects": 0,
            "views": 0,
            "relations": 0,
            "actions": 0,
            "dbsources": 0,
        }

        # Write unified JSON registry (fast-load path)
        registry: dict[str, list[dict[str, Any]]] = {
            "objects": objects,
            "views": views,
            "relations": relations,
            "actions": actions,
            "dbsources": dbsources,
        }
        base_path.mkdir(parents=True, exist_ok=True)
        atomic_write_json(base_path / "objects_registry.json", registry)

        # Write per-object shard files
        for obj in objects:
            obj_code: str = obj.get("object_code", "") or ""
            if obj_code:
                entity_store.save("objects", obj_code, obj)
                counts["objects"] += 1

        # Write per-view shard files
        for view in views:
            v_code: str = (
                view.get("view_code", view.get("viewCode", view.get("view_id", "")))
                or ""
            )
            if v_code:
                entity_store.save("views", v_code, view)
                counts["views"] += 1

        # Write per-relation shard files
        for rel in relations:
            r_code: str = rel.get("relation_code", rel.get("relationCode", "")) or ""
            if r_code:
                entity_store.save("relations", r_code, rel)
                counts["relations"] += 1

        # Write per-action shard files
        for act in actions:
            a_code: str = act.get("action_code", act.get("actionCode", "")) or ""
            if a_code:
                entity_store.save("actions", a_code, act)
                counts["actions"] += 1

        # Write per-datasource shard files
        for ds in dbsources:
            db_id: str = ds.get("db_id", ds.get("dbId", "")) or ""
            if db_id:
                entity_store.save("datasources", db_id, ds)
                counts["dbsources"] += 1

        # Rebuild all indexes
        for et in ("objects", "views", "relations", "actions", "datasources"):
            entity_store.save_index(et, entity_store.rebuild_index(et))

        # Batch sync terms to knowledge DB (single writer, no per-term backfill)
        self._batch_sync_entity_terms(objects, views, relations, actions)

        logger.info(
            "batch_import_ontology: %s objects=%d views=%d relations=%d actions=%d dbsources=%d",
            base_path,
            counts["objects"],
            counts["views"],
            counts["relations"],
            counts["actions"],
            counts["dbsources"],
        )
        return counts

    def load_ontology(self, base_path: Path) -> OntologyQueryable:
        """Load parsed ontology directory into a queryable runtime object.

        Prefers ``objects_registry.json`` (single file, < 1s) when available.
        On first access without a registry, parses OWL, persists the registry
        via ``parse_owl()`` + ``batch_import_ontology()`` (same pipeline as
        ``import-owl``), then loads from the newly created registry.

        Args:
            base_path: Path to the OWL resource directory root.

        Returns:
            An OntologyLoader instance that satisfies OntologyQueryable.
        """
        from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415

        # Fast path: unified JSON registry (< 1s)
        registry = base_path / "objects_registry.json"
        if registry.exists():
            content = _json.loads(registry.read_text(encoding="utf-8"))
            loader = OntologyLoader()
            loader.load_from_content(content)
            return loader  # type: ignore[no-any-return]

        # Fallback: OWL directory exists but no registry yet —
        # parse → persist (same pipeline as import-owl) → fast path
        if base_path.exists():
            logger.info(
                "objects_registry.json not found in %s, "
                "falling back to parse_owl + batch_import_ontology",
                base_path,
            )
            parsed = self.parse_owl(base_path)
            self.batch_import_ontology(
                base_path,
                parsed.objects,
                parsed.views,
                parsed.relations,
                parsed.actions,
                parsed.dbsources,
            )
            return self.load_ontology(base_path)  # recurse → hits fast path above

        # No OWL directory, return empty loader
        return OntologyLoader()  # type: ignore[no-any-return]

    def load_terms(
        self, _loader: OntologyQueryable, *, library_id: str = "PERSONAL_LIB"
    ) -> Any:
        """Load term index from knowledge DB via TermLoader.

        Uses the datacloud_data_sdk reference TermLoader implementation.
        The return type is intentionally ``Any``: TermLoader is not yet
        abstracted into a Protocol.

        Args:
            loader: An OntologyQueryable (typically an OntologyLoader).
            library_id: Library identifier (default ``PERSONAL_LIB``).

        Returns:
            A TermLoader instance.
        """
        from datacloud_data_sdk.ontology.term_loader import TermLoader  # noqa: PLC0415

        _ = library_id  # consumed by concrete TermLoader subclass
        return TermLoader()

    def create_table(self, object_code: str, fields: list[dict[str, Any]]) -> None:
        """Create physical table for DYNAMIC_TABLE objects.

        Args:
            object_code: Ontology object code / table name.
            fields: Column definitions.
        """
        from datacloud_data_sdk.ddl.table_manager import (  # noqa: PLC0415
            create_table as _create_table,
        )

        _create_table(object_code, fields)

    def drop_table(self, object_code: str) -> None:
        """Drop physical table.

        Args:
            object_code: Ontology object code / table name.
        """
        from datacloud_data_sdk.ddl.table_manager import drop_table as _drop_table  # noqa: PLC0415

        _drop_table(object_code)

    def get_objects(
        self, loader: OntologyQueryable, base_id: str
    ) -> list[ObjectSummary]:
        """Get all object summaries under a base.

        Args:
            loader: An OntologyQueryable with _classes populated.
            base_id: Base / project identifier.

        Returns:
            List of ObjectSummary for every class in the loader.
        """
        _ = base_id
        return [self._to_summary(cls) for cls in loader._classes.values()]

    def get_object_detail(
        self, loader: OntologyQueryable, object_code: str
    ) -> dict[str, Any] | None:
        """Get full object detail with properties and actions.

        Args:
            loader: An OntologyQueryable with _classes populated.
            object_code: The object code to look up.

        Returns:
            Full ObjectType dict (alias-mapped) if found, otherwise None.
        """
        cls = loader._classes.get(object_code)
        if cls is None:
            return None
        obj = ObjectType(
            objectCode=cls.object_code,
            objectName=cls.object_name,
            objectDesc=getattr(cls, "description", None),
            objectSource=getattr(cls, "source_type", None),
            conceptType=getattr(cls, "concept_type", None),
            baseId="",
            properties=[
                Property(
                    propertyName=f.field_name,
                    propertyCode=f.field_code,
                    dataType=f.field_type,
                    businessKey=1 if f.is_primary_key else 0,
                    sourceColumn=getattr(f, "source_column", None),
                    dbId=getattr(cls, "datasource_alias", None),
                )
                for f in cls.fields
            ],
            actions=[
                Action(
                    actionCode=a.action_code,
                    actionName=a.action_name,
                    actionType=a.action_type,
                    belongObjectCode=a.belong_class,
                    actionDesc=getattr(a, "description", None),
                    requestUrl=getattr(a, "request_url", None),
                    requestMethod=getattr(a, "request_method", None),
                    params=[
                        ActionParam(
                            paramCode=p.param_code,
                            paramName=p.param_name,
                            paramType=getattr(p, "param_type", None),
                            isRequired=1 if p.required else 0,
                            direction=getattr(p, "direction", None),
                            mappingPath=getattr(p, "mapping_path", None),
                        )
                        for p in getattr(a, "params", [])
                    ],
                )
                for a in getattr(cls, "actions", [])
            ],
        )
        return obj.model_dump(by_alias=True)

    # ── Object CRUD (stub — datacloud-data SDK does not yet support) ────────

    def create_object(self, base_id: str, obj: Any) -> Any:
        """Persist a new ontology object via JsonEntityStore.

        Args:
            base_id: Base / project identifier.
            obj: ObjectType dict or pydantic model.

        Returns:
            The saved object dict.

        Raises:
            ValueError: If object_code is missing or empty.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        obj_dict: dict[str, Any] = (
            obj if isinstance(obj, dict) else obj.model_dump(by_alias=True)
        )
        code: str = obj_dict.get("object_code") or obj_dict.get("objectCode", "")
        if not code:
            raise ValueError("object_code is required for object creation")
        entity_store.save("objects", code, obj_dict)
        self._incremental_save(entity_store, "objects", code, obj_dict)
        self._upsert_object_registry(base_path, self._to_registry_entry(obj_dict))
        self._invalidate_loader_cache(base_id)
        logger.info("Created object: base_id=%s object_code=%s", base_id, code)
        self._sync_entity_terms(
            entity_type="object",
            entity_code=code,
            entity_name=obj_dict.get("objectName") or obj_dict.get("object_name", code),
            entity_desc=obj_dict.get("objectDesc") or obj_dict.get("description", ""),
            base_id=base_id,
        )
        return obj_dict

    def update_object(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Update an existing ontology object.

        Args:
            base_id: Base / project identifier.
            object_code: Target object code.
            obj: Updated ObjectType dict or pydantic model.

        Returns:
            The updated object dict.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        obj_dict: dict[str, Any] = (
            obj if isinstance(obj, dict) else obj.model_dump(by_alias=True)
        )
        entity_store.save("objects", object_code, obj_dict)
        self._incremental_save(entity_store, "objects", object_code, obj_dict)
        self._upsert_object_registry(base_path, self._to_registry_entry(obj_dict))
        self._invalidate_loader_cache(base_id)
        logger.info("Updated object: base_id=%s object_code=%s", base_id, object_code)
        # Re-sync terms: delete old → write new (build_terms is upsert-safe)
        self._remove_entity_terms(entity_type="object", entity_code=object_code)
        self._sync_entity_terms(
            entity_type="object",
            entity_code=object_code,
            entity_name=obj_dict.get("objectName")
            or obj_dict.get("object_name", object_code),
            entity_desc=obj_dict.get("objectDesc") or obj_dict.get("description", ""),
            base_id=base_id,
        )
        return obj_dict

    @staticmethod
    def _to_registry_entry(obj_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert camelCase ObjectType dict to objects_registry.json snake_case format.

        Extracts kb_id/kb_directory from sourceConfig into ext_property so that
        OntologyLoader (which reads ext_property) can find them at runtime.
        """
        code = obj_dict.get("object_code") or obj_dict.get("objectCode", "")
        source_type = (
            obj_dict.get("source_type")
            or obj_dict.get("objectSource")
            or obj_dict.get("sourceType", "DB")
        )
        # Merge ext_property; promote kb_id/kb_directory from sourceConfig when absent
        ext_property: dict[str, Any] = dict(
            obj_dict.get("ext_property") or obj_dict.get("extProperty") or {}
        )
        source_config = obj_dict.get("source_config") or obj_dict.get("sourceConfig")
        if isinstance(source_config, dict):
            for kb_key in ("kb_id", "kb_directory", "knCode"):
                if source_config.get(kb_key) and kb_key not in ext_property:
                    ext_property[kb_key] = source_config[kb_key]

        # Normalise properties → fields
        raw_fields = obj_dict.get("fields") or obj_dict.get("properties") or []
        fields: list[dict[str, Any]] = [
            {
                "field_code": f.get("field_code") or f.get("propertyCode", ""),
                "field_name": f.get("field_name") or f.get("propertyName", ""),
                "field_type": f.get("field_type") or f.get("dataType", "STRING"),
                "is_primary_key": bool(f.get("is_primary_key", False)),
                "source_column": f.get("source_column") or f.get("sourceColumn"),
            }
            for f in raw_fields
        ]

        entry: dict[str, Any] = {
            "object_code": code,
            "object_name": obj_dict.get("object_name") or obj_dict.get("objectName", code),
            "description": obj_dict.get("description") or obj_dict.get("objectDesc", ""),
            "source_type": source_type,
            "concept_type": obj_dict.get("concept_type") or obj_dict.get("conceptType", ""),
            "table_name": obj_dict.get("table_name") or obj_dict.get("tableName", ""),
            "fields": fields,
            "actions": obj_dict.get("actions", []),
        }
        if ext_property:
            entry["ext_property"] = ext_property
        return entry

    def _upsert_object_registry(self, base_path: Path, entry: dict[str, Any]) -> None:
        """Incrementally upsert one object into objects_registry.json."""
        registry_path = base_path / "objects_registry.json"
        try:
            content: dict[str, Any] = (
                _json.loads(registry_path.read_text(encoding="utf-8"))
                if registry_path.exists()
                else {}
            )
        except (ValueError, OSError):
            logger.warning("objects_registry.json unreadable, starting fresh: %s", registry_path)
            content = {}

        objects: list[dict[str, Any]] = list(content.get("objects") or [])
        code = entry["object_code"]
        for i, obj in enumerate(objects):
            if obj.get("object_code") == code:
                objects[i] = entry
                break
        else:
            objects.append(entry)

        content["objects"] = objects
        content.setdefault("views", [])
        content.setdefault("relations", [])
        base_path.mkdir(parents=True, exist_ok=True)
        atomic_write_json(registry_path, content)

    @staticmethod
    def _invalidate_loader_cache(base_id: str) -> None:
        """Invalidate the in-memory OntologyLoader cache so the next request rebuilds it.

        Uses the module-level runtime ref registered by the API server at startup.
        Safe to call even when running outside the API (e.g. tests) — silently no-ops.
        """
        try:
            from datacloud_platform.api.mcp_handler import _get_loader_runtime  # noqa: PLC0415

            runtime = _get_loader_runtime()
            if runtime is not None and hasattr(runtime, "invalidate"):
                runtime.invalidate(base_id)
                logger.debug("Loader cache invalidated for base_id=%s", base_id)
        except Exception:
            logger.debug("_invalidate_loader_cache: skipped (runtime not available)")

    def delete_object(self, base_id: str, object_code: str) -> None:
        """Delete an ontology object.

        Args:
            base_id: Base / project identifier.
            object_code: Target object code.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        entity_store.delete("objects", object_code)
        self._incremental_delete(entity_store, "objects", object_code)
        logger.info("Deleted object: base_id=%s object_code=%s", base_id, object_code)
        self._remove_entity_terms(entity_type="object", entity_code=object_code)

    # ── View CRUD ──────────────────────────────────────────────────────────

    def get_views(self, loader: Any, base_id: str) -> list[dict[str, Any]]:
        """Get all views from the loaded ontology.

        Args:
            loader: An OntologyQueryable with _views populated.
            base_id: Base / project identifier.

        Returns:
            List of View dicts (alias-mapped).
        """
        _ = base_id
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        result: list[dict[str, Any]] = []
        for vc, view_data in raw_views.items():
            normalized_codes = _normalize_object_codes(view_data.get("objects", []))
            view = View(
                viewCode=view_data.get("view_id", vc),
                viewName=view_data.get("view_name", ""),
                description=view_data.get("description"),
                objectCodes=normalized_codes,
                properties=[
                    ViewProperty(
                        propertyName=m.get("property_name", ""),
                        propertyCode=m.get("property_code", ""),
                        sourceObject=m.get("source_object_code", ""),
                        sourceObjectProperty=m.get("source_object_column_code", ""),
                    )
                    for m in view_data.get("mappings", [])
                ],
            )
            result.append(view.model_dump(by_alias=True))
        return result

    def get_view_detail(
        self, loader: Any, base_id: str, view_code: str
    ) -> dict[str, Any] | None:
        """Get single view detail by code from the loaded ontology.

        Args:
            loader: An OntologyQueryable with _views populated.
            base_id: Base / project identifier.
            view_code: View identifier to look up.

        Returns:
            View dict if found, otherwise None.
        """
        _ = base_id
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        view_data = raw_views.get(view_code)
        if view_data is None:
            return None
        normalized_codes = _normalize_object_codes(view_data.get("objects", []))
        view = View(
            viewCode=view_data.get("view_id", view_code),
            viewName=view_data.get("view_name", ""),
            description=view_data.get("description"),
            objectCodes=normalized_codes,
            properties=[
                ViewProperty(
                    propertyName=m.get("property_name", ""),
                    propertyCode=m.get("property_code", ""),
                    sourceObject=m.get("source_object_code", ""),
                    sourceObjectProperty=m.get("source_object_column_code", ""),
                )
                for m in view_data.get("mappings", [])
            ],
        )
        return view.model_dump(by_alias=True)

    def create_view(self, base_id: str, view: Any) -> Any:
        """Persist a new view via JsonEntityStore.

        Args:
            base_id: Base / project identifier.
            view: View dict or pydantic model.

        Returns:
            The saved view dict.

        Raises:
            ValueError: If view_code is missing or empty.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        view_dict: dict[str, Any] = (
            view if isinstance(view, dict) else view.model_dump(by_alias=True)
        )
        code: str = (
            view_dict.get("view_code")
            or view_dict.get("viewCode")
            or view_dict.get("view_id", "")
        )
        if not code:
            raise ValueError("view_code is required for view creation")
        entity_store.save("views", code, view_dict)
        self._incremental_save(entity_store, "views", code, view_dict)
        logger.info("Created view: base_id=%s view_code=%s", base_id, code)
        self._sync_entity_terms(
            entity_type="view",
            entity_code=code,
            entity_name=view_dict.get("viewName") or view_dict.get("view_name", code),
            entity_desc=view_dict.get("description", ""),
            base_id=base_id,
        )
        return view_dict

    def update_view(self, base_id: str, view_code: str, view: Any) -> Any:
        """Update an existing view.

        Args:
            base_id: Base / project identifier.
            view_code: Target view code.
            view: Updated View dict or pydantic model.

        Returns:
            The updated view dict.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        view_dict: dict[str, Any] = (
            view if isinstance(view, dict) else view.model_dump(by_alias=True)
        )
        entity_store.save("views", view_code, view_dict)
        self._incremental_save(entity_store, "views", view_code, view_dict)
        logger.info("Updated view: base_id=%s view_code=%s", base_id, view_code)
        self._remove_entity_terms(entity_type="view", entity_code=view_code)
        self._sync_entity_terms(
            entity_type="view",
            entity_code=view_code,
            entity_name=view_dict.get("viewName")
            or view_dict.get("view_name", view_code),
            entity_desc=view_dict.get("description", ""),
            base_id=base_id,
        )
        return view_dict

    def delete_view(self, base_id: str, view_code: str) -> None:
        """Delete a view.

        Args:
            base_id: Base / project identifier.
            view_code: Target view code.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        entity_store.delete("views", view_code)
        self._incremental_delete(entity_store, "views", view_code)
        logger.info("Deleted view: base_id=%s view_code=%s", base_id, view_code)
        self._remove_entity_terms(entity_type="view", entity_code=view_code)

    # ── Relation CRUD (stub — datacloud-data SDK does not yet support) ──────

    def get_relations(self, loader: Any, base_id: str) -> list[dict[str, Any]]:
        """Get all relations from the loaded ontology.

        Supports both OntologyRelation objects and raw dicts.
        Resolves sourceObjectName / targetObjectName from loader._classes.
        """
        raw_relations: list[Any] = getattr(loader, "_relations", None) or []
        result: list[dict[str, Any]] = []
        for r in raw_relations:
            if hasattr(r, "source_class"):
                src = r.source_class
                tgt = r.target_class
            elif isinstance(r, dict):
                src = r.get("source_class", "")
                tgt = r.get("target_class", "")
            else:
                continue
            src_name = ""
            tgt_name = ""
            src_cls = loader._classes.get(src)
            if src_cls is not None:
                src_name = src_cls.object_name
            tgt_cls = loader._classes.get(tgt)
            if tgt_cls is not None:
                tgt_name = tgt_cls.object_name

            if hasattr(r, "relation_code"):
                rel = Relation(
                    relationCode=r.relation_code,
                    relationName=getattr(r, "relation_name", None),
                    sourceObjectCode=src,
                    targetObjectCode=tgt,
                    relationCardinality=getattr(r, "relation_type", None),
                    sourceObjectName=src_name,
                    targetObjectName=tgt_name,
                    relationDesc=getattr(r, "relation_desc", None)
                    or getattr(r, "description", None),
                    relationSceneType=getattr(r, "relation_scene_type", None),
                )
            elif isinstance(r, dict):
                rel = Relation(
                    relationCode=r.get("relation_code", ""),
                    relationName=r.get("relation_name"),
                    sourceObjectCode=src,
                    targetObjectCode=tgt,
                    relationCardinality=r.get("relation_type"),
                    sourceObjectName=src_name,
                    targetObjectName=tgt_name,
                    relationDesc=r.get("relation_desc") or r.get("description"),
                    relationSceneType=r.get("relation_scene_type"),
                )
            else:
                continue
            result.append(rel.model_dump(by_alias=True))
        return result

    def get_relation_detail(
        self, loader: Any, base_id: str, rel_code: str
    ) -> dict[str, Any] | None:
        """Get single relation detail by code from the loaded ontology."""
        for r in self.get_relations(loader, base_id):
            if r.get("relationCode") == rel_code:
                return r
        return None

    def create_relation(self, base_id: str, rel: Any) -> Any:
        """Persist a new relation via JsonEntityStore.

        Args:
            base_id: Base / project identifier.
            rel: Relation dict or pydantic model.

        Returns:
            The saved relation dict.

        Raises:
            ValueError: If relation_code is missing or empty.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        rel_dict: dict[str, Any] = (
            rel if isinstance(rel, dict) else rel.model_dump(by_alias=True)
        )
        code: str = rel_dict.get("relation_code") or rel_dict.get("relationCode", "")
        if not code:
            raise ValueError("relation_code is required for relation creation")
        entity_store.save("relations", code, rel_dict)
        self._incremental_save(entity_store, "relations", code, rel_dict)
        from datacloud_platform.adapters.registry_sync import (  # noqa: PLC0415
            registry_sync_upsert,
            rel_camel_to_registry,
        )
        registry_sync_upsert(base_path, "relations", "relation_code", code, rel_camel_to_registry(rel_dict))
        logger.info("Created relation: base_id=%s relation_code=%s", base_id, code)
        self._sync_entity_terms(
            entity_type="relation",
            entity_code=code,
            entity_name=rel_dict.get("relationName")
            or rel_dict.get("relation_name", code),
            entity_desc=rel_dict.get("relationDesc") or rel_dict.get("description", ""),
            base_id=base_id,
        )
        return rel_dict

    def update_relation(self, base_id: str, rel_code: str, rel: Any) -> Any:
        """Update an existing relation.

        Args:
            base_id: Base / project identifier.
            rel_code: Target relation code.
            rel: Updated Relation dict or pydantic model.

        Returns:
            The updated relation dict.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        rel_dict: dict[str, Any] = (
            rel if isinstance(rel, dict) else rel.model_dump(by_alias=True)
        )
        entity_store.save("relations", rel_code, rel_dict)
        self._incremental_save(entity_store, "relations", rel_code, rel_dict)
        from datacloud_platform.adapters.registry_sync import (  # noqa: PLC0415
            registry_sync_upsert,
            rel_camel_to_registry,
        )
        registry_sync_upsert(base_path, "relations", "relation_code", rel_code, rel_camel_to_registry(rel_dict))
        logger.info("Updated relation: base_id=%s rel_code=%s", base_id, rel_code)
        self._remove_entity_terms(entity_type="relation", entity_code=rel_code)
        self._sync_entity_terms(
            entity_type="relation",
            entity_code=rel_code,
            entity_name=rel_dict.get("relationName")
            or rel_dict.get("relation_name", rel_code),
            entity_desc=rel_dict.get("relationDesc") or rel_dict.get("description", ""),
            base_id=base_id,
        )
        return rel_dict

    def delete_relation(self, base_id: str, rel_code: str) -> None:
        """Delete a relation.

        Args:
            base_id: Base / project identifier.
            rel_code: Target relation code.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        entity_store.delete("relations", rel_code)
        self._incremental_delete(entity_store, "relations", rel_code)
        from datacloud_platform.adapters.registry_sync import registry_sync_delete  # noqa: PLC0415
        registry_sync_delete(base_path, "relations", "relation_code", rel_code)
        logger.info("Deleted relation: base_id=%s rel_code=%s", base_id, rel_code)
        self._remove_entity_terms(entity_type="relation", entity_code=rel_code)

    # ── Action CRUD (stub — datacloud-data SDK does not yet support) ────────

    def get_actions(
        self, loader: Any, base_id: str, object_code: str
    ) -> list[dict[str, Any]]:
        """Get all actions for an object from the loaded ontology."""
        cls = loader._classes.get(object_code)
        if cls is None:
            return []
        return [
            Action(
                actionCode=a.action_code,
                actionName=a.action_name,
                actionType=a.action_type,
                belongObjectCode=a.belong_class,
                actionDesc=getattr(a, "description", None),
                requestUrl=getattr(a, "request_url", None),
                requestMethod=getattr(a, "request_method", None),
                params=[
                    ActionParam(
                        paramCode=p.param_code,
                        paramName=p.param_name,
                        paramType=getattr(p, "param_type", None),
                        isRequired=1 if p.required else 0,
                        direction=getattr(p, "direction", None),
                        mappingPath=getattr(p, "mapping_path", None),
                    )
                    for p in getattr(a, "params", [])
                ],
            ).model_dump(by_alias=True)
            for a in getattr(cls, "actions", [])
        ]

    def get_action_detail(
        self, loader: Any, base_id: str, object_code: str, action_code: str
    ) -> dict[str, Any] | None:
        """Get single action detail by code from the loaded ontology."""
        for a in self.get_actions(loader, base_id, object_code):
            if a.get("actionCode") == action_code:
                return a
        return None

    def create_action(self, base_id: str, object_code: str, action: Any) -> Any:
        """Persist a new action under an object via JsonEntityStore.

        Args:
            base_id: Base / project identifier.
            object_code: Parent object code.
            action: Action dict or pydantic model.

        Returns:
            The saved action dict.

        Raises:
            ValueError: If action_code is missing or empty.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        action_dict: dict[str, Any] = (
            action if isinstance(action, dict) else action.model_dump(by_alias=True)
        )
        code: str = action_dict.get("action_code") or action_dict.get("actionCode", "")
        if not code:
            raise ValueError("action_code is required for action creation")
        # Ensure parent object_code is recorded
        action_dict["belongObjectCode"] = object_code
        entity_store.save("actions", code, action_dict)
        self._incremental_save(entity_store, "actions", code, action_dict)
        logger.info(
            "Created action: base_id=%s object_code=%s action_code=%s",
            base_id,
            object_code,
            code,
        )
        self._sync_entity_terms(
            entity_type="ontology_action",
            entity_code=code,
            entity_name=action_dict.get("actionName")
            or action_dict.get("action_name", code),
            entity_desc=action_dict.get("actionDesc")
            or action_dict.get("description", ""),
            base_id=base_id,
        )
        return action_dict

    def update_action(
        self,
        base_id: str,
        object_code: str,
        action_code: str,
        action: Any,
    ) -> Any:
        """Update an existing action.

        Args:
            base_id: Base / project identifier.
            object_code: Parent object code.
            action_code: Target action code.
            action: Updated Action dict or pydantic model.

        Returns:
            The updated action dict.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        action_dict: dict[str, Any] = (
            action if isinstance(action, dict) else action.model_dump(by_alias=True)
        )
        action_dict["belongObjectCode"] = object_code
        entity_store.save("actions", action_code, action_dict)
        self._incremental_save(entity_store, "actions", action_code, action_dict)
        logger.info(
            "Updated action: base_id=%s object_code=%s action_code=%s",
            base_id,
            object_code,
            action_code,
        )
        self._remove_entity_terms(
            entity_type="ontology_action", entity_code=action_code
        )
        self._sync_entity_terms(
            entity_type="ontology_action",
            entity_code=action_code,
            entity_name=action_dict.get("actionName")
            or action_dict.get("action_name", action_code),
            entity_desc=action_dict.get("actionDesc")
            or action_dict.get("description", ""),
            base_id=base_id,
        )
        return action_dict

    def delete_action(self, base_id: str, object_code: str, action_code: str) -> None:
        """Delete an action.

        Args:
            base_id: Base / project identifier.
            object_code: Parent object code.
            action_code: Target action code.
        """
        _ = object_code  # stored entity keyed by action_code; object_code is context only
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        entity_store.delete("actions", action_code)
        self._incremental_delete(entity_store, "actions", action_code)
        logger.info(
            "Deleted action: base_id=%s object_code=%s action_code=%s",
            base_id,
            object_code,
            action_code,
        )
        self._remove_entity_terms(
            entity_type="ontology_action", entity_code=action_code
        )

    # ── Datasource CRUD ────────────────────────────────────────────────────

    def get_datasources(self, loader: Any, base_id: str) -> list[dict[str, Any]]:
        """Get all datasources from the loaded ontology.

        Scans all classes in the loader, collects unique dbId values from
        field definitions, and wraps them as Datasource dicts.

        Args:
            loader: An OntologyQueryable with _classes populated.
            base_id: Base / project identifier.

        Returns:
            List of Datasource dicts (alias-mapped).
        """
        _ = base_id
        used_db_ids: set[str] = set()
        for cls in loader._classes.values():
            db_id: str = getattr(cls, "datasource_alias", "") or ""
            if db_id:
                used_db_ids.add(db_id)

        dbs: list[DbConnection] = []
        for db_id in sorted(used_db_ids):
            dbs.append(
                DbConnection(
                    dbId=db_id,
                    dbCode=db_id,
                    dbType="",
                    dbParams={},
                )
            )
        if not dbs:
            return []
        return [Datasource(db=dbs).model_dump(by_alias=True)]

    def get_datasource_detail(
        self, loader: Any, base_id: str, db_id: str
    ) -> dict[str, Any] | None:
        """Get single datasource detail by db_id from the loaded ontology.

        Args:
            loader: An OntologyQueryable with _classes populated.
            base_id: Base / project identifier.
            db_id: Database identifier to look up.

        Returns:
            Datasource dict if found, otherwise None.
        """
        _ = base_id
        used_db_ids: set[str] = set()
        for cls in loader._classes.values():
            for f in cls.fields:
                field_db_id: str = getattr(f, "db", "") or ""
                if field_db_id:
                    used_db_ids.add(field_db_id)

        if db_id not in used_db_ids:
            return None

        db_conn = DbConnection(
            dbId=db_id,
            dbCode=db_id,
            dbType="",
            dbParams={},
        )
        return Datasource(db=[db_conn]).model_dump(by_alias=True)

    def create_datasource(self, base_id: str, ds: Any) -> Any:
        """Persist a new datasource via JsonEntityStore.

        Args:
            base_id: Base / project identifier.
            ds: Datasource dict or pydantic model.

        Returns:
            The saved datasource dict.

        Raises:
            ValueError: If db_id is missing or empty.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        ds_dict: dict[str, Any] = (
            ds if isinstance(ds, dict) else ds.model_dump(by_alias=True)
        )
        # Datasource wraps a list of DbConnection; extract first db_id
        db_list: list[dict[str, Any]] = ds_dict.get("db", [])
        db_id = ""
        if db_list:
            db_id = db_list[0].get("dbId", db_list[0].get("db_id", ""))
        if not db_id:
            raise ValueError("db_id is required for datasource creation")
        entity_store.save("datasources", db_id, ds_dict)
        self._incremental_save(entity_store, "datasources", db_id, ds_dict)
        logger.info("Created datasource: base_id=%s db_id=%s", base_id, db_id)
        return ds_dict

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Delete a datasource.

        Args:
            base_id: Base / project identifier.
            db_id: Target database identifier.
        """
        base_path = self._resolve_base_path(base_id)
        entity_store = JsonEntityStore(base_path)
        entity_store.delete("datasources", db_id)
        self._incremental_delete(entity_store, "datasources", db_id)
        logger.info("Deleted datasource: base_id=%s db_id=%s", base_id, db_id)

    # ── Term sync helpers (called by CRUD methods) ─────────────────────────

    @staticmethod
    def _extract_fields_from_entity(
        entity_type: str, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extract field dicts for term sync, typed by entity kind."""
        if entity_type == "object":
            raw_props: list[dict[str, Any]] = data.get("properties", []) or []
            return [
                {
                    "property_code": (
                        p.get("propertyCode") or p.get("property_code", "")
                    ),
                    "property_name": (
                        p.get("propertyName") or p.get("property_name", "")
                    ),
                    "data_type": p.get("dataType", "STRING"),
                }
                for p in raw_props
            ]
        if entity_type == "view":
            raw_mappings: list[dict[str, Any]] = (
                data.get("properties") or data.get("mappings") or []
            )
            return [
                {
                    "property_code": (
                        m.get("propertyCode") or m.get("property_code", "")
                    ),
                    "property_name": (
                        m.get("propertyName") or m.get("property_name", "")
                    ),
                }
                for m in raw_mappings
            ]
        if entity_type == "action":
            raw_params: list[dict[str, Any]] = data.get("params", []) or []
            return [
                {
                    "property_code": (p.get("paramCode") or p.get("param_code", "")),
                    "property_name": (p.get("paramName") or p.get("param_name", "")),
                }
                for p in raw_params
            ]
        # relation — no sub-fields
        return []

    # ── Term type mapping (entity_type → knowledge DB term_type_code) ───
    _TERM_TYPE_MAP: dict[str, str] = {
        "object": "object",
        "view": "view",
        "relation": "relation",
        "action": "ontology_action",
    }

    @staticmethod
    def _batch_sync_entity_terms(
        objects: list[dict[str, Any]],
        views: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> None:
        """Batch-upsert entity terms then backfill vectors in a single batch.

        1. Opens one writer, upserts all terms with ``backfill_vectors=False``.
        2. Collects all created/updated term_ids.
        3. After commit, spawns a daemon thread to run ``backfill_tsvector``
           and ``backfill_embeddings(term_ids=...)`` — leveraging the
           embedding model's batch API (``batch_size=50``) instead of N
           individual calls.

        Failures are logged but do not block the import.
        """
        try:
            from datacloud_knowledge.adapters import (  # noqa: PLC0415
                backfill_embeddings,
                backfill_tsvector,
                create_writer,
            )
        except ImportError:
            logger.debug(
                "_batch_sync_entity_terms skipped (datacloud_knowledge unavailable)"
            )
            return

        entities: list[tuple[str, str, str]] = []
        for obj in objects:
            code = obj.get("object_code", "")
            name = obj.get("object_name", "")
            if code and name:
                entities.append(("object", code, name))
        for view in views:
            code = (
                view.get("view_code", view.get("viewCode", view.get("view_id", "")))
                or ""
            )
            name = view.get("view_name", "")
            if code and name:
                entities.append(("view", code, name))
        for rel in relations:
            code = rel.get("relation_code", rel.get("relationCode", "")) or ""
            name = rel.get("relation_name", "")
            if code and name:
                entities.append(("relation", code, name))
        for act in actions:
            code = act.get("action_code", act.get("actionCode", "")) or ""
            name = act.get("action_name", "")
            if code and name:
                entities.append(("action", code, name))

        if not entities:
            return

        term_type_map = {
            "object": "object",
            "view": "view",
            "relation": "relation",
            "action": "ontology_action",
        }
        term_ids: list[str] = []
        try:
            with create_writer() as writer:
                for entity_type, entity_code, entity_name in entities:
                    try:
                        term_id = writer.upsert_term(
                            term_code=entity_code,
                            term_name=entity_name,
                            term_type_code=term_type_map[entity_type],
                            backfill_vectors=False,
                        )
                        if term_id:
                            term_ids.append(term_id)
                    except Exception:
                        logger.exception(
                            "_batch_sync_entity_terms: type=%s code=%s failed",
                            entity_type,
                            entity_code,
                        )
        except Exception:
            logger.exception("_batch_sync_entity_terms: batch upsert failed")
            return

        logger.info("_batch_sync_entity_terms: upserted %d terms", len(term_ids))

        if not term_ids:
            return

        # Defer vector backfill to background thread — batch API call
        def _backfill() -> None:
            try:
                backfill_tsvector()
            except Exception:
                logger.exception("_batch_sync_entity_terms: tsvector backfill failed")
            try:
                backfill_embeddings(term_ids=term_ids, batch_size=50)
            except Exception:
                logger.exception("_batch_sync_entity_terms: embeddings backfill failed")

        threading.Thread(target=_backfill, daemon=True).start()

    def _sync_entity_terms(
        self,
        *,
        entity_type: str,
        entity_code: str,
        entity_name: str,
        entity_desc: str = "",
        fields: list[dict[str, Any]] | None = None,
        base_id: str = "",
        domain_codes: tuple[str, ...] | None = None,
    ) -> None:
        """Write entity term into knowledge DB via ``create_writer``.

        Calls ``upsert_term`` (with explicit term_code=entity_code) and
        ``create_term_name`` internally.  tsvector + embedding backfill
        runs in a daemon thread (best-effort, non-blocking).

        ``domain_ids`` defaults to empty; scene membership is managed by
        ``_sync_entity_domains`` / ``_remove_entity_domains``.
        """
        _ = entity_desc, fields
        try:
            from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

            term_type_code = self._TERM_TYPE_MAP.get(entity_type, entity_type)
            domains = list(domain_codes) if domain_codes else []

            with create_writer() as writer:
                writer.upsert_term(
                    term_code=entity_code,
                    term_name=entity_name,
                    term_type_code=term_type_code,
                    library_id=base_id or None,
                    domain_ids=domains,
                    search_scope={"base": base_id} if base_id else {},
                    backfill_vectors=True,
                )
            logger.info(
                "_sync_entity_terms: type=%s term_type=%s code=%s done",
                entity_type,
                term_type_code,
                entity_code,
            )
        except ImportError:
            logger.debug(
                "_sync_entity_terms skipped (datacloud_knowledge unavailable): "
                "type=%s code=%s",
                entity_type,
                entity_code,
            )
        except Exception:
            logger.exception(
                "_sync_entity_terms failed: type=%s code=%s", entity_type, entity_code
            )

    def _remove_entity_terms(self, *, entity_type: str, entity_code: str) -> None:
        """Remove entity terms from knowledge DB on delete/update.

        Uses the standalone ``delete_scope`` function (reader/writer
        agnostic) for cascading delete of term + name + relation + knowledge.
        """
        try:
            from datacloud_knowledge.adapters import delete_scope  # noqa: PLC0415

            scope = f"{entity_type}:{entity_code}"
            delete_scope(scope)
            logger.info(
                "_remove_entity_terms: type=%s code=%s done", entity_type, entity_code
            )
        except ImportError:
            logger.debug(
                "_remove_entity_terms skipped (datacloud_knowledge unavailable): "
                "type=%s code=%s",
                entity_type,
                entity_code,
            )
        except Exception:
            logger.exception(
                "_remove_entity_terms failed: type=%s code=%s",
                entity_type,
                entity_code,
            )

    def _sync_entity_domains(
        self,
        base_id: str,
        scene_id: str,
        entity_type: str,
        entity_codes: list[str],
    ) -> None:
        """Called by add_scene_members — merges scene_id into term.domain_ids.

        Reads the existing term by ``term_code = entity_code``, merges
        ``scene_id`` into its domain_ids set, and writes the merged list
        back via ``update_term``.  Existing scene IDs are preserved.
        """
        if not entity_codes:
            return
        try:
            from datacloud_knowledge.adapters import create_reader, create_writer  # noqa: PLC0415
            from datacloud_knowledge.contracts.term_provider_types import (  # noqa: PLC0415
                TermUpdate,
            )

            reader = create_reader()
            with create_writer() as writer:
                for entity_code in entity_codes:
                    try:
                        terms = reader.get_terms_batch_raw(term_codes=[entity_code])
                        if not terms:
                            logger.warning(
                                "_sync_entity_domains: term not found for code=%s",
                                entity_code,
                            )
                            continue
                        term_id = str(terms[0].get("term_id", ""))
                        if not term_id:
                            continue
                        current_domains: list[str] = terms[0].get("domain_ids") or []
                        merged = list({*current_domains, scene_id})
                        writer.update_term(
                            dataset_id=base_id,
                            term_id=term_id,
                            updates=TermUpdate(domain_ids=merged),
                        )
                        logger.info(
                            "_sync_entity_domains: type=%s code=%s scene=%s domains=%s done",
                            entity_type,
                            entity_code,
                            scene_id,
                            merged,
                        )
                    except Exception:
                        logger.exception(
                            "_sync_entity_domains: failed for code=%s, "
                            "rolling back entire batch",
                            entity_code,
                        )
                        raise
                # commit handled by context manager exit
        except ImportError:
            logger.debug(
                "_sync_entity_domains skipped (datacloud_knowledge unavailable)"
            )
        except Exception:
            logger.exception(
                "_sync_entity_domains failed: type=%s scene=%s",
                entity_type,
                scene_id,
            )

    def _remove_entity_domains(
        self,
        base_id: str,
        scene_id: str,
        entity_type: str,
        entity_codes: list[str],
    ) -> None:
        """Called by remove_scene_members — removes scene_id from term.domain_ids.

        Reads the existing term by ``term_code = entity_code``, removes
        ``scene_id`` from its domain_ids set, and writes the result back
        via ``update_term``.  Other scene IDs are preserved.
        """
        if not entity_codes:
            return
        try:
            from datacloud_knowledge.adapters import create_reader, create_writer  # noqa: PLC0415
            from datacloud_knowledge.contracts.term_provider_types import (  # noqa: PLC0415
                TermUpdate,
            )

            reader = create_reader()
            with create_writer() as writer:
                for entity_code in entity_codes:
                    try:
                        terms = reader.get_terms_batch_raw(term_codes=[entity_code])
                        if not terms:
                            logger.warning(
                                "_remove_entity_domains: term not found for code=%s",
                                entity_code,
                            )
                            continue
                        term_id = str(terms[0].get("term_id", ""))
                        if not term_id:
                            continue
                        current_domains: list[str] = terms[0].get("domain_ids") or []
                        updated = [d for d in current_domains if d != scene_id]
                        writer.update_term(
                            dataset_id=base_id,
                            term_id=term_id,
                            updates=TermUpdate(domain_ids=updated),
                        )
                        logger.info(
                            "_remove_entity_domains: type=%s code=%s scene=%s domains=%s done",
                            entity_type,
                            entity_code,
                            scene_id,
                            updated,
                        )
                    except Exception:
                        logger.exception(
                            "_remove_entity_domains: failed for code=%s, "
                            "rolling back entire batch",
                            entity_code,
                        )
                        raise
                # commit handled by context manager exit
        except ImportError:
            logger.debug(
                "_remove_entity_domains skipped (datacloud_knowledge unavailable)"
            )
        except Exception:
            logger.exception(
                "_remove_entity_domains failed: type=%s scene=%s",
                entity_type,
                scene_id,
            )
