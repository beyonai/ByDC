"""Scene management — list, query, CRUD, reverse lookup, member management."""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from datacloud_platform.adapters.data_adapter._base import (
    DataCloudDataBackendBase,
    _normalize_object_codes,
)
from datacloud_platform.models.action import Action, ActionParam
from datacloud_platform.models.datasource import Datasource, DbConnection
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.property import Property
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View, ViewProperty

logger = logging.getLogger(__name__)


class SceneMixin(DataCloudDataBackendBase):
    """Scene management — list, query, CRUD, reverse lookup, member management."""

    # ── Scene management ──────────────────────────────────────────────────

    def _ensure_scenes_loaded(self) -> dict[str, dict[str, Any]]:
        """Load scenes index, invalidating cache on mtime change (cross-process safe)."""
        if self._entity_store is None:
            self._scenes = {}
            return self._scenes
        current_version = self._entity_store.storage_version("scenes")
        if self._scenes is not None and self._scenes_version == current_version:
            return self._scenes
        try:
            self._scenes = dict(self._entity_store.load_index("scenes"))
            self._scenes_version = current_version
            self._reverse_index_built = False
        except Exception:
            logger.warning("Failed to load scenes index", exc_info=True)
            self._scenes = {}
            self._scenes_version = ""
        return self._scenes

    def _ensure_reverse_index(self) -> None:
        """Build reverse index from _scenes: object_code → {scene_ids}."""
        if self._reverse_index_built:
            return
        self._object_scene_map = {}
        self._view_scene_map = {}
        for sid, scene in (self._scenes or {}).items():
            for code in scene.get("member_object_codes", []):
                self._object_scene_map.setdefault(code, set()).add(sid)
            for code in scene.get("member_view_codes", []):
                self._view_scene_map.setdefault(code, set()).add(sid)
        self._reverse_index_built = True

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

    # ── Atomic ontology methods (used by get_scene_details) ──────────────

    def get_scene_members(
        self, base_id: str, scene_id: str
    ) -> tuple[list[str], list[str]]:
        """Return (object_codes, view_codes) for a scene — pure metadata query.

        Args:
            base_id: Base / project identifier.
            scene_id: Target scene ID.

        Returns:
            Tuple of (member_object_codes, member_view_codes). Empty lists if scene
            not found.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            return ([], [])
        return (
            list(scene.get("member_object_codes", [])),
            list(scene.get("member_view_codes", [])),
        )

    def extract_objects_detail(
        self, base_id: str, loader: Any, object_codes: list[str]
    ) -> list[dict[str, Any]]:
        """Extract ObjectType JSON for each code from loader._classes.

        Args:
            base_id: Base / project identifier (used as baseId in each object).
            loader: An OntologyQueryable with _classes populated.
            object_codes: Object codes to extract detail for.

        Returns:
            List of ObjectType dicts (by_alias=True), without actions.
        """
        objects: list[dict[str, Any]] = []
        for code in object_codes:
            cls = loader._classes.get(code)
            if cls is None:
                continue
            obj = ObjectType(
                objectCode=cls.object_code,
                objectName=cls.object_name,
                objectDesc=getattr(cls, "description", None),
                objectSource=getattr(cls, "source_type", None),
                conceptType=getattr(cls, "concept_type", None),
                ownerType=getattr(cls, "owner_type", "enterprise"),
                userCode=getattr(cls, "user_code", None),
                baseId=base_id,
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
        return objects

    def extract_views_detail(
        self, base_id: str, loader: Any, view_codes: list[str]
    ) -> list[dict[str, Any]]:
        """Extract View JSON for each code from loader._views.

        Args:
            base_id: Base / project identifier.
            loader: An OntologyQueryable with _views populated.
            view_codes: View codes to extract detail for.

        Returns:
            List of View dicts (by_alias=True).
        """
        _ = base_id
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        views: list[dict[str, Any]] = []
        for vc in view_codes:
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
                ownerType=view_data.get(
                    "owner_type", view_data.get("ownerType", "enterprise")
                ),
                userCode=view_data.get("user_code", view_data.get("userCode")),
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
        return views

    def extract_relations(
        self, base_id: str, loader: Any, object_codes_set: set[str]
    ) -> list[dict[str, Any]]:
        """Extract bidirectional Relation JSON where both ends are in object_codes_set.

        Args:
            base_id: Base / project identifier.
            loader: An OntologyQueryable with _relations and _classes populated.
            object_codes_set: Only relations where both source and target are in this set
                are included.

        Returns:
            List of Relation dicts (by_alias=True).
        """
        _ = base_id
        raw_relations: list[Any] = getattr(loader, "_relations", None) or []
        relations: list[dict[str, Any]] = []
        for r in raw_relations:
            if hasattr(r, "source_class"):
                src = r.source_class
                tgt = r.target_class
            elif isinstance(r, dict):
                src = r.get("source_class", "")
                tgt = r.get("target_class", "")
            else:
                continue
            if src not in object_codes_set or tgt not in object_codes_set:
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
                    ownerType=getattr(r, "owner_type", "enterprise"),
                    userCode=getattr(r, "user_code", None),
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
                    ownerType=r.get("owner_type", r.get("ownerType", "enterprise")),
                    userCode=r.get("user_code") or r.get("userCode"),
                )
            else:
                continue
            relations.append(rel.model_dump(by_alias=True))
        return relations

    def get_term_scope_info(self, base_id: str, object_code: str) -> dict[str, Any]:
        """Return {library_id, scene_id} identifying which scene contains object_code.

        Searches all scenes under *base_id* for one that lists *object_code* as a member.
        Returns the first match found.

        Args:
            base_id: Base / project identifier.
            object_code: Object code to look up.

        Returns:
            Dict with ``library_id`` (str) and ``scene_id`` (str, empty if not found).
        """
        scenes = self._ensure_scenes_loaded()
        for scene in scenes.values():
            if scene.get("base_id") != base_id:
                continue
            if object_code in scene.get("member_object_codes", []):
                return {
                    "library_id": "PERSONAL_LIB",
                    "scene_id": scene.get("scene_id", ""),
                }
        return {"library_id": "PERSONAL_LIB", "scene_id": ""}

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
        member_obj_codes, member_view_codes = self.get_scene_members(base_id, scene_id)

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

        # Determine which objects/views to include based on filter params
        if view_code and not object_code:
            target_views = [vc for vc in member_view_codes if vc in view_code]
            target_objects = member_obj_codes
        elif object_code and not view_code:
            target_views = []
            target_objects = [oc for oc in member_obj_codes if oc in object_code]
        elif view_code and object_code:
            target_views = [vc for vc in member_view_codes if vc in view_code]
            target_objects = list(set(object_code) | set(member_obj_codes))
        else:
            target_views = list(member_view_codes)
            target_objects = list(member_obj_codes)

        target_obj_set = set(target_objects)

        # Use atomic methods for extraction
        scene_base_id: str = scene.get("base_id", base_id)
        objects = self.extract_objects_detail(
            scene_base_id, loader, sorted(target_obj_set)
        )
        views = self.extract_views_detail(base_id, loader, target_views)
        relations = self.extract_relations(base_id, loader, target_obj_set)

        # Extract actions from matching objects
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
                    ownerType=getattr(a, "owner_type", "enterprise"),
                    userCode=getattr(a, "user_code", None),
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

        # Build dbsources from object properties' dbId
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
        type: str | None = None,
        owner_type: str | None = None,
        cross_scene: bool = False,
    ) -> dict[str, Any]:
        """Query ontologies (objects + views) with pagination, type, and owner_type filters.

        Supports cross-scene mode: when scene_id is empty and cross_scene=True,
        iterates all scenes and collects all member codes.
        """
        # 1. Collect member codes (single scene, cross-scene, or all)
        member_obj_codes: set[str] = set()
        member_view_codes: set[str] = set()
        scenes = self._ensure_scenes_loaded()
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}

        if not scene_id and cross_scene:
            # Cross-scene: query ALL objects/views in the base (including orphans
            # without scene membership), not just scene members.
            member_obj_codes.update(loader._classes.keys())
            member_view_codes.update(raw_views.keys())
        else:
            found = scenes.get(scene_id)
            if found is None:
                return {
                    "data": {"objects": [], "views": []},
                    "totalCount": 0,
                    "page": page,
                    "pageSize": page_size,
                }
            member_obj_codes.update(found.get("member_object_codes", []))
            member_view_codes.update(found.get("member_view_codes", []))

        # 2. Convert member codes to summaries via loader
        all_objects: list[dict[str, Any]] = []
        for code in member_obj_codes:
            cls = loader._classes.get(code)
            if cls is not None:
                summary = self._to_summary(cls)
                summary_dict = dataclasses.asdict(summary)

                # owner_type filter
                if owner_type and summary.owner_type != owner_type:
                    continue

                # keyword filter
                if keyword:
                    kw = keyword.strip().lower()
                    if (
                        kw not in (summary.object_name or "").lower()
                        and kw not in summary.object_code.lower()
                        and kw not in (summary.description or "").lower()
                    ):
                        continue

                all_objects.append(summary_dict)

        all_views: list[dict[str, Any]] = []
        for code in member_view_codes:
            view_data = raw_views.get(code)
            if view_data is not None:
                view_sum = self._to_view_summary(view_data, code)
                summary_dict = dataclasses.asdict(view_sum)

                # owner_type filter
                if owner_type and view_sum.owner_type != owner_type:
                    continue

                # keyword filter
                if keyword:
                    kw = keyword.strip().lower()
                    if (
                        kw not in (view_sum.view_name or "").lower()
                        and kw not in (view_sum.view_code or "").lower()
                        and kw not in (view_sum.description or "").lower()
                    ):
                        continue

                all_views.append(summary_dict)

        # 3. Type filter (all/object/view) — case-insensitive
        if type:
            t = type.lower()
            if t == "object":
                all_views = []
            elif t == "view":
                all_objects = []

        # 4. Pagination
        total = len(all_objects) + len(all_views)
        offset = (page - 1) * page_size

        # objects-first ordering: slice objects, then views
        paged_objects = all_objects[offset : offset + page_size]
        remaining = page_size - len(paged_objects)
        paged_views: list[dict[str, Any]] = []
        if remaining > 0:
            view_start = max(0, offset - len(all_objects))
            paged_views = all_views[view_start : view_start + remaining]

        return {
            "data": {"objects": paged_objects, "views": paged_views},
            "totalCount": total,
            "page": page,
            "pageSize": page_size,
        }

    def get_base_details(
        self,
        loader: Any,
        base_id: str,
        *,
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get comprehensive base-level detail — all objects, views, relations, actions, dbsources.

        Similar to get_scene_details but scoped to the entire base, not a single scene.
        Supports optional view_code/object_code filtering.
        """
        # Collect all object codes from loader
        all_classes = getattr(loader, "_classes", {}) or {}
        all_object_codes = list(all_classes.keys())

        # Collect all view codes from loader
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        all_view_codes = list(raw_views.keys())

        # Filter by view_code / object_code
        if view_code and not object_code:
            target_views = [vc for vc in all_view_codes if vc in view_code]
            target_objects = all_object_codes
        elif object_code and not view_code:
            target_views = []
            target_objects = [oc for oc in all_object_codes if oc in object_code]
        elif view_code and object_code:
            target_views = [vc for vc in all_view_codes if vc in view_code]
            target_objects = list(set(object_code) | set(all_object_codes))
        else:
            target_views = list(all_view_codes)
            target_objects = list(all_object_codes)

        target_obj_set = set(target_objects)

        objects = self.extract_objects_detail(base_id, loader, sorted(target_obj_set))
        views = self.extract_views_detail(base_id, loader, target_views)
        relations = self.extract_relations(base_id, loader, target_obj_set)

        # Extract actions from all matching objects
        actions: list[dict[str, Any]] = []
        for code in sorted(target_obj_set):
            cls = all_classes.get(code)
            if cls is None:
                continue
            for a in getattr(cls, "actions", []):
                act = Action(
                    actionCode=a.action_code,
                    actionName=a.action_name,
                    actionType=a.action_type,
                    belongObjectCode=a.belong_class,
                    actionDesc=getattr(a, "description", None),
                    requestUrl=getattr(a, "request_url", None),
                    requestMethod=getattr(a, "request_method", None),
                    ownerType=getattr(a, "owner_type", "enterprise"),
                    userCode=getattr(a, "user_code", None),
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

        # Build dbsources
        used_db_ids: set[str] = set()
        for obj_dict in objects:
            for prop in obj_dict.get("properties", []):
                db_id = prop.get("dbId")
                if db_id:
                    used_db_ids.add(db_id)
        dbs: list[DbConnection] = []
        for db_id in sorted(used_db_ids):
            dbs.append(DbConnection(dbId=db_id, dbCode=db_id, dbType="", dbParams={}))

        # Collect all scenes under this base
        scenes_list = self.list_scenes(base_id)

        return {
            "base": {"baseId": base_id},
            "scenes": scenes_list,
            "views": views,
            "objects": objects,
            "actions": actions,
            "relations": relations,
            "dbsources": Datasource(db=dbs).model_dump(by_alias=True),
            "version": "v0.1.0",
        }

    def get_object_subtree(
        self,
        loader: Any,
        base_id: str,
        object_code: str,
    ) -> dict[str, Any]:
        """Get a single object's full subtree — detail + related views, relations, actions.

        Args:
            loader: An OntologyQueryable with _classes/_views/_relations populated.
            base_id: Base identifier.
            object_code: Target object code.

        Returns:
            Dict with object, views, relations, actions, dbsources.
        """
        all_classes = getattr(loader, "_classes", {}) or {}
        cls = all_classes.get(object_code)
        if cls is None:
            return {
                "object": None,
                "views": [],
                "relations": [],
                "actions": [],
                "dbsources": {"db": [], "doc": [], "api": []},
            }

        # Object detail
        objects = self.extract_objects_detail(base_id, loader, [object_code])

        # Views that reference this object
        raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
        related_views: list[str] = []
        for vc, vd in raw_views.items():
            objs = vd.get("objects", [])
            for obj_entry in objs:
                obj_code = (
                    obj_entry
                    if isinstance(obj_entry, str)
                    else obj_entry.get("object_code", "")
                )
                if obj_code == object_code:
                    related_views.append(vc)
                    break
        views = self.extract_views_detail(base_id, loader, related_views)

        # Relations involving this object (bidirectional)
        raw_relations: list[Any] = getattr(loader, "_relations", None) or []
        relations: list[dict[str, Any]] = []
        for r in raw_relations:
            if hasattr(r, "source_class"):
                src = r.source_class
                tgt = r.target_class
            elif isinstance(r, dict):
                src = r.get("source_class", "")
                tgt = r.get("target_class", "")
            else:
                continue
            if src != object_code and tgt != object_code:
                continue

            src_name = ""
            tgt_name = ""
            src_cls = all_classes.get(src)
            if src_cls is not None:
                src_name = src_cls.object_name
            tgt_cls = all_classes.get(tgt)
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
                    ownerType=getattr(r, "owner_type", "enterprise"),
                    userCode=getattr(r, "user_code", None),
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
                    ownerType=r.get("owner_type", r.get("ownerType", "enterprise")),
                    userCode=r.get("user_code") or r.get("userCode"),
                )
            else:
                continue
            relations.append(rel.model_dump(by_alias=True))

        # Actions on this object
        actions: list[dict[str, Any]] = []
        for a in getattr(cls, "actions", []):
            act = Action(
                actionCode=a.action_code,
                actionName=a.action_name,
                actionType=a.action_type,
                belongObjectCode=a.belong_class,
                actionDesc=getattr(a, "description", None),
                requestUrl=getattr(a, "request_url", None),
                requestMethod=getattr(a, "request_method", None),
                ownerType=getattr(a, "owner_type", "enterprise"),
                userCode=getattr(a, "user_code", None),
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

        # Dbsources from object properties
        used_db_ids: set[str] = set()
        for obj_dict in objects:
            for prop in obj_dict.get("properties", []):
                db_id = prop.get("dbId")
                if db_id:
                    used_db_ids.add(db_id)
        dbs: list[DbConnection] = []
        for db_id in sorted(used_db_ids):
            dbs.append(DbConnection(dbId=db_id, dbCode=db_id, dbType="", dbParams={}))

        return {
            "object": objects[0] if objects else None,
            "views": views,
            "relations": relations,
            "actions": actions,
            "dbsources": Datasource(db=dbs).model_dump(by_alias=True),
        }

    # ── Scene CRUD ────────────────────────────────────────────────────────

    def _generate_scene_id(self) -> str:
        """Generate a unique scene ID (snowflake)."""
        from datacloud_platform.base_entry import generate_snowflake

        return generate_snowflake()

    def create_scene(self, base_id: str, scene: Any) -> dict[str, Any]:
        """Create a scene (grouping container) with EntityStore persistence.

        Args:
            base_id: Base / project identifier.
            scene: Scene-like object or dict with scene_name, scene_code, scene_desc.
                   scene_id is always auto-generated; scene_code defaults to scene_name.
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

        scene_id = self._generate_scene_id()
        scene_code = scene_code or scene_name

        # 幂等：scene_code + base_id 已存在时返回已有场景（不重复创建）
        for _sid, _s in scenes.items():
            if _s.get("scene_code") == scene_code and _s.get("base_id") == base_id:
                logger.info(
                    "Scene with scene_code=%r already exists (scene_id=%s), skipping create",
                    scene_code,
                    _sid,
                )
                return _s

        if scene_id in scenes:
            raise ValueError(f"Scene already exists: {scene_id}")

        new_scene: dict[str, Any] = {
            "scene_id": scene_id,
            "scene_name": scene_name,
            "scene_code": scene_code,
            "scene_desc": scene_desc,
            "base_id": base_id,
            "member_object_codes": [],
            "member_view_codes": [],
        }
        scenes[scene_id] = new_scene
        self._save_scene(scene_id, new_scene)
        logger.info(
            "Created scene: base_id=%s scene_id=%s scene_code=%s",
            base_id,
            scene_id,
            scene_code,
        )
        self._invoke_sync_hook(
            "on_create",
            "SCENE",
            resource_code=scene_id,
            resource_name=scene_name,
            resource_desc=scene_desc or "",
            base_code=base_id,
        )
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
            if "scene_code" in updates or "sceneCode" in updates:
                scene["scene_code"] = updates.get(
                    "scene_code", updates.get("sceneCode")
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
        self._invoke_sync_hook(
            "on_update",
            "SCENE",
            resource_code=scene_id,
            resource_name=scene.get("scene_name", ""),
            resource_desc=scene.get("scene_desc", ""),
            base_code=base_id,
        )
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
        self._invoke_sync_hook(
            "on_delete",
            "SCENE",
            resource_code=scene_id,
            base_code=base_id,
        )

    # ── Scene reverse-lookup queries ────────────────────────────────────────

    def get_object_scene_count(self, base_id: str, object_code: str) -> int:
        """Return how many scenes this object belongs to."""
        self._ensure_scenes_loaded()
        self._ensure_reverse_index()
        return len(self._object_scene_map.get(object_code, set()))

    def get_view_scene_count(self, base_id: str, view_code: str) -> int:
        """Return how many scenes this view belongs to."""
        self._ensure_scenes_loaded()
        self._ensure_reverse_index()
        return len(self._view_scene_map.get(view_code, set()))

    def remove_object_from_all_scenes(self, base_id: str, object_code: str) -> int:
        """Remove object from all scenes. Returns count of scenes removed from."""
        self._ensure_scenes_loaded()
        count = 0
        for scene_id, scene in list((self._scenes or {}).items()):
            if scene.get("base_id") != base_id:
                continue
            obj_set: set[str] = set(scene.get("member_object_codes", []))
            if object_code in obj_set:
                obj_set.discard(object_code)
                scene["member_object_codes"] = list(obj_set)
                self._save_scene(scene_id, scene)
                count += 1
        if count > 0:
            self._reverse_index_built = False
        return count

    def remove_view_from_all_scenes(self, base_id: str, view_code: str) -> int:
        """Remove view from all scenes. Returns count of scenes removed from."""
        self._ensure_scenes_loaded()
        count = 0
        for scene_id, scene in list((self._scenes or {}).items()):
            if scene.get("base_id") != base_id:
                continue
            view_set: set[str] = set(scene.get("member_view_codes", []))
            if view_code in view_set:
                view_set.discard(view_code)
                scene["member_view_codes"] = list(view_set)
                self._save_scene(scene_id, scene)
                count += 1
        if count > 0:
            self._reverse_index_built = False
        return count

    def get_scenes_containing_object(self, base_id: str, object_code: str) -> list[str]:
        """Return scene_ids that contain this object."""
        self._ensure_scenes_loaded()
        self._ensure_reverse_index()
        return list(self._object_scene_map.get(object_code, set()))

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
        self._reverse_index_built = False
        # B-domain: fill term domain_codes after scene association (deferred sync)
        if hasattr(self, "_sync_entity_domains"):
            self._sync_entity_domains(base_id, scene_id, "object", added_objs)
            self._sync_entity_domains(base_id, scene_id, "view", added_views)
        logger.info(
            "Added scene members: scene_id=%s objects=%d views=%d (synced=%d+%d)",
            scene_id,
            len(added_objs),
            len(added_views),
            len(added_objs),
            len(added_views),
        )
        self._invoke_sync_hook(
            "on_update",
            "SCENE",
            resource_code=scene_id,
            resource_name=scene.get("scene_name", ""),
            resource_desc=scene.get("scene_desc", ""),
            base_code=base_id,
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
        self._reverse_index_built = False
        # B-domain: remove scene_id from term.domain_ids after scene disassociation
        if hasattr(self, "_remove_entity_domains"):
            self._remove_entity_domains(base_id, scene_id, "object", object_codes)
            self._remove_entity_domains(base_id, scene_id, "view", view_codes)
        logger.info(
            "Removed scene members: scene_id=%s objects=%d views=%d",
            scene_id,
            len(object_codes),
            len(view_codes),
        )
        self._invoke_sync_hook(
            "on_update",
            "SCENE",
            resource_code=scene_id,
            resource_name=scene.get("scene_name", ""),
            resource_desc=scene.get("scene_desc", ""),
            base_code=base_id,
        )
        return scene
