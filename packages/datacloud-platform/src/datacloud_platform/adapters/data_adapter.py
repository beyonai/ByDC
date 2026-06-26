"""DataCloudDataBackend — OntologyBackend + StorageBackend via datacloud-data SDK."""

from __future__ import annotations

import dataclasses
import json as _json
import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyQueryable

from datacloud_platform.models import (
    ObjectSummary,
    ParsedOwlContent,
    StoredFile,
    ViewSummary,
)
from datacloud_platform.adapters.json_entity_store import JsonEntityStore
from datacloud_platform.ports.entity_store import EntityStore
from datacloud_platform.models.action import Action, ActionParam
from datacloud_platform.models.datasource import Datasource, DbConnection
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.property import Property
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View, ViewProperty
from datacloud_platform.platform_file_storage import atomic_write_json

logger = logging.getLogger(__name__)

_STORAGE_DIR_ENV = "DATACLOUD_STORAGE_DIR"
_DEFAULT_STORAGE_DIR = ".datacloud_results"


def _normalize_object_codes(raw_objects: list[Any]) -> list[str]:
    """Normalize view ``objects`` entries into a flat list of object codes.

    Each entry may be a plain ``str`` or a ``dict`` with an ``object_code`` key.
    """
    codes: list[str] = []
    for item in raw_objects:
        if isinstance(item, str):
            codes.append(item)
        elif isinstance(item, dict):
            code = item.get("object_code", "")
            if code:
                codes.append(code)
    return codes


class DataCloudDataBackend:
    """OntologyBackend + StorageBackend via datacloud-data SDK.

    Each method imports the concrete SDK class locally so the package
    does not hard-depend on datacloud-data at import time.
    """

    def __init__(self, entity_store: EntityStore | None = None) -> None:
        if entity_store is None:
            from datacloud_platform.adapters.json_entity_store import JsonEntityStore
            from datacloud_platform.platform_file_storage import _data_dir

            entity_store = JsonEntityStore(_data_dir())
        self._entity_store = entity_store
        self._scenes: dict[str, dict[str, Any]] | None = (
            None  # lazy loaded (entity_store path)
        )

    # ── OntologyBackend ────────────────────────────────────────────────────

    def parse_owl(self, directory: Path) -> ParsedOwlContent:
        """Parse OWL directory via OwlParser, return typed ParsedOwlContent.

        Args:
            directory: Path to the OWL resource directory.

        Returns:
            ParsedOwlContent with objects, views, relations lists.
        """
        from datacloud_data_sdk.ontology.owl_parser import OwlParser  # noqa: PLC0415

        raw: dict[str, Any] = OwlParser().parse_resource_directory(directory)
        return ParsedOwlContent(
            objects=list(raw.get("objects", [])),
            views=list(raw.get("views", [])),
            relations=list(raw.get("relations", [])),
        )

    def save_parsed_content(
        self, base_path: Path, parsed: ParsedOwlContent
    ) -> dict[str, int]:
        """Persist parsed OWL content as ``objects_registry.json`` + shard files.

        Writes a unified JSON registry for fast :meth:`load_ontology` loads and
        individual shard files for detail queries.  Rebuilds indexes for all
        three entity types on completion.

        Args:
            base_path: Root directory for the ontology base.
            parsed: Structured parse result from :meth:`parse_owl`.

        Returns:
            Counts dict with ``objects``, ``views``, ``relations`` keys.
        """
        entity_store = JsonEntityStore(base_path)

        counts: dict[str, int] = {"objects": 0, "views": 0, "relations": 0}

        # Write unified JSON registry (fast-load path)
        registry: dict[str, list[dict[str, Any]]] = {
            "objects": parsed.objects,
            "views": parsed.views,
            "relations": parsed.relations,
        }
        base_path.mkdir(parents=True, exist_ok=True)
        atomic_write_json(base_path / "objects_registry.json", registry)

        # Write per-object shard files
        for obj in parsed.objects:
            obj_code: str = obj.get("object_code", "") or ""
            if obj_code:
                entity_store.save("objects", obj_code, obj)
                counts["objects"] += 1

        # Write per-view shard files
        for view in parsed.views:
            v_code: str = (
                view.get("view_code", view.get("viewCode", view.get("view_id", "")))
                or ""
            )
            if v_code:
                entity_store.save("views", v_code, view)
                counts["views"] += 1

        # Write per-relation shard files
        for rel in parsed.relations:
            r_code: str = rel.get("relation_code", rel.get("relationCode", "")) or ""
            if r_code:
                entity_store.save("relations", r_code, rel)
                counts["relations"] += 1

        # Rebuild all indexes
        for et in ("objects", "views", "relations"):
            entity_store.save_index(et, entity_store.rebuild_index(et))

        logger.info(
            "save_parsed_content: %s objects=%d views=%d relations=%d",
            base_path,
            counts["objects"],
            counts["views"],
            counts["relations"],
        )
        return counts

    def load_ontology(self, base_path: Path) -> OntologyQueryable:
        """Load parsed ontology directory into a queryable runtime object.

        Prefers ``objects_registry.json`` (single file, < 1s) when available.
        Falls back to full OWL directory traversal for backwards compatibility.

        Args:
            base_path: Path to the OWL resource directory root.

        Returns:
            An OntologyLoader instance that satisfies OntologyQueryable.
        """
        from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415

        loader = OntologyLoader()

        # Fast path: unified JSON registry (Phase 2 output)
        registry = base_path / "objects_registry.json"
        if registry.exists():
            content = _json.loads(registry.read_text(encoding="utf-8"))
            loader.load_from_content(content)
            return loader  # type: ignore[return-value]

        # Fallback: old-format OWL directory traversal (~10s)
        if base_path.exists():
            loader.load_from_owl_resource_directory(str(base_path))
        return loader  # type: ignore[return-value]

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
        return TermLoader()  # type: ignore[abstract]

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
        logger.info("Created object: base_id=%s object_code=%s", base_id, code)
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
        logger.info("Updated object: base_id=%s object_code=%s", base_id, object_code)
        return obj_dict

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
        logger.info("Created relation: base_id=%s relation_code=%s", base_id, code)
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
        logger.info("Updated relation: base_id=%s rel_code=%s", base_id, rel_code)
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
        logger.info("Deleted relation: base_id=%s rel_code=%s", base_id, rel_code)

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

    # ── Scene management ──────────────────────────────────────────────────

    def _ensure_scenes_loaded(self) -> dict[str, dict[str, Any]]:
        """Lazy-load scenes from EntityStore into in-memory dict.

        Falls back to an empty dict when no EntityStore is configured.
        """
        if self._scenes is not None:
            return self._scenes
        if self._entity_store is not None:
            try:
                self._scenes = dict(self._entity_store.load_index("scenes"))
            except Exception:
                logger.warning("Failed to load scenes index", exc_info=True)
                self._scenes = {}
        else:
            self._scenes = {}
        return self._scenes

    def _save_scenes(self) -> None:
        """Persist in-memory scenes to EntityStore index atomically."""
        if self._scenes is None or self._entity_store is None:
            return
        self._entity_store.save_index("scenes", self._scenes)
        logger.info("Saved %d scenes to EntityStore", len(self._scenes))

    def _save_scene(self, scene_id: str, scene: dict[str, Any]) -> None:
        """Persist a single scene file and the index atomically."""
        if self._entity_store is not None:
            self._entity_store.save("scenes", scene_id, scene)
        self._save_scenes()

    def _delete_scene(self, scene_id: str) -> None:
        """Delete a single scene file and update the index."""
        if self._entity_store is not None:
            self._entity_store.delete("scenes", scene_id)
        self._save_scenes()

    def list_scenes(self, base_id: str) -> list[dict[str, Any]]:
        """Return all scenes under a base."""
        scenes = self._ensure_scenes_loaded()
        return [s for s in scenes.values() if s.get("base_id") == base_id]

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict[str, Any]]:
        """Query scenes with optional keyword filter on scene_name / scene_code."""
        all_scenes = self.list_scenes(base_id)
        if not keyword:
            return all_scenes
        kw = keyword.strip().lower()
        return [
            s
            for s in all_scenes
            if kw in str(s.get("scene_name", "")).lower()
            or kw in str(s.get("scene_code", "")).lower()
        ]

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        """Count scenes matching optional keyword filter."""
        return len(self.query_scenes(base_id, keyword))

    def get_scene_details(
        self,
        loader: Any,
        base_id: str,
        scene_id: str,
        *,
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get scene details with optional filtering by view_code / object_code.

        Filtering rules (aligning with external protocol):
        - No params: return all member objects + views.
        - view_code only: return matching views + objects referenced by those views.
        - object_code only: return matching objects, views = [].
        - Both: union of the two sets.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            return {
                "scene": None,
                "views": [],
                "objects": [],
                "actions": [],
                "relations": [],
                "dbsources": Datasource(db=[], doc=[], api=[]).model_dump(
                    by_alias=True
                ),
                "version": "v0.1.0",
            }

        member_obj_codes: list[str] = scene.get("member_object_codes", [])
        member_view_codes: list[str] = scene.get("member_view_codes", [])

        # Determine which objects/views to include based on filter params
        if view_code and not object_code:
            target_views = [vc for vc in member_view_codes if vc in view_code]
            target_objects = member_obj_codes
        elif object_code and not view_code:
            target_views = []
            target_objects = [oc for oc in member_obj_codes if oc in object_code]
        elif view_code and object_code:
            target_views = [vc for vc in member_view_codes if vc in view_code]
            target_objects_set: set[str] = set(object_code) | set(member_obj_codes)
            target_objects = list(target_objects_set)
        else:
            target_views = list(member_view_codes)
            target_objects = list(member_obj_codes)

        target_obj_set: set[str] = set(target_objects)

        # ── Extract objects from loader._classes ──
        objects: list[dict[str, Any]] = []
        for code in sorted(target_obj_set):
            cls = loader._classes.get(code)
            if cls is None:
                continue
            obj = ObjectType(
                objectCode=cls.object_code,
                objectName=cls.object_name,
                objectDesc=getattr(cls, "description", None),
                objectSource=getattr(cls, "source_type", None),
                conceptType=getattr(cls, "concept_type", None),
                baseId=scene.get("base_id", base_id),
                tableName=getattr(cls, "table_name", None),
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
            )
            objects.append(obj.model_dump(by_alias=True))

        # ── Extract actions from all matching objects ──
        actions: list[dict[str, Any]] = []
        for code in sorted(target_obj_set):
            cls = loader._classes.get(code)
            if cls is None:
                continue
            for a in cls.actions:
                act = Action(
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
                actions.append(act.model_dump(by_alias=True))

        # ── Extract views from loader._views ──
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        views: list[dict[str, Any]] = []
        for vc in target_views:
            view_data = raw_views.get(vc)
            if view_data is None:
                continue
            raw_objects = view_data.get("objects", [])
            normalized_codes = _normalize_object_codes(raw_objects)
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
            views.append(view.model_dump(by_alias=True))

        # ── Extract relations filtered by target objects ──
        raw_relations: list[Any] = getattr(loader, "_relations", None) or []
        relations: list[dict[str, Any]] = []
        for r in raw_relations:
            # r may be OntologyRelation or dict
            if hasattr(r, "source_class"):
                src = r.source_class
                tgt = r.target_class
            elif isinstance(r, dict):
                src = r.get("source_class", "")
                tgt = r.get("target_class", "")
            else:
                continue
            if src in target_obj_set and tgt in target_obj_set:
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
                relations.append(rel.model_dump(by_alias=True))

        # ── Build dbsources from object properties' dbId ──
        used_db_ids: set[str] = set()
        for obj_dict in objects:
            for prop in obj_dict.get("properties", []):
                db_id = prop.get("dbId")
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

        return {
            "scene": scene,
            "views": views,
            "objects": objects,
            "actions": actions,
            "relations": relations,
            "dbsources": Datasource(db=dbs).model_dump(by_alias=True),
            "version": "v0.1.0",
        }

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
        """Query ontologies (objects + views) in a scene with optional keyword filter.

        Looks up the scene's member_object_codes and member_view_codes from the
        local scene registry, fetches matching ObjectSummary / ViewSummary from
        *loader*, applies optional keyword filter, and returns both lists.
        """
        _ = page, page_size  # pagination removed — objects/views returned as full lists

        # 1. Look up scene member codes
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            return {"data": {"objects": [], "views": []}, "totalCount": 0}

        member_obj_codes: list[str] = scene.get("member_object_codes", [])
        member_view_codes: list[str] = scene.get("member_view_codes", [])

        # 2. Convert member codes to summaries via loader
        all_objects: list[dict[str, Any]] = []
        for code in member_obj_codes:
            cls = loader._classes.get(code)
            if cls is not None:
                summary = self._to_summary(cls)
                all_objects.append(dataclasses.asdict(summary))

        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        all_views: list[dict[str, Any]] = []
        for code in member_view_codes:
            view_data = raw_views.get(code)
            if view_data is not None:
                view_sum = self._to_view_summary(view_data, code)
                all_views.append(dataclasses.asdict(view_sum))

        # 3. Keyword filter (case-insensitive on name / code / description)
        if keyword:
            kw = keyword.strip().lower()
            all_objects = [
                o
                for o in all_objects
                if kw in (o.get("object_name", "") or "").lower()
                or kw in (o.get("object_code", "") or "").lower()
                or kw in (o.get("description", "") or "").lower()
            ]
            all_views = [
                v
                for v in all_views
                if kw in (v.get("view_name", "") or "").lower()
                or kw in (v.get("view_code", "") or "").lower()
                or kw in (v.get("description", "") or "").lower()
            ]

        # 4. Total count (objects + views)
        total = len(all_objects) + len(all_views)

        return {
            "data": {"objects": all_objects, "views": all_views},
            "totalCount": total,
        }

    # ── Scene CRUD ────────────────────────────────────────────────────────

    def _generate_scene_id(self) -> str:
        """Generate a unique scene ID."""
        return f"scene_{uuid.uuid4().hex[:12]}"

    def create_scene(self, base_id: str, scene: Any) -> dict[str, Any]:
        """Create a scene (grouping container) with EntityStore persistence.

        Args:
            base_id: Base / project identifier.
            scene: Scene-like object or dict with scene_name, scene_code, scene_desc.
        """
        scenes = self._ensure_scenes_loaded()

        # Extract fields from dict or object
        if isinstance(scene, dict):
            scene_name = scene.get("scene_name", scene.get("sceneName", ""))
            scene_code = scene.get("scene_code", scene.get("sceneCode"))
            scene_desc = scene.get("scene_desc", scene.get("sceneDesc"))
        else:
            scene_name = getattr(scene, "scene_name", "")
            scene_code = getattr(scene, "scene_code", None)
            scene_desc = getattr(scene, "scene_desc", None)

        scene_id = scene_code or self._generate_scene_id()

        if scene_id in scenes:
            raise ValueError(f"Scene already exists: {scene_id}")

        new_scene: dict[str, Any] = {
            "scene_id": scene_id,
            "scene_name": scene_name,
            "scene_code": scene_id,
            "scene_desc": scene_desc,
            "base_id": base_id,
            "member_object_codes": [],
            "member_view_codes": [],
        }
        scenes[scene_id] = new_scene
        self._save_scene(scene_id, new_scene)
        logger.info("Created scene: base_id=%s scene_id=%s", base_id, scene_id)
        return new_scene

    def update_scene(self, base_id: str, scene_id: str, updates: Any) -> dict[str, Any]:
        """Update scene metadata.

        Args:
            base_id: Base / project identifier.
            scene_id: Target scene ID.
            updates: Dict or object with scene_name / scene_desc fields to patch.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        if scene.get("base_id") != base_id:
            raise KeyError(f"Scene {scene_id} not owned by base {base_id}")

        if isinstance(updates, dict):
            if "scene_name" in updates or "sceneName" in updates:
                scene["scene_name"] = updates.get(
                    "scene_name", updates.get("sceneName")
                )
            if "scene_desc" in updates or "sceneDesc" in updates:
                scene["scene_desc"] = updates.get(
                    "scene_desc", updates.get("sceneDesc")
                )
        else:
            if hasattr(updates, "scene_name") and updates.scene_name is not None:
                scene["scene_name"] = updates.scene_name
            if hasattr(updates, "scene_desc") and updates.scene_desc is not None:
                scene["scene_desc"] = updates.scene_desc

        self._save_scene(scene_id, scene)
        logger.info("Updated scene: base_id=%s scene_id=%s", base_id, scene_id)
        return scene

    def delete_scene(self, base_id: str, scene_id: str) -> None:
        """Delete a scene — does NOT delete member resources.

        Only removes the grouping container. Member objects/views are unaffected.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            return
        if scene.get("base_id") != base_id:
            return
        del scenes[scene_id]
        self._delete_scene(scene_id)
        logger.info("Deleted scene: base_id=%s scene_id=%s", base_id, scene_id)

    # ── Scene member management ────────────────────────────────────────────

    def add_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> dict[str, Any]:
        """Add objects/views to a scene (idempotent — duplicates are ignored).

        Args:
            base_id: Base / project identifier.
            scene_id: Target scene ID.
            object_codes: Object codes to add as members.
            view_codes: View codes to add as members.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        if scene.get("base_id") != base_id:
            raise KeyError(f"Scene {scene_id} not owned by base {base_id}")

        existing_objs: set[str] = set(scene.get("member_object_codes", []))
        existing_views: set[str] = set(scene.get("member_view_codes", []))

        added_objs = [oc for oc in object_codes if oc not in existing_objs]
        added_views = [vc for vc in view_codes if vc not in existing_views]

        scene["member_object_codes"] = list(existing_objs | set(object_codes))
        scene["member_view_codes"] = list(existing_views | set(view_codes))
        self._save_scene(scene_id, scene)
        logger.info(
            "Added scene members: scene_id=%s objects=%d views=%d",
            scene_id,
            len(added_objs),
            len(added_views),
        )
        return scene

    def remove_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> dict[str, Any]:
        """Remove objects/views from a scene — does NOT delete resources.

        Args:
            base_id: Base / project identifier.
            scene_id: Target scene ID.
            object_codes: Object codes to remove from scene membership.
            view_codes: View codes to remove from scene membership.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        if scene.get("base_id") != base_id:
            raise KeyError(f"Scene {scene_id} not owned by base {base_id}")

        obj_set: set[str] = set(scene.get("member_object_codes", []))
        view_set: set[str] = set(scene.get("member_view_codes", []))

        obj_set.difference_update(object_codes)
        view_set.difference_update(view_codes)

        scene["member_object_codes"] = list(obj_set)
        scene["member_view_codes"] = list(view_set)
        self._save_scene(scene_id, scene)
        logger.info(
            "Removed scene members: scene_id=%s objects=%d views=%d",
            scene_id,
            len(object_codes),
            len(view_codes),
        )
        return scene

    # ── StorageBackend ─────────────────────────────────────────────────────

    def store_result(
        self, key: str, data: bytes, *, metadata: dict[str, Any] | None = None
    ) -> str:
        """Store result file bytes, returning a unique file_id.

        Args:
            key: Human-readable file key / name.
            data: Raw bytes to persist.
            metadata: Optional metadata dict (stored as a JSON sidecar).

        Returns:
            A UUID-based file_id for retrieval.
        """
        file_id = uuid.uuid4().hex
        store_dir = self._storage_dir()
        store_dir.mkdir(parents=True, exist_ok=True)

        data_path = store_dir / file_id
        data_path.write_bytes(data)

        if metadata:
            meta_path = store_dir / f"{file_id}.meta"
            meta_path.write_text(
                _json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
            )

        logger.info("Stored result file_id=%s key=%s size=%d", file_id, key, len(data))
        return file_id

    def get_result(self, file_id: str) -> bytes:
        """Get result file bytes by ID.

        Args:
            file_id: The file identifier returned by :meth:`store_result`.

        Returns:
            Raw bytes of the stored file.

        Raises:
            FileNotFoundError: If the file_id does not exist.
        """
        data_path = self._storage_dir() / file_id
        if not data_path.exists():
            raise FileNotFoundError(f"Result file not found: {file_id}")
        return data_path.read_bytes()

    def delete_result(self, file_id: str) -> None:
        """Delete a result file by ID.

        Args:
            file_id: The file identifier to delete.
        """
        data_path = self._storage_dir() / file_id
        meta_path = self._storage_dir() / f"{file_id}.meta"
        if data_path.exists():
            data_path.unlink()
        if meta_path.exists():
            meta_path.unlink()
        logger.info("Deleted result file_id=%s", file_id)

    def list_results(self, prefix: str = "") -> list[StoredFile]:
        """List stored result files, optionally filtered by prefix.

        Args:
            prefix: Optional key prefix filter.

        Returns:
            List of StoredFile summaries.
        """
        store_dir = self._storage_dir()
        if not store_dir.exists():
            return []

        files: list[StoredFile] = []
        for entry in sorted(store_dir.iterdir()):
            if entry.is_dir() or entry.suffix == ".meta":
                continue
            fid = entry.name
            if prefix and not fid.startswith(prefix):
                continue
            stat = entry.stat()
            files.append(
                StoredFile(
                    file_id=fid,
                    key=fid,
                    size_bytes=stat.st_size,
                    created_at=str(stat.st_ctime),
                )
            )
        return files

    # ── internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _resolve_base_path(base_id: str) -> Path:
        """Resolve a base_id to a filesystem path under the platform data dir.

        Uses ``DATACLOUD_DATA_DIR`` env var when set, otherwise ``~/.datacloud``.
        """
        from datacloud_platform.platform_file_storage import _data_dir

        return _data_dir() / base_id

    @staticmethod
    def _rebuild_index(
        entity_store: JsonEntityStore, entity_type: str
    ) -> dict[str, dict[str, Any]]:
        """Rebuild and persist the index for *entity_type* (full-scan, for batch use only).

        Prefer :meth:`_incremental_save` / :meth:`_incremental_delete` for
        single-entity CRUD operations to avoid O(n) scans.
        """
        idx = entity_store.rebuild_index(entity_type)
        entity_store.save_index(entity_type, idx)
        return idx

    @staticmethod
    def _incremental_save(
        entity_store: JsonEntityStore,
        entity_type: str,
        code: str,
        data: dict[str, Any],
    ) -> None:
        """Incrementally update a single entity in the index (O(1) read + O(1) write)."""
        from datacloud_platform.adapters.json_entity_store import _to_index_entry

        idx = entity_store.load_index(entity_type)
        idx[code] = _to_index_entry(data, entity_type)
        entity_store.save_index(entity_type, idx)

    @staticmethod
    def _incremental_delete(
        entity_store: JsonEntityStore,
        entity_type: str,
        code: str,
    ) -> None:
        """Incrementally remove a single entity from the index (O(1) read + O(1) write)."""
        idx = entity_store.load_index(entity_type)
        idx.pop(code, None)
        entity_store.save_index(entity_type, idx)

    @staticmethod
    def _to_summary(ont_class: object) -> ObjectSummary:
        """Convert an OntologyClass-like object to ObjectSummary.

        References the same attribute names as local_adapter._ontology_class_to_summary.
        """
        object_code: str = getattr(ont_class, "object_code", "")
        object_name: str = getattr(ont_class, "object_name", "")
        description: str = getattr(ont_class, "description", "")
        source_type: str = getattr(ont_class, "source_type", "")
        field_count: int = len(getattr(ont_class, "fields", []))
        action_count: int = len(getattr(ont_class, "actions", []))
        return ObjectSummary(
            object_code=object_code,
            object_name=object_name,
            description=description,
            object_source=source_type,
            field_count=field_count,
            action_count=action_count,
        )

    @staticmethod
    def _to_view_summary(view_data: dict[str, Any], view_code: str) -> ViewSummary:
        """Convert a raw view dict to ViewSummary."""
        normalized_codes = _normalize_object_codes(view_data.get("objects", []))
        return ViewSummary(
            view_code=view_data.get("view_id", view_code),
            view_name=view_data.get("view_name", ""),
            description=view_data.get("description", "") or "",
            object_codes=normalized_codes,
        )

    @staticmethod
    def _storage_dir() -> Path:
        """Resolve storage directory from env or default."""
        env_dir = os.getenv(_STORAGE_DIR_ENV)
        if env_dir:
            return Path(env_dir)
        return Path(_DEFAULT_STORAGE_DIR)
