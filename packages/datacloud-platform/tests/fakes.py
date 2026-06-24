"""Fake Backend implementations for testing — in-memory, no external dependencies.

Usage::

    from fakes import (
        FakeOntologyBackend,
        FakeKnowledgeBackend,
        FakeExecutionBackend,
        FakeStorageBackend,
    )

    onto = FakeOntologyBackend()
    onto._objects["obj1"] = ObjectSummary(object_code="obj1", object_name="Object 1")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from datacloud_platform.models.shared import (
    DimensionProperty,
    EmbeddingHit,
    MatchCandidate,
    MatchResult,
    ObjectSummary,
    ParsedOwlContent,
    ReferenceProperty,
    ScoreUpdateRecord,
    StoredFile,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datacloud_platform.backends.ontology import OntologyQueryable


class _FakeOntologyQueryable:
    """Fake OntologyQueryable for testing — holds objects dict as _classes."""

    _classes: dict[str, Any]
    _relations: list[Any]
    _views: dict[str, Any] | None

    def __init__(self, objects: dict[str, ObjectSummary] | None = None) -> None:
        self._classes = objects or {}
        self._relations = []
        self._views = None


class FakeOntologyBackend:
    """In-memory ontology backend — no datacloud-data SDK dependency.

    Test code can preset ``_objects`` and ``_parsed`` to control behaviour.
    """

    def __init__(self) -> None:
        self._objects: dict[str, ObjectSummary] = {}
        self._parsed: ParsedOwlContent | None = None
        self._tables_created: list[str] = []
        self._tables_dropped: list[str] = []
        self._created_objects: list[tuple[Any, Any, Any]] = []
        self._updated_objects: list[tuple[Any, Any, Any, Any]] = []
        self._deleted_objects: list[tuple[Any, Any, str]] = []
        self._readonly: bool = False
        """When True, write operations raise PermissionError."""

        # View tracking
        self._views: dict[str, list[dict[str, Any]]] = {}
        self._created_views: list[tuple[Any, Any, Any]] = []
        self._updated_views: list[tuple[Any, Any, Any, Any]] = []
        self._deleted_views: list[tuple[Any, Any, str]] = []

        # Relation tracking
        self._relations: dict[str, list[dict[str, Any]]] = {}
        self._created_relations: list[tuple[Any, Any, Any]] = []
        self._updated_relations: list[tuple[Any, Any, Any, Any]] = []
        self._deleted_relations: list[tuple[Any, Any, str]] = []

        # Action tracking
        self._actions: dict[str, list[dict[str, Any]]] = {}
        self._created_actions: list[tuple[Any, Any, Any, Any]] = []
        self._updated_actions: list[tuple[Any, Any, Any, Any, Any]] = []
        self._deleted_actions: list[tuple[Any, Any, Any, str]] = []

        # Datasource tracking
        self._datasources: dict[str, list[dict[str, Any]]] = {}
        self._created_datasources: list[tuple[Any, Any, Any]] = []
        self._deleted_datasources: list[tuple[Any, Any, str]] = []

        # Scene tracking
        self._scenes: list[dict[str, Any]] = []
        self._scenes_dict: dict[str, dict[str, Any]] = {}
        self._scene_details: dict[str, dict[str, Any]] = {}
        self._ontologies_by_scene: dict[str, dict[str, Any]] = {}
        self._created_scenes: list[tuple[Any, Any]] = []
        self._updated_scenes: list[tuple[Any, Any, Any]] = []
        self._deleted_scenes: list[tuple[Any, str]] = []
        self._scene_members_added: list[tuple[Any, str, list[str], list[str]]] = []
        self._scene_members_removed: list[tuple[Any, str, list[str], list[str]]] = []

        # Full object storage (with properties/actions) for get_scene_details filtering
        self._full_objects: dict[str, dict[str, Any]] = {}
        self._all_relations_flat: list[dict[str, Any]] = []
        self._all_dbsources_flat: list[dict[str, Any]] = []

    @staticmethod
    def _empty_scene_details() -> dict[str, Any]:
        """Return empty scene details dict."""
        return {
            "scene": None,
            "views": [],
            "objects": [],
            "actions": [],
            "relations": [],
            "dbsources": {"db": [], "doc": [], "api": []},
            "version": "v0.1.0",
        }

    def parse_owl(self, directory: Path) -> ParsedOwlContent:  # noqa: ARG002
        """Return preset _parsed or empty ParsedOwlContent."""
        return self._parsed or ParsedOwlContent(objects=[], views=[], relations=[])

    def load_ontology(self, base_path: Path) -> OntologyQueryable:
        """Return a FakeOntologyQueryable wrapping _objects."""
        return _FakeOntologyQueryable(self._objects)

    def load_terms(
        self,
        loader: OntologyQueryable,
        *,
        library_id: str = "PERSONAL_LIB",  # noqa: ARG002
    ) -> Any:
        """No-op in fake."""
        return None

    def create_table(self, object_code: str, fields: list[dict[str, Any]]) -> None:
        """Record table creation."""
        self._tables_created.append(object_code)

    def drop_table(self, object_code: str) -> None:
        """Record table drop."""
        self._tables_dropped.append(object_code)

    def get_objects(
        self,
        loader: OntologyQueryable,
        _base_id: str,
    ) -> list[ObjectSummary]:
        """Return all objects from _objects."""
        return list(self._objects.values())

    def get_object_detail(
        self,
        loader: OntologyQueryable,
        object_code: str,
    ) -> ObjectSummary | None:
        """Look up object by code in _objects."""
        return self._objects.get(object_code)

    # -- Object CRUD --

    def create_object(self, base_id: str, obj: Any) -> Any:  # noqa: ARG002
        """Record created object and return it."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._created_objects.append((base_id, obj))
        return obj

    def update_object(  # noqa: ARG002
        self, base_id: str, object_code: str, obj: Any
    ) -> Any:
        """Record updated object and return it."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._updated_objects.append((base_id, object_code, obj))
        return obj

    def delete_object(self, base_id: str, object_code: str) -> None:
        """Record deleted object."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._deleted_objects.append((base_id, object_code))

    # -- View CRUD (fake) --

    def get_views(self, loader: Any, base_id: str) -> list[dict[str, Any]]:  # noqa: ARG002
        """Return preset _views for the scene."""
        _ = loader
        result = []
        for vlist in self._views.values():
            result.extend(vlist)
        return result

    def get_view_detail(
        self,
        loader: Any,
        base_id: str,
        view_code: str,  # noqa: ARG002
    ) -> dict[str, Any] | None:
        """Look up view by code."""
        _ = loader
        for vlist in self._views.values():
            for v in vlist:
                if v.get("viewCode") == view_code:
                    return v
        return None

    def create_view(self, base_id: str, view: Any) -> Any:  # noqa: ARG002
        """Record created view."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._created_views.append((base_id, view))
        self._views.setdefault("__all__", []).append(view)
        return view

    def update_view(  # noqa: ARG002
        self, base_id: str, view_code: str, view: Any
    ) -> Any:
        """Record updated view."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._updated_views.append((base_id, view_code, view))
        return view

    def delete_view(self, base_id: str, view_code: str) -> None:
        """Record deleted view."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._deleted_views.append((base_id, view_code))

    # -- Relation CRUD (fake) --

    def get_relations(self, loader: Any, base_id: str) -> list[dict[str, Any]]:  # noqa: ARG002
        """Return preset _relations for the scene."""
        _ = loader
        result = []
        for rlist in self._relations.values():
            result.extend(rlist)
        return result

    def get_relation_detail(  # noqa: ARG002
        self, loader: Any, base_id: str, rel_code: str
    ) -> dict[str, Any] | None:
        """Look up relation by code."""
        _ = loader
        for rlist in self._relations.values():
            for r in rlist:
                if r.get("relationCode") == rel_code:
                    return r
        return None

    def create_relation(self, base_id: str, rel: Any) -> Any:  # noqa: ARG002
        """Record created relation."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._created_relations.append((base_id, rel))
        self._relations.setdefault("__all__", []).append(rel)
        return rel

    def update_relation(  # noqa: ARG002
        self, base_id: str, rel_code: str, rel: Any
    ) -> Any:
        """Record updated relation."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._updated_relations.append((base_id, rel_code, rel))
        return rel

    def delete_relation(self, base_id: str, rel_code: str) -> None:
        """Record deleted relation."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._deleted_relations.append((base_id, rel_code))

    # -- Action CRUD (fake) --

    def get_actions(  # noqa: ARG002
        self, loader: Any, base_id: str, object_code: str
    ) -> list[dict[str, Any]]:
        """Return preset _actions for the object."""
        _ = loader
        return list(self._actions.get(object_code, []))

    def get_action_detail(  # noqa: ARG002
        self, loader: Any, base_id: str, object_code: str, action_code: str
    ) -> dict[str, Any] | None:
        """Look up action by code."""
        _ = loader
        for a in self._actions.get(object_code, []):
            if a.get("actionCode") == action_code:
                return a
        return None

    def create_action(  # noqa: ARG002
        self, base_id: str, object_code: str, action: Any
    ) -> Any:
        """Record created action."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._created_actions.append((base_id, object_code, action))
        self._actions.setdefault(object_code, []).append(action)
        return action

    def update_action(
        self, base_id: str, object_code: str, action_code: str, action: Any
    ) -> Any:
        """Record updated action."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._updated_actions.append((base_id, object_code, action_code, action))
        return action

    def delete_action(  # noqa: ARG002
        self, base_id: str, object_code: str, action_code: str
    ) -> None:
        """Record deleted action."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._deleted_actions.append((base_id, object_code, action_code))

    # -- Datasource CRUD (fake) --

    def get_datasources(self, loader: Any, base_id: str) -> list[dict[str, Any]]:  # noqa: ARG002
        """Return preset _datasources for the scene."""
        _ = loader
        result = []
        for dslist in self._datasources.values():
            result.extend(dslist)
        return result

    def get_datasource_detail(  # noqa: ARG002
        self,
        loader: Any,
        base_id: str,
        db_id: str,
    ) -> dict[str, Any] | None:
        """Look up datasource by db_id."""
        _ = loader
        for dslist in self._datasources.values():
            for ds in dslist:
                db_list = ds.get("db", [])
                if db_list and isinstance(db_list, list) and db_list:
                    if str(db_list[0].get("dbId", "")) == db_id:
                        return ds
                elif str(ds.get("dbId", ds.get("db_id", ""))) == db_id:
                    return ds
        return None

    def create_datasource(self, base_id: str, ds: Any) -> Any:  # noqa: ARG002
        """Record created datasource."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._created_datasources.append((base_id, ds))
        self._datasources.setdefault("__all__", []).append(ds)
        return ds

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Record deleted datasource."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        self._deleted_datasources.append((base_id, db_id))

    # -- Scene management (fake) --

    def list_scenes(self, base_id: str) -> list[dict[str, Any]]:  # noqa: ARG002
        """Return preset _scenes list."""
        return list(self._scenes)

    def query_scenes(  # noqa: ARG002
        self, base_id: str, keyword: str | None
    ) -> list[dict[str, Any]]:
        """Return preset _scenes list filtered by keyword."""
        if not keyword:
            return list(self._scenes)
        kw = keyword.strip().lower()
        return [
            s
            for s in self._scenes
            if kw in s.get("sceneName", "").lower()
            or kw in s.get("sceneCode", "").lower()
        ]

    def count_scenes(self, base_id: str, keyword: str | None) -> int:  # noqa: ARG002
        """Return count of matching scenes."""
        return len(self.query_scenes(base_id, keyword))

    def get_scene_details(  # noqa: ARG002
        self,
        loader: object,
        base_id: str,
        scene_id: str,
        *,
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return scene details with optional filtering.

        When _full_objects is populated, applies full filtering logic:
        - No params: all member objects + views.
        - view_code only: matching views + objects referenced by those views.
        - object_code only: matching objects, views = [].
        - Both: union of the two sets.

        Falls back to preset _scene_details for backward compatibility.
        """
        _ = loader
        # Try full filtering path first
        scene = self._scenes_dict.get(scene_id)
        if scene is not None:
            return self._compute_scene_details(
                scene, view_code=view_code, object_code=object_code
            )
        # Fallback to preset
        return dict(self._scene_details.get(scene_id, self._empty_scene_details()))

    def _compute_scene_details(
        self,
        scene: dict[str, Any],
        *,
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compute scene details with filtering from internal storage."""
        member_obj_codes: list[str] = scene.get("member_object_codes", [])
        member_view_codes: list[str] = scene.get("member_view_codes", [])

        # Collect all views in this base (from _views dict)
        all_views: list[dict[str, Any]] = []
        for vlist in self._views.values():
            all_views.extend(vlist)

        # Determine target views and objects
        if view_code and not object_code:
            # Only view_code: matching views + objects referenced by those views
            target_views = [v for v in all_views if v.get("viewCode") in view_code]
            target_obj_set: set[str] = set()
            for v in target_views:
                target_obj_set.update(v.get("objectCodes", []))
        elif object_code and not view_code:
            # Only object_code: views = []
            target_views = []
            target_obj_set = set(object_code)
        elif view_code and object_code:
            # Both: union
            target_views = [v for v in all_views if v.get("viewCode") in view_code]
            target_obj_set = set(object_code)
            for v in target_views:
                target_obj_set.update(v.get("objectCodes", []))
        else:
            # No filter: all member views + all member objects
            target_views = [
                v for v in all_views if v.get("viewCode") in member_view_codes
            ]
            target_obj_set = set(member_obj_codes)

        # Resolve full objects
        objects = [
            self._full_objects[code]
            for code in target_obj_set
            if code in self._full_objects
        ]

        # Collect actions from filtered objects
        actions: list[dict[str, Any]] = []
        for obj in objects:
            actions.extend(obj.get("actions", []))

        # Filter relations: both ends in target_obj_set
        relations = [
            r
            for r in self._all_relations_flat
            if r.get("sourceObjectCode") in target_obj_set
            and r.get("targetObjectCode") in target_obj_set
        ]

        # Filter dbsources: referenced by filtered objects' properties
        used_db_ids: set[str] = set()
        for obj in objects:
            for prop in obj.get("properties", []):
                db_id = prop.get("dbId")
                if db_id:
                    used_db_ids.add(db_id)

        dbs = [ds for ds in self._all_dbsources_flat if ds.get("dbId") in used_db_ids]

        return {
            "scene": scene,
            "views": target_views,
            "objects": objects,
            "actions": actions,
            "relations": relations,
            "dbsources": {"db": dbs, "doc": [], "api": []},
            "version": "v0.1.0",
        }

    def query_ontologies_by_scene(  # noqa: ARG002
        self,
        loader: object,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """Return preset _ontologies_by_scene or empty result."""
        _ = loader
        result = self._ontologies_by_scene.get(scene_id, {"data": [], "totalCount": 0})
        if keyword:
            kw = keyword.strip().lower()
            data = [
                o
                for o in result.get("data", [])
                if kw in o.get("ontologyName", "").lower()
                or kw in o.get("ontologyCode", "").lower()
                or kw in o.get("ontologyDesc", "").lower()
            ]
            total = len(data)
            start = (page - 1) * page_size
            return {"data": data[start : start + page_size], "totalCount": total}
        return result

    # -- Scene CRUD (fake) --

    def create_scene(self, base_id: str, scene: Any) -> Any:  # noqa: ARG002
        """Create a scene (grouping container)."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        if isinstance(scene, dict):
            scene_name = scene.get("scene_name", scene.get("sceneName", ""))
            scene_code = scene.get("scene_code", scene.get("sceneCode"))
            scene_desc = scene.get("scene_desc", scene.get("sceneDesc"))
        else:
            scene_name = getattr(scene, "scene_name", "")
            scene_code = getattr(scene, "scene_code", None)
            scene_desc = getattr(scene, "scene_desc", None)
        scene_id = scene_code or f"scene_{uuid4().hex[:12]}"
        if scene_id in self._scenes_dict:
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
        self._scenes_dict[scene_id] = new_scene
        self._scenes.append(new_scene)
        self._created_scenes.append((base_id, scene))
        return new_scene

    def update_scene(  # noqa: ARG002
        self, base_id: str, scene_id: str, updates: Any
    ) -> Any:
        """Update scene metadata."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        scene = self._scenes_dict.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
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
        self._updated_scenes.append((base_id, scene_id, updates))
        return scene

    def delete_scene(self, base_id: str, scene_id: str) -> None:
        """Delete a scene — does NOT delete member resources."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        scene = self._scenes_dict.pop(scene_id, None)
        if scene is not None:
            self._scenes = [s for s in self._scenes if s.get("scene_id") != scene_id]
            self._deleted_scenes.append((base_id, scene_id))

    # -- Scene member management (fake) --

    def add_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Add objects/views to a scene (idempotent — duplicates are ignored)."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        scene = self._scenes_dict.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        existing_objs: set[str] = set(scene.get("member_object_codes", []))
        existing_views: set[str] = set(scene.get("member_view_codes", []))
        scene["member_object_codes"] = list(existing_objs | set(object_codes))
        scene["member_view_codes"] = list(existing_views | set(view_codes))
        self._scene_members_added.append((base_id, scene_id, object_codes, view_codes))
        return scene

    def remove_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Remove objects/views from a scene — does NOT delete resources."""
        if self._readonly:
            raise PermissionError("REMOTE backend is read-only")
        scene = self._scenes_dict.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        obj_set: set[str] = set(scene.get("member_object_codes", []))
        view_set: set[str] = set(scene.get("member_view_codes", []))
        obj_set.difference_update(object_codes)
        view_set.difference_update(view_codes)
        scene["member_object_codes"] = list(obj_set)
        scene["member_view_codes"] = list(view_set)
        self._scene_members_removed.append(
            (base_id, scene_id, object_codes, view_codes)
        )
        return scene


# ── Scene grouping test helpers ───────────────────────────────────────────


def make_object(
    object_code: str,
    *,
    object_name: str = "",
    db_id: str | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a minimal full object dict for scene grouping tests."""
    name = object_name or object_code
    properties: list[dict[str, Any]] = []
    if db_id:
        properties.append({"dbId": db_id})
    return {
        "objectCode": object_code,
        "objectName": name,
        "objectDesc": "",
        "properties": properties,
        "actions": actions or [],
    }


def make_action(action_code: str, *, action_name: str = "") -> dict[str, Any]:
    """Create a minimal action dict."""
    return {
        "actionCode": action_code,
        "actionName": action_name or action_code,
    }


def make_scene(
    scene_name: str, *, scene_code: str | None = None, scene_desc: str | None = None
) -> dict[str, Any]:
    """Create a minimal scene dict."""
    code = scene_code or scene_name
    return {
        "sceneName": scene_name,
        "sceneCode": code,
        "sceneDesc": scene_desc,
    }


def make_view(
    view_code: str,
    *,
    view_name: str = "",
    object_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Create a minimal view dict."""
    return {
        "viewCode": view_code,
        "viewName": view_name or view_code,
        "objectCodes": object_codes or [],
    }


def make_relation(
    rel_code: str,
    *,
    source: str = "",
    target: str = "",
) -> dict[str, Any]:
    """Create a minimal relation dict."""
    return {
        "relationCode": rel_code,
        "sourceObjectCode": source,
        "targetObjectCode": target,
    }


def make_ds(db_id: str, *, ds_name: str = "") -> dict[str, Any]:
    """Create a minimal datasource dict."""
    return {"dbId": db_id, "dbName": ds_name or db_id}


class FakeSceneBackend:
    """In-memory backend for pure scene-grouping business-logic tests.

    Independent of the full OntologyBackend protocol — stores objects, views,
    relations, datasources, and scenes entirely in dicts. Implements the full
    getSceneDetails filtering logic for deterministic testing.
    """

    def __init__(self) -> None:
        self._scenes: dict[str, dict[str, Any]] = {}
        self._objects: dict[str, dict[str, Any]] = {}
        self._views: dict[str, dict[str, Any]] = {}
        self._relations: list[dict[str, Any]] = []
        self._dbsources: dict[str, dict[str, Any]] = {}

    # -- Object helpers --

    def create_object(self, base_id: str, obj: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        """Store a full object dict keyed by objectCode."""
        code = obj["objectCode"]
        self._objects[code] = dict(obj)
        return self._objects[code]

    def get_object_detail(
        self, base_id: str, object_code: str
    ) -> dict[str, Any] | None:  # noqa: ARG002
        """Look up a full object by code."""
        return self._objects.get(object_code)

    # -- View helpers --

    def create_view(self, base_id: str, view: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        """Store a view dict keyed by viewCode."""
        code = view["viewCode"]
        self._views[code] = dict(view)
        return self._views[code]

    # -- Relation helpers --

    def create_relation(self, base_id: str, rel: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        """Append a relation dict."""
        self._relations.append(dict(rel))
        return rel

    # -- Datasource helpers --

    def create_datasource(self, base_id: str, ds: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        """Store a datasource dict keyed by dbId."""
        db_id = ds["dbId"]
        self._dbsources[db_id] = dict(ds)
        return self._dbsources[db_id]

    # -- Scene CRUD --

    def create_scene(self, base_id: str, scene: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        """Create a scene (grouping container)."""
        scene_name = scene.get("sceneName", scene.get("scene_name", ""))
        scene_code = scene.get("sceneCode", scene.get("scene_code"))
        scene_desc = scene.get("sceneDesc", scene.get("scene_desc"))
        scene_id = scene_code or f"scene_{uuid4().hex[:12]}"
        if scene_id in self._scenes:
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
        self._scenes[scene_id] = new_scene
        return new_scene

    def update_scene(
        self, base_id: str, scene_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:  # noqa: ARG002
        """Update scene metadata."""
        scene = self._scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        if "sceneName" in updates or "scene_name" in updates:
            scene["scene_name"] = updates.get("sceneName", updates.get("scene_name"))
        if "sceneDesc" in updates or "scene_desc" in updates:
            scene["scene_desc"] = updates.get("sceneDesc", updates.get("scene_desc"))
        return scene

    def delete_scene(self, base_id: str, scene_id: str) -> None:  # noqa: ARG002
        """Delete a scene — does NOT delete member resources."""
        self._scenes.pop(scene_id, None)

    # -- Scene member management --

    def add_scene_members(
        self,
        base_id: str,  # noqa: ARG002
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> dict[str, Any]:
        """Add objects/views to a scene (idempotent — duplicates are ignored)."""
        scene = self._scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        existing_objs: set[str] = set(scene.get("member_object_codes", []))
        existing_views: set[str] = set(scene.get("member_view_codes", []))
        scene["member_object_codes"] = sorted(existing_objs | set(object_codes))
        scene["member_view_codes"] = sorted(existing_views | set(view_codes))
        return scene

    def remove_scene_members(
        self,
        base_id: str,  # noqa: ARG002
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> dict[str, Any]:
        """Remove objects/views from a scene — does NOT delete resources."""
        scene = self._scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        obj_set: set[str] = set(scene.get("member_object_codes", []))
        view_set: set[str] = set(scene.get("member_view_codes", []))
        obj_set.difference_update(object_codes)
        view_set.difference_update(view_codes)
        scene["member_object_codes"] = sorted(obj_set)
        scene["member_view_codes"] = sorted(view_set)
        return scene

    # -- getSceneDetails (full filtering logic) --

    def get_scene_details(
        self,
        base_id: str,  # noqa: ARG002
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
        scene = self._scenes.get(scene_id)
        if scene is None:
            return {
                "scene": None,
                "views": [],
                "objects": [],
                "actions": [],
                "relations": [],
                "dbsources": {"db": [], "doc": [], "api": []},
                "version": "v0.1.0",
            }

        member_obj_codes: list[str] = scene.get("member_object_codes", [])
        member_view_codes: list[str] = scene.get("member_view_codes", [])

        all_views = list(self._views.values())

        # Determine target views and objects
        if view_code and not object_code:
            target_views = [v for v in all_views if v.get("viewCode") in view_code]
            target_obj_set: set[str] = set()
            for v in target_views:
                target_obj_set.update(v.get("objectCodes", []))
        elif object_code and not view_code:
            target_views = []
            target_obj_set = set(object_code)
        elif view_code and object_code:
            target_views = [v for v in all_views if v.get("viewCode") in view_code]
            target_obj_set = set(object_code)
            for v in target_views:
                target_obj_set.update(v.get("objectCodes", []))
        else:
            target_views = [
                v for v in all_views if v.get("viewCode") in member_view_codes
            ]
            target_obj_set = set(member_obj_codes)

        # Resolve full objects
        objects = [
            self._objects[code]
            for code in sorted(target_obj_set)
            if code in self._objects
        ]

        # Collect actions from filtered objects
        actions: list[dict[str, Any]] = []
        for obj in objects:
            actions.extend(obj.get("actions", []))

        # Filter relations: both ends in target_obj_set
        relations = [
            r
            for r in self._relations
            if r.get("sourceObjectCode") in target_obj_set
            and r.get("targetObjectCode") in target_obj_set
        ]

        # Filter dbsources: referenced by filtered objects' properties
        used_db_ids: set[str] = set()
        for obj in objects:
            for prop in obj.get("properties", []):
                db_id = prop.get("dbId")
                if db_id:
                    used_db_ids.add(db_id)

        dbs = [
            self._dbsources[db_id]
            for db_id in sorted(used_db_ids)
            if db_id in self._dbsources
        ]

        return {
            "scene": scene,
            "views": target_views,
            "objects": objects,
            "actions": actions,
            "relations": relations,
            "dbsources": {"db": dbs, "doc": [], "api": []},
            "version": "v0.1.0",
        }

    # -- Persistence helpers --

    def persist_scenes(self, directory: Path) -> None:
        """Write scenes to directory as JSON (for roundtrip tests)."""
        import json

        directory.mkdir(parents=True, exist_ok=True)
        scenes_file = directory / "scenes.json"
        scenes_file.write_text(
            json.dumps(list(self._scenes.values()), ensure_ascii=False, indent=2)
        )

    def restore_scenes(self, directory: Path) -> None:
        """Read scenes from directory JSON (for roundtrip tests)."""
        import json

        scenes_file = directory / "scenes.json"
        if scenes_file.exists():
            data = json.loads(scenes_file.read_text())
            for s in data:
                self._scenes[s["scene_id"]] = s


class FakeKnowledgeBackend:
    """In-memory knowledge backend — no datacloud-knowledge SDK dependency.

    Test code can preset ``candidates``, ``_disambiguated``, ``_terms``
    and other internal dicts/lists to control behaviour.
    """

    def __init__(self) -> None:
        self._terms: dict[tuple[str, str], str] = {}
        self._terms_by_ids: dict[tuple[str, str, str], str] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._search_results: list[EmbeddingHit] = []
        self.candidates: list[MatchCandidate] = []
        self._disambiguated: list[MatchResult] = []
        self._synced: list[str] = []
        self._removed: list[str] = []
        self._scorerecords: list[ScoreUpdateRecord] = []
        self._type_codes: list[str] = []
        self._ontology_search_results: dict[str, Any] = {}
        self._graph_results: dict[str, Any] = {"nodes": [], "edges": []}
        self._batch_searches: list[dict[str, Any]] = []
        self._search_instances_result: dict[str, Any] = {"data": [], "totalCount": 0}
        self._graph_path_result: dict[str, Any] = {"path": [], "edges": [], "hops": -1}

    # -- Search --

    def search_candidates(
        self,
        query: str,  # noqa: ARG002
        *,
        scope: str = "all",  # noqa: ARG002
        limit: int = 20,  # noqa: ARG002
    ) -> list[MatchCandidate]:
        """Return preset candidates."""
        return list(self.candidates)

    def disambiguate(
        self,
        candidates: list[MatchCandidate],
        query: str,  # noqa: ARG002
    ) -> list[MatchResult]:
        """Return preset _disambiguated."""
        return list(self._disambiguated)

    # -- Clarification --

    def prepare_clarification(
        self,
        query: str,  # noqa: ARG002
        slots: list[dict[str, Any]],  # noqa: ARG002
    ) -> dict[str, Any]:
        """Return empty dict."""
        return {}

    def finalize_clarification(self, clarification_id: str) -> dict[str, Any]:  # noqa: ARG002
        """Return empty dict."""
        return {}

    # -- Term CRUD --

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        _entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,  # noqa: ARG002
    ) -> None:
        """Record sync call."""
        self._synced.append(entity_code)

    def remove_terms(self, entity_code: str) -> None:
        """Record remove call."""
        self._removed.append(entity_code)

    def get_term(self, term_code: str, term_type_code: str) -> str | None:
        """Look up term name by (code, type_code)."""
        return self._terms.get((term_code, term_type_code))

    def term_exists(self, term_code: str, term_type_code: str) -> bool:
        """Check if term is in _terms."""
        return (term_code, term_type_code) in self._terms

    def get_term_by_ids(
        self, keys: list[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """Batch lookup by (library_id, type_code, term_code) -> term_id."""
        return {k: v for k, v in self._terms_by_ids.items() if k in keys}

    def get_type_codes_by_category(
        self,
        categories: list[int],  # noqa: ARG002
    ) -> list[str]:
        """Return preset _type_codes."""
        return list(self._type_codes)

    # -- Vector --

    def embed(self, text: str) -> list[float]:
        """Return preset embedding or a zero-vector."""
        return self._embeddings.get(text, [0.0] * 768)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return preset embeddings or zero-vectors."""
        return [self.embed(t) for t in texts]

    def search_by_embedding(
        self,
        vector: list[float],  # noqa: ARG002
        term_types: list[str],  # noqa: ARG002
        limit: int = 20,  # noqa: ARG002
    ) -> list[EmbeddingHit]:
        """Return preset _search_results, capped at limit."""
        return self._search_results[:limit]

    # -- Dimension resolution --

    def resolve_dimension_value(
        self,
        value_term_id: str,  # noqa: ARG002
    ) -> DimensionProperty:
        """Return empty DimensionProperty."""
        return DimensionProperty(property_code="", object_code="")

    def get_referenced_by(
        self,
        value_term_id: str,  # noqa: ARG002
    ) -> list[ReferenceProperty]:
        """Return empty list."""
        return []

    def resolve_object_for_property(
        self,
        property_code: str,  # noqa: ARG002
    ) -> str | None:
        """Return None (not resolved)."""
        return None

    # -- Ontology search & graph --

    def search_ontology(
        self,
        base_id: str,
        scene_id: str,
        *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return preset _ontology_search_results or empty dict."""
        return dict(self._ontology_search_results)

    def search_ontology_batch(
        self,
        base_id: str,
        keyword: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return preset _ontology_search_results or empty dict.

        Records the call for test inspection via ``_batch_searches``.
        """
        self._batch_searches.append(
            {
                "base_id": base_id,
                "keyword": keyword,
                "limit": limit,
                "result": dict(self._ontology_search_results),
            }
        )
        return dict(self._ontology_search_results)

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
        """Return preset _graph_results."""
        return dict(self._graph_results)

    # -- Scoring --

    def update_scores(self, records: list[ScoreUpdateRecord]) -> None:
        """Record score updates."""
        self._scorerecords.extend(records)

    # -- Instance search & graph path (fake) --

    def search_instances(
        self,
        base_id: str,  # noqa: ARG002
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return preset _search_instances_result or empty."""
        return dict(self._search_instances_result)

    def graph_path(
        self,
        base_id: str,  # noqa: ARG002
        scene_id: str,  # noqa: ARG002
        *,
        match_by: str = "name",
        start_node: str,
        end_node: str = "",
        direction: str = "forward",
    ) -> dict[str, Any]:
        """Return preset _graph_path_result or empty path."""
        return dict(self._graph_path_result)

    # -- Field aliases & clarification results (fake) --

    def resolve_field_aliases(
        self,
        field_aliases: dict[str, list[str]],  # noqa: ARG002
    ) -> dict[str, list[tuple[str, str]]]:
        """Return empty dict."""
        return {}

    def store_clarification_results(
        self,
        results: dict[str, Any],
        user_id: str,  # noqa: ARG002
    ) -> list[str]:
        """Return empty list."""
        return []


class FakeExecutionBackend:
    """In-memory execution backend — captures executed actions and tool definitions."""

    def __init__(self) -> None:
        self._executed: list[dict[str, Any]] = []
        self._tools: list[dict[str, Any]] = []

    async def execute_action(  # type: ignore[override]
        self,
        loader: Any,
        object_code: str,
        action_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Record execution and return ok status."""
        self._executed.append(
            {
                "object_code": object_code,
                "action_code": action_code,
                "arguments": arguments,
            }
        )
        return {"status": "ok"}

    def generate_action_tools(
        self,
        loader: Any,
        object_code: str,
    ) -> list[dict[str, Any]]:
        """Return preset _tools."""
        return list(self._tools)

    def generate_dynamic_query_tools(
        self,
        loader: Any,
        object_code: str,
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def generate_virtual_actions(
        self,
        loader: OntologyQueryable,
        mounted_objects: list[str],
    ) -> list[dict[str, Any]]:
        """Return empty list."""
        return []

    def generate_plan(
        self,
        query: str,
        loader: OntologyQueryable,
        context: Any,
    ) -> Any:
        """Return empty steps plan."""
        return {"steps": []}


class FakeStorageBackend:
    """In-memory file storage backend."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._meta: dict[str, dict[str, Any]] = {}

    def store_result(
        self,
        key: str,
        data: bytes,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store data and return auto-generated file_id."""
        file_id = str(uuid4())
        self._files[file_id] = data
        if metadata is not None:
            self._meta[file_id] = metadata
        return file_id

    def get_result(self, file_id: str) -> bytes:
        """Return file content by id."""
        return self._files[file_id]

    def delete_result(self, file_id: str) -> None:
        """Remove file by id (no-op if missing)."""
        self._files.pop(file_id, None)
        self._meta.pop(file_id, None)

    def list_results(self, prefix: str = "") -> list[StoredFile]:
        """List all files, optionally filtered by prefix."""
        return [
            StoredFile(file_id=k, key=k, size_bytes=len(v), created_at="")
            for k, v in self._files.items()
            if k.startswith(prefix)
        ]
