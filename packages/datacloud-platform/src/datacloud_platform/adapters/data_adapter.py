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

from datacloud_platform.models import ObjectSummary, ParsedOwlContent, StoredFile
from datacloud_platform.models.action import Action, ActionParam
from datacloud_platform.models.datasource import Datasource, DbConnection
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.property import Property
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View, ViewProperty

logger = logging.getLogger(__name__)

_STORAGE_DIR_ENV = "DATACLOUD_STORAGE_DIR"
_DEFAULT_STORAGE_DIR = ".datacloud_results"
_SCENES_FILE_ENV = "DATACLOUD_SCENE_REGISTRY_PATH"
_DEFAULT_SCENES_FILE = ".datacloud/scenes.json"


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

    def __init__(self) -> None:
        self._scenes: dict[str, dict[str, Any]] | None = None  # lazy loaded

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

    def load_ontology(self, base_path: Path) -> OntologyQueryable:
        """Load parsed ontology directory into a queryable runtime object.

        Args:
            base_path: Path to the OWL resource directory root.

        Returns:
            An OntologyLoader instance that satisfies OntologyQueryable.
        """
        from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415

        loader = OntologyLoader()
        if base_path.exists():
            loader.load_from_owl_resource_directory(str(base_path))
        return loader  # type: ignore[no-any-return]

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
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Object creation not supported via datacloud-data SDK")

    def update_object(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Object update not supported via datacloud-data SDK")

    def delete_object(self, base_id: str, object_code: str) -> None:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Object deletion not supported via datacloud-data SDK")

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
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("View creation not supported via datacloud-data SDK")

    def update_view(self, base_id: str, view_code: str, view: Any) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("View update not supported via datacloud-data SDK")

    def delete_view(self, base_id: str, view_code: str) -> None:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("View deletion not supported via datacloud-data SDK")

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
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Relation creation not supported via datacloud-data SDK")

    def update_relation(self, base_id: str, rel_code: str, rel: Any) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Relation update not supported via datacloud-data SDK")

    def delete_relation(self, base_id: str, rel_code: str) -> None:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Relation deletion not supported via datacloud-data SDK")

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
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Action creation not supported via datacloud-data SDK")

    def update_action(
        self,
        base_id: str,
        object_code: str,
        action_code: str,
        action: Any,
    ) -> Any:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Action update not supported via datacloud-data SDK")

    def delete_action(self, base_id: str, object_code: str, action_code: str) -> None:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError("Action deletion not supported via datacloud-data SDK")

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
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError(
            "Datasource creation not supported via datacloud-data SDK"
        )

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Raise PermissionError — write operations not supported via SDK."""
        raise PermissionError(
            "Datasource deletion not supported via datacloud-data SDK"
        )

    # ── Scene management ──────────────────────────────────────────────────

    def _scenes_file(self) -> Path:
        """Resolve scenes JSON file path from env or default."""
        env_path = os.getenv(_SCENES_FILE_ENV)
        if env_path:
            return Path(env_path)
        return Path(_DEFAULT_SCENES_FILE)

    def _ensure_scenes_loaded(self) -> dict[str, dict[str, Any]]:
        """Lazy-load scenes from JSON file into in-memory dict."""
        if self._scenes is not None:
            return self._scenes
        file_path = self._scenes_file()
        if file_path.exists():
            try:
                raw = _json.loads(file_path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    self._scenes = {s["scene_id"]: s for s in raw}
                else:
                    self._scenes = {}
            except Exception:
                logger.warning(
                    "Failed to load scenes from %s", file_path, exc_info=True
                )
                self._scenes = {}
        else:
            self._scenes = {}
        return self._scenes

    def _save_scenes(self) -> None:
        """Persist in-memory scenes to JSON file."""
        if self._scenes is None:
            return
        file_path = self._scenes_file()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        data = list(self._scenes.values())
        file_path.write_text(
            _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Saved %d scenes to %s", len(data), file_path)

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
        """Query ontologies (objects) in a scene with pagination and keyword filter.

        Looks up the scene's member_object_codes from the local scene registry,
        fetches matching ObjectSummary from *loader*._classes, applies optional
        keyword filter, and paginates the result.
        """
        # 1. Look up scene member codes
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            return {"data": [], "totalCount": 0}

        member_obj_codes: list[str] = scene.get("member_object_codes", [])
        if not member_obj_codes:
            return {"data": [], "totalCount": 0}

        # 2. Convert member codes to ObjectSummary dicts via loader
        all_objects: list[dict[str, Any]] = []
        for code in member_obj_codes:
            cls = loader._classes.get(code)
            if cls is not None:
                summary = self._to_summary(cls)
                all_objects.append(dataclasses.asdict(summary))

        # 3. Keyword filter (case-insensitive on object_code / object_name / description)
        if keyword:
            kw = keyword.strip().lower()
            all_objects = [
                o
                for o in all_objects
                if kw in (o.get("object_name", "") or "").lower()
                or kw in (o.get("object_code", "") or "").lower()
                or kw in (o.get("description", "") or "").lower()
            ]

        # 4. Paginate
        total = len(all_objects)
        start = (page - 1) * page_size
        page_data = all_objects[start : start + page_size]

        return {"data": page_data, "totalCount": total}

    # ── Scene CRUD ────────────────────────────────────────────────────────

    def _generate_scene_id(self) -> str:
        """Generate a unique scene ID."""
        return f"scene_{uuid.uuid4().hex[:12]}"

    def create_scene(self, base_id: str, scene: Any) -> dict[str, Any]:
        """Create a scene (grouping container) with local JSON persistence.

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
        self._save_scenes()
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

        self._save_scenes()
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
        self._save_scenes()
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
        self._save_scenes()
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
        self._save_scenes()
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
    def _storage_dir() -> Path:
        """Resolve storage directory from env or default."""
        env_dir = os.getenv(_STORAGE_DIR_ENV)
        if env_dir:
            return Path(env_dir)
        return Path(_DEFAULT_STORAGE_DIR)
