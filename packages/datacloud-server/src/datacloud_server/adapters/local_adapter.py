"""Local ontology adapter - reads OWL/JSON via datacloud-data SDK, writes via JSONWriter.

Uses datacloud-data SDK for OWL parsing and OpenGauss (via sqlalchemy) for vector search.
"""

from __future__ import annotations

import io
import json as _json
import logging
import os
import shutil
import tempfile
import zipfile
from collections import deque
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

import requests
from sqlalchemy import create_engine, text

if TYPE_CHECKING:
    from datacloud_server.models.action import Action
    from datacloud_server.models.datasource import Datasource
    from datacloud_server.models.object_type import ObjectType
    from datacloud_server.models.relation import Relation
    from datacloud_server.models.view import View
    from datacloud_server.storage.json_writer import JSONWriter

from datacloud_data_sdk.ontology.loader import OntologyLoader
from datacloud_data_sdk.ontology.owl_parser import OwlParser

logger = logging.getLogger(__name__)


def _add_nodes_and_edges(  # noqa: PLR0912
    loader: OntologyLoader,
    object_codes: list[str] | None,
    depth: int | None,
    nodes: dict[str, dict],
    edges: list[dict],
) -> None:
    """Build nodes and edges from loader relations, populating nodes/edges in-place.

    If object_codes is provided, filter to those objects.  If depth is provided,
    BFS-expand from the seed objects up to depth hops to include connected objects.
    """
    # Build adjacency from relations
    adj: dict[str, list[dict]] = {}
    for rel in loader._relations:
        s, t = rel.source_class, rel.target_class
        edge_data = {
            "source": s,
            "target": t,
            "relationCode": rel.relation_code,
            "relationCardinality": rel.relation_type,
        }
        adj.setdefault(s, []).append(edge_data)
        adj.setdefault(t, []).append(
            {
                "source": t,
                "target": s,
                "relationCode": rel.relation_code,
                "relationCardinality": rel.relation_type,
            }
        )

    # Determine seed object codes
    seed_codes: set[str]
    seed_codes = set(object_codes) if object_codes else set(loader._classes.keys())

    # Expand by depth if requested
    effective_codes = seed_codes.copy()
    if depth is not None:
        frontier = seed_codes.copy()
        for _ in range(depth):
            next_frontier: set[str] = set()
            for code in frontier:
                for edge_data in adj.get(code, []):
                    neighbor = edge_data["target"]
                    if neighbor not in effective_codes:
                        next_frontier.add(neighbor)
                        effective_codes.add(neighbor)
            frontier = next_frontier
            if not frontier:
                break

    # Build nodes — only for objects that exist in loader._classes
    for code in sorted(effective_codes):
        if code not in loader._classes:
            continue
        cls = loader._classes[code]
        nodes[code] = {
            "code": cls.object_code,
            "label": cls.object_name,
            "description": cls.description,
        }

    # Build edges — only between objects in the effective set
    seen_edges: set[tuple[str, str]] = set()
    for code in effective_codes:
        for edge_data in adj.get(code, []):
            target = edge_data["target"]
            if target not in effective_codes:
                continue
            key = (min(code, target), max(code, target))
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append(edge_data)


class LocalOntologyAdapter:
    """Local ontology adapter - implements OntologyRepository via datacloud-data SDK.

    Read path: OWL files -> OwlParser -> OntologyLoader -> OntologyClass
    Write path: JSONWriter -> atomic JSON file I/O -> reload loader
    """

    def __init__(self, data_dir: str, writer: JSONWriter) -> None:
        self.data_dir = Path(data_dir)
        self.writer = writer
        self._loaders: dict[str, OntologyLoader] = {}

    # -- internal helpers --

    def _get_loader(self, base_id: str) -> OntologyLoader:
        """Get or create OntologyLoader for a base, loading OWL data."""
        if base_id not in self._loaders:
            loader = OntologyLoader()
            base_path = self.data_dir / base_id
            if base_path.exists():
                loader.load_from_owl_resource_directory(str(base_path))
            self._loaders[base_id] = loader
        return self._loaders[base_id]

    def _reload_loader(self, base_id: str) -> OntologyLoader:
        """Force-reload loader after writes."""
        loader = OntologyLoader()
        base_path = self.data_dir / base_id
        if base_path.exists():
            loader.load_from_owl_resource_directory(str(base_path))
        self._loaders[base_id] = loader
        return loader

    def _scene_path(self, base_id: str, scene_id: str) -> Path:
        return self.data_dir / base_id / scene_id

    # -- Scene: read --

    def list_scenes(self, base_id: str) -> list[dict]:
        base_path = self.data_dir / base_id
        if not base_path.exists():
            return []
        return [
            {"sceneId": item.name, "sceneName": item.name, "sceneCode": item.name, "sceneDesc": ""}
            for item in sorted(base_path.iterdir())
            if item.is_dir()
        ]

    def get_scene(self, base_id: str, scene_id: str) -> dict | None:
        scene_path = self._scene_path(base_id, scene_id)
        if not scene_path.exists():
            return None
        return {
            "sceneId": scene_id,
            "sceneName": scene_id,
            "sceneCode": scene_id,
            "sceneDesc": "",
        }

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict]:
        scenes = self.list_scenes(base_id)
        if not keyword:
            return scenes
        kw = keyword.strip().lower()
        return [
            s
            for s in scenes
            if kw in s.get("sceneName", "").lower() or kw in s.get("sceneCode", "").lower()
        ]

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        return len(self.query_scenes(base_id, keyword))

    def get_scene_details(
        self,
        base_id: str,
        scene_id: str,
        *,
        view_code: str | None = None,
        object_code: str | None = None,
    ) -> dict:
        """Get full scene details with optional associated resource filtering.

        - viewCode: return only those views + associated objects/actions/relations/dbsources
        - objectCode: return only those objects + associated actions/relations/dbsources (views empty)
        - neither: full dump
        """
        scene = self.get_scene(base_id, scene_id)
        all_objects = self.get_objects(base_id, scene_id)
        all_views = self.get_views(base_id, scene_id)
        all_relations = self.get_relations(base_id, scene_id)
        all_actions: list[dict] = []
        for obj in all_objects:
            obj_code = obj.get("objectCode", "")
            all_actions.extend(self.get_actions(base_id, scene_id, obj_code))
        all_dbsources = self.get_datasources(base_id, scene_id)

        view_codes: set[str] | None = None
        object_codes: set[str] | None = None

        if view_code:
            view_codes = {vc.strip() for vc in view_code.split(",") if vc.strip()}
        if object_code:
            object_codes = {oc.strip() for oc in object_code.split(",") if oc.strip()}

        # Determine affected object codes
        affected_object_codes: set[str] | None = None
        if view_codes:
            filtered_views = [v for v in all_views if v.get("viewCode") in view_codes]
            affected_object_codes = set()
            for v in filtered_views:
                for oc in v.get("objectCodes", []):
                    affected_object_codes.add(oc)
        elif object_codes:
            filtered_views = []
            affected_object_codes = object_codes
        else:
            filtered_views = all_views
            affected_object_codes = None

        if affected_object_codes is not None:
            filtered_objects = [
                o for o in all_objects if o.get("objectCode") in affected_object_codes
            ]
            filtered_actions = [
                a for a in all_actions if a.get("belongObjectCode") in affected_object_codes
            ]
            filtered_relations = [
                r
                for r in all_relations
                if r.get("sourceObjectCode") in affected_object_codes
                or r.get("targetObjectCode") in affected_object_codes
            ]
            # dbsources: keep those referenced by filtered objects' properties
            filtered_dbsources = (
                [
                    d
                    for d in all_dbsources
                    if any(
                        p.get("dbId") == d.get("db", [{}])[0].get("dbId")
                        for o in filtered_objects
                        for p in o.get("properties", [])
                    )
                ]
                if any(o.get("properties") for o in filtered_objects)
                else all_dbsources
            )
        else:
            filtered_objects = all_objects
            filtered_actions = all_actions
            filtered_relations = all_relations
            filtered_dbsources = all_dbsources

        return {
            "scene": scene,
            "views": filtered_views,
            "objects": filtered_objects,
            "actions": filtered_actions,
            "relations": filtered_relations,
            "dbsources": filtered_dbsources,
            "version": None,
        }

    def query_ontologies_by_scene(
        self,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict:
        """Query ontologies (objects) in a scene with pagination and keyword filter.

        Returns: {"data": [...OntologySummary dicts], "totalCount": N}
        """
        objects = self.get_objects(base_id, scene_id)
        if keyword:
            kw = keyword.strip().lower()
            objects = [
                o
                for o in objects
                if kw in o.get("objectName", "").lower()
                or kw in o.get("objectCode", "").lower()
                or kw in o.get("objectDesc", "").lower()
            ]
        total = len(objects)
        start = (page - 1) * page_size
        # Convert to OntologySummary format
        summaries = [
            {
                "ontologyId": o.get("objectCode", ""),
                "sceneId": scene_id,
                "ontologyName": o.get("objectName", ""),
                "ontologyCode": o.get("objectCode", ""),
                "ontologySource": o.get("objectSource"),
                "ontologyDesc": o.get("objectDesc"),
                "conceptType": o.get("conceptType"),
                "ontologyType": o.get("objectType"),
                "domainType": o.get("domainType"),
            }
            for o in objects[start : start + page_size]
        ]
        return {"data": summaries, "totalCount": total}

    # -- Object: read --

    def get_objects(self, base_id: str, scene_id: str) -> list[dict]:
        """List objects: returns ObjectTypeSummary (fieldCount + actionCount)."""
        loader = self._get_loader(base_id)
        objects: list[dict] = []
        seen_codes: set[str] = set()

        for ont_class in loader._classes.values():
            objects.append(self._ontology_class_to_summary(ont_class))
            seen_codes.add(ont_class.object_code)

        scene_path = self._scene_path(base_id, scene_id)
        objects_dir = scene_path / "objects"
        if objects_dir.exists():
            for json_file in sorted(objects_dir.glob("*.json")):
                code = json_file.stem
                if code not in seen_codes:
                    data = _json.loads(json_file.read_text(encoding="utf-8"))
                    objects.append(self._json_obj_to_summary(data))
                    seen_codes.add(code)

        return objects

    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None:
        """Get object detail: returns full ObjectType with properties[].terminology, actions[].params[]."""
        loader = self._get_loader(base_id)
        try:
            ont_class = loader.get_ontology_class(object_code)
            return self._ontology_class_to_detail(ont_class)
        except Exception as e:
            logger.debug(
                "Object '%s' not found in loader, trying JSON: %s: %s",
                object_code,
                type(e).__name__,
                e,
            )

        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "objects" / f"{object_code}.json"
        if file_path.exists():
            data = _json.loads(file_path.read_text(encoding="utf-8"))
            return self._json_obj_to_detail(data)

        logger.warning("Object '%s' not found", object_code)
        return None

    # -- View: read --

    def get_views(self, base_id: str, scene_id: str) -> list[dict]:
        loader = self._get_loader(base_id)
        views: list[dict] = []
        seen_codes: set[str] = set()

        for vid, scene in loader._scenes.items():
            views.append(
                {
                    "viewCode": vid,
                    "viewName": scene.get("view_name", vid),
                    "description": scene.get("description", ""),
                    "objectCodes": self._extract_object_codes(scene),
                    "properties": [],  # Views from loader don't have explicit properties
                }
            )
            seen_codes.add(vid)

        scene_path = self._scene_path(base_id, scene_id)
        views_dir = scene_path / "views"
        if views_dir.exists():
            for json_file in sorted(views_dir.glob("*.json")):
                code = json_file.stem
                if code not in seen_codes:
                    data = _json.loads(json_file.read_text(encoding="utf-8"))
                    # Ensure properties field exists
                    if "properties" not in data:
                        data["properties"] = []
                    views.append(data)
                    seen_codes.add(code)

        return views

    def get_view_detail(self, base_id: str, scene_id: str, view_code: str) -> dict | None:
        loader = self._get_loader(base_id)
        if view_code in loader._scenes:
            scene = loader._scenes[view_code]
            return {
                "viewCode": view_code,
                "viewName": scene.get("view_name", view_code),
                "description": scene.get("description", ""),
                "objectCodes": self._extract_object_codes(scene),
                "properties": [],
            }

        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "views" / f"{view_code}.json"
        if file_path.exists():
            data = _json.loads(file_path.read_text(encoding="utf-8"))
            if "properties" not in data:
                data["properties"] = []
            return data

        return None

    # -- Relation: read --

    def get_relations(self, base_id: str, scene_id: str) -> list[dict]:
        loader = self._get_loader(base_id)
        seen_codes: set[str] = set()
        relations: list[dict] = []

        for r in loader._relations:
            rel = {
                "relationCode": r.relation_code or "",
                "relationName": getattr(r, "relation_name", ""),
                "sourceObjectCode": r.source_class,
                "targetObjectCode": r.target_class,
                "relationCardinality": r.relation_type,
                "joinKeys": r.join_keys,
            }
            relations.append(rel)
            if rel["relationCode"]:
                seen_codes.add(rel["relationCode"])

        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "relations.json"
        if file_path.exists():
            data = _json.loads(file_path.read_text(encoding="utf-8"))
            for rel in data.get("relations", []):
                code = rel.get("relationCode", "")
                if code and code not in seen_codes:
                    # Normalize field names
                    normalized_rel = self._normalize_relation(rel)
                    relations.append(normalized_rel)
                    seen_codes.add(code)

        return relations

    def get_relation_detail(self, base_id: str, scene_id: str, rel_code: str) -> dict | None:
        relations = self.get_relations(base_id, scene_id)
        for r in relations:
            if r.get("relationCode") == rel_code:
                return r
        return None

    @staticmethod
    def _normalize_relation(rel: dict) -> dict:
        """Normalize relation dict to API field names: sourceObjectCode, targetObjectCode, relationCardinality."""
        return {
            "relationCode": rel.get("relationCode", rel.get("relation_code", "")),
            "relationName": rel.get("relationName", rel.get("relation_name", "")),
            "sourceObjectCode": rel.get(
                "sourceObjectCode", rel.get("sourceClass", rel.get("source_class", ""))
            ),
            "targetObjectCode": rel.get(
                "targetObjectCode", rel.get("targetClass", rel.get("target_class", ""))
            ),
            "relationCardinality": rel.get(
                "relationCardinality", rel.get("relationType", rel.get("relation_type", ""))
            ),
            "relationDesc": rel.get("relationDesc", rel.get("relation_desc")),
            "relationSceneType": rel.get("relationSceneType", rel.get("relation_scene_type")),
            "objectRelationId": rel.get("objectRelationId", rel.get("object_relation_id")),
            "sourceObjectName": rel.get("sourceObjectName", rel.get("source_object_name")),
            "targetObjectName": rel.get("targetObjectName", rel.get("target_object_name")),
            "srcMetaId": rel.get("srcMetaId", rel.get("src_meta_id")),
            "srcColumnId": rel.get("srcColumnId", rel.get("src_column_id")),
            "targetMetaId": rel.get("targetMetaId", rel.get("target_meta_id")),
            "targetColumnId": rel.get("targetColumnId", rel.get("target_column_id")),
            "attribute": rel.get("attribute"),
            "sortNo": rel.get("sortNo", rel.get("sort_no", 0)),
            "status": rel.get("status", 0),
        }

    # -- metadata: write --

    def create_object(self, base_id: str, scene_id: str, obj: ObjectType) -> ObjectType:
        self._validate_object(obj)
        scene_path = self._scene_path(base_id, scene_id)
        obj_data = obj.model_dump(by_alias=True)
        file_path = scene_path / "objects" / f"{obj_data['objectCode']}.json"
        if file_path.exists():
            raise ValueError(f"Object '{obj_data['objectCode']}' already exists")
        self.writer.write_object(scene_path, obj_data)
        self._reload_loader(base_id)
        return obj

    def update_object(
        self, base_id: str, scene_id: str, _object_code: str, obj: ObjectType
    ) -> ObjectType:
        self._validate_object(obj)
        scene_path = self._scene_path(base_id, scene_id)
        obj_data = obj.model_dump(by_alias=True)
        self.writer.write_object(scene_path, obj_data)
        self._reload_loader(base_id)
        return obj

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        self.writer.delete_object(self._scene_path(base_id, scene_id), object_code)
        self._reload_loader(base_id)

    def create_view(self, base_id: str, scene_id: str, view: View) -> View:
        scene_path = self._scene_path(base_id, scene_id)
        view_data = view.model_dump(by_alias=True)
        view_code = view_data.get("viewCode", view.view_code)
        file_path = scene_path / "views" / f"{view_code}.json"
        if file_path.exists():
            raise ValueError(f"View '{view_code}' already exists")
        self.writer.write_view(scene_path, view_data)
        self._reload_loader(base_id)
        return view

    def update_view(self, base_id: str, scene_id: str, _view_code: str, view: View) -> View:
        scene_path = self._scene_path(base_id, scene_id)
        view_data = view.model_dump(by_alias=True)
        self.writer.write_view(scene_path, view_data)
        self._reload_loader(base_id)
        return view

    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None:
        self.writer.delete_view(self._scene_path(base_id, scene_id), view_code)
        self._reload_loader(base_id)

    def create_relation(self, base_id: str, scene_id: str, rel: Relation) -> Relation:
        scene_path = self._scene_path(base_id, scene_id)
        rel_data = rel.model_dump(by_alias=True)
        file_path = scene_path / "relations.json"
        existing: list[dict] = []
        if file_path.exists():
            existing = _json.loads(file_path.read_text(encoding="utf-8")).get("relations", [])
        for r in existing:
            if r.get("relationCode") == rel_data.get("relationCode"):
                raise ValueError(f"Relation '{rel_data['relationCode']}' already exists")
        existing.append(rel_data)
        self.writer.write_relation(scene_path, existing)
        self._reload_loader(base_id)
        return rel

    def update_relation(
        self, base_id: str, scene_id: str, rel_code: str, rel: Relation
    ) -> Relation:
        scene_path = self._scene_path(base_id, scene_id)
        rel_data = rel.model_dump(by_alias=True)
        file_path = scene_path / "relations.json"
        existing: list[dict] = []
        if file_path.exists():
            existing = _json.loads(file_path.read_text(encoding="utf-8")).get("relations", [])
        updated = False
        for i, r in enumerate(existing):
            if r.get("relationCode") == rel_code:
                existing[i] = rel_data
                updated = True
                break
        if not updated:
            raise KeyError(f"Relation '{rel_code}' not found")
        self.writer.write_relation(scene_path, existing)
        self._reload_loader(base_id)
        return rel

    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None:
        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "relations.json"
        if not file_path.exists():
            return
        existing = _json.loads(file_path.read_text(encoding="utf-8")).get("relations", [])
        filtered = [r for r in existing if r.get("relationCode") != rel_code]
        self.writer.write_relation(scene_path, filtered)
        self._reload_loader(base_id)

    # -- datasource --

    def get_datasources(self, base_id: str, scene_id: str) -> list[dict]:
        scene_path = self._scene_path(base_id, scene_id)
        ds_dir = scene_path / "datasources"
        if not ds_dir.exists():
            return []
        result: list[dict] = [
            _json.loads(json_file.read_text(encoding="utf-8"))
            for json_file in sorted(ds_dir.glob("*.json"))
        ]
        return result

    def get_datasource_detail(self, base_id: str, scene_id: str, db_id: str) -> dict | None:
        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "datasources" / f"{db_id}.json"
        if file_path.exists():
            return _json.loads(file_path.read_text(encoding="utf-8"))
        return None

    def _extract_db_id(self, ds_data: dict) -> str:
        """Extract db_id from nested Datasource or flat legacy format."""
        # Nested: {"db": [{"dbId": "pg1", ...}], ...}
        if "db" in ds_data and isinstance(ds_data["db"], list) and ds_data["db"]:
            db_entry: dict = ds_data["db"][0]
            return str(db_entry.get("dbId", ""))
        # Flat legacy: {"dbId": "pg1", ...}
        return str(ds_data.get("dbId", ds_data.get("db_id", "")))

    def create_datasource(self, base_id: str, scene_id: str, ds: Datasource) -> Datasource:
        scene_path = self._scene_path(base_id, scene_id)
        ds_data = ds.model_dump(by_alias=True)
        db_id = self._extract_db_id(ds_data)
        ds_dir = scene_path / "datasources"
        self.writer.ensure_dir(ds_dir)
        file_path = ds_dir / f"{db_id}.json"
        if file_path.exists():
            raise ValueError(f"Datasource '{db_id}' already exists")
        self.writer._atomic_write(file_path, ds_data)
        return ds

    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None:
        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "datasources" / f"{db_id}.json"
        if file_path.exists():
            file_path.unlink()

    # -- action --

    def get_actions(self, base_id: str, scene_id: str, object_code: str) -> list[dict]:
        """Get actions for an object."""
        obj = self.get_object_detail(base_id, scene_id, object_code)
        if obj is None:
            return []
        return obj.get("actions", [])

    def get_action_detail(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> dict | None:
        """Get action detail."""
        actions = self.get_actions(base_id, scene_id, object_code)
        for a in actions:
            if a.get("actionCode") == action_code:
                return a
        return None

    def create_action(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action: Action,
    ) -> Action:
        """Create an action on an object."""
        scene_path = self._scene_path(base_id, scene_id)
        action_data = action.model_dump(by_alias=True)
        file_path = scene_path / "objects" / f"{object_code}.json"
        if not file_path.exists():
            raise KeyError(f"Object '{object_code}' not found")
        obj = _json.loads(file_path.read_text(encoding="utf-8"))
        existing = obj.get("actions", [])
        for a in existing:
            if a.get("actionCode") == action_data.get("actionCode"):
                raise ValueError(f"Action '{action_data['actionCode']}' already exists")
        existing.append(action_data)
        obj["actions"] = existing
        self.writer._atomic_write(file_path, obj)
        self._reload_loader(base_id)
        return action

    def update_action(
        self,
        base_id: str,
        scene_id: str,
        object_code: str,
        action_code: str,
        action: Action,
    ) -> Action:
        """Update an action on an object."""
        scene_path = self._scene_path(base_id, scene_id)
        action_data = action.model_dump(by_alias=True)
        file_path = scene_path / "objects" / f"{object_code}.json"
        if not file_path.exists():
            raise KeyError(f"Object '{object_code}' not found")
        obj = _json.loads(file_path.read_text(encoding="utf-8"))
        existing = obj.get("actions", [])
        updated = False
        for i, a in enumerate(existing):
            if a.get("actionCode") == action_code:
                existing[i] = action_data
                updated = True
                break
        if not updated:
            raise KeyError(f"Action '{action_code}' not found on object '{object_code}'")
        obj["actions"] = existing
        self.writer._atomic_write(file_path, obj)
        self._reload_loader(base_id)
        return action

    def delete_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> None:
        """Delete an action from an object."""
        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "objects" / f"{object_code}.json"
        if not file_path.exists():
            return
        obj = _json.loads(file_path.read_text(encoding="utf-8"))
        existing = obj.get("actions", [])
        filtered = [a for a in existing if a.get("actionCode") != action_code]
        if len(filtered) == len(existing):
            return  # action not found, no-op
        obj["actions"] = filtered
        self.writer._atomic_write(file_path, obj)
        self._reload_loader(base_id)

    # -- OWL import --

    def import_owl(self, base_id: str, scene_id: str, zip_bytes: bytes) -> dict:
        """Import OWL definitions from a ZIP file.

        Flow:
            1. Unzip to temp directory
            2. Parse OWL via OwlParser.parse_resource_directory()
            3. Write objects/views/relations via JSONWriter
            4. Reload loader

        Returns:
            {"objects": N, "views": N, "relations": N}
        """
        tmp_path = Path(tempfile.mkdtemp(prefix="owl_import_"))
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(tmp_path)

            parser = OwlParser()
            content = parser.parse_resource_directory(tmp_path)

            scene_path = self._scene_path(base_id, scene_id)

            # Write objects (parser uses snake_case, writer expects camelCase)
            objects_count = 0
            for obj in content.get("objects", []):
                obj_data = self._parser_obj_to_writer(obj)
                self.writer.write_object(scene_path, obj_data)
                objects_count += 1

            # Write views
            views_count = 0
            for view in content.get("views", []):
                view_data = {
                    "viewCode": view["view_id"],
                    "viewName": view.get("view_name", view["view_id"]),
                    "description": view.get("description", ""),
                    "objectCodes": [
                        obj.get("object_code", obj.get("objectCode", ""))
                        for obj in view.get("objects", [])
                    ],
                    "properties": [],
                }
                self.writer.write_view(scene_path, view_data)
                views_count += 1

            # Write relations
            relations = content.get("relations", [])
            if relations:
                self.writer.write_relation(scene_path, relations)

            # Reload loader
            self._reload_loader(base_id)

            return {
                "objects": objects_count,
                "views": views_count,
                "relations": len(relations),
            }
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    # -- application services --

    def search_instances(
        self,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,  # noqa: ARG002  # reserved: future search filtering
        where: dict | None = None,
    ) -> dict:
        """Search ontology objects by keyword.

        Args:
            base_id: Ontology base identifier.
            object_code: Filter to a single object code.
            select: Optional field list (unused in local adapter).
            where: Optional filter conditions (unused in local adapter).

        Returns:
            {"data": [object_dict, ...], "totalCount": N}
        """
        loader = self._get_loader(base_id)
        keyword_str = (where or {}).get("keyword", "") if where else ""

        if not keyword_str:
            classes = list(loader._classes.values())
            if object_code:
                classes = [c for c in classes if c.object_code == object_code]
            total = len(classes)
            data = [self._ontology_class_to_summary(c) for c in classes]
            return {"data": data, "totalCount": total}

        matches: list[dict] = []
        for cls in loader._classes.values():
            if object_code and cls.object_code != object_code:
                continue
            if not self._class_matches_keyword(cls, keyword_str.strip().lower()):
                continue
            matches.append(self._ontology_class_to_summary(cls))

        return {"data": matches, "totalCount": len(matches)}

    @staticmethod
    def _class_matches_keyword(ont_class: object, keyword: str) -> bool:
        """Check if OntologyClass matches a keyword (case-insensitive)."""
        if keyword in ont_class.object_code.lower():
            return True
        if keyword in ont_class.object_name.lower():
            return True
        if keyword in ont_class.description.lower():
            return True
        for field in ont_class.fields:
            if keyword in field.field_code.lower():
                return True
            if keyword in field.field_name.lower():
                return True
        return False

    def search_ontology(
        self,
        base_id: str,
        scene_id: str,
        *,
        keyword: str,
        query_type: str = "vector",  # reserved: future search mode
        search_scope: str = "all",
        object_code: list[str] | None = None,  # noqa: ARG002  # reserved: future scope filter
        view_code: list[str] | None = None,  # noqa: ARG002  # reserved: future scope filter
        property_code: list[str] | None = None,  # noqa: ARG002  # reserved: future scope filter
        result_per_type: int = 5,  # reserved: future result count
        page_size: int = 20,  # noqa: ARG002  # reserved: future paging
        page_token: str | None = None,  # noqa: ARG002  # reserved: future pagination
    ) -> dict:
        """Unified search across single scene or all scenes (scene_id='-1')."""
        if scene_id and scene_id != "-1":
            return self._search_single_scene(
                base_id,
                scene_id,
                keyword=keyword,
                query_type=query_type,
                search_scope=search_scope,
                result_per_type=result_per_type,
            )
        # Global search: iterate all scenes under the base
        return self._search_all_scenes(
            base_id,
            keyword=keyword,
            query_type=query_type,
            search_scope=search_scope,
            result_per_type=result_per_type,
        )

    def _search_single_scene(
        self,
        base_id: str,
        scene_id: str,
        *,
        keyword: str,
        query_type: str = "vector",  # noqa: ARG002  # reserved: future search mode
        search_scope: str = "all",
        result_per_type: int = 5,  # noqa: ARG002  # reserved: future result count
    ) -> dict:
        """Vector search across metadata and instance terms within a single scene.

        Uses embedding model to encode keyword, then pgvector cosine distance.
        Returns per-resultType metadata fields and enriched instance hits.

        Returns:
            {"metadata": [MetadataHit-like dicts], "instances": [InstanceHit-like dicts],
             "totalCount": {"metadata": int, "instances": int}}
        """
        if not keyword:
            return {"metadata": [], "instances": [], "totalCount": {"metadata": 0, "instances": 0}}

        vec_str = self._embed_and_encode(keyword)
        engine = self._get_search_engine()

        result: dict = {
            "metadata": [],
            "instances": [],
            "totalCount": {"metadata": 0, "instances": 0},
        }

        # Pre-load loader for enrichment (objectSource, view description, etc.)
        loader = None
        with suppress(Exception):
            loader = self._get_loader(base_id)

        with engine.connect() as conn:
            # -- metadata branch --
            if search_scope in ("metadata", "all"):
                rows = conn.execute(
                    text(
                        """SELECT tn.name_text, t.term_code, t.term_type_code,
                                  t.term_name, t.desc_summary,
                                  1 - (tn.name_embedding <=> :vec) AS score
                           FROM byai.term_name tn
                           JOIN byai.term t ON t.term_id = tn.term_id
                           WHERE t.term_type_code IN ('object','view','prop','action','func')
                             AND tn.name_embedding IS NOT NULL
                           ORDER BY tn.name_embedding <=> :vec
                           LIMIT 20"""
                    ),
                    {"vec": vec_str},
                ).fetchall()

                result["metadata"] = [
                    self._build_metadata_hit(
                        conn=conn,
                        scene_id=scene_id,
                        term_code=row[1],
                        term_type=row[2],
                        term_name=row[3],
                        desc_summary=row[4] or "",
                        matched_value=row[0],
                        score=round(float(row[5]), 4),
                        loader=loader,
                    )
                    for row in rows
                ]
                result["totalCount"]["metadata"] = len(result["metadata"])

            # -- instance branch --
            if search_scope in ("instance", "all"):
                rows = conn.execute(
                    text(
                        """SELECT tn.name_text, t.term_code, t.term_type_code,
                                  t.term_name, t.term_id,
                                  1 - (tn.name_embedding <=> :vec) AS score
                           FROM byai.term_name tn
                           JOIN byai.term t ON t.term_id = tn.term_id
                           JOIN byai.term_type tt ON tt.type_code = t.term_type_code
                           WHERE tt.type_category IN (1, 2)
                             AND tn.name_embedding IS NOT NULL
                           ORDER BY tn.name_embedding <=> :vec
                           LIMIT 20"""
                    ),
                    {"vec": vec_str},
                ).fetchall()

                instance_items: list[dict] = []
                for row in rows:
                    value_name = row[0]
                    value_code = row[1]
                    value_type = row[2]
                    value_term_id = row[4]
                    score = round(float(row[5]), 4)

                    # Resolve: value term -> property -> object
                    prop_info = self._resolve_value_to_property(conn, value_term_id)
                    object_code = prop_info.get("objectCode", "")
                    property_code = prop_info.get("propertyCode", value_type)

                    # objectName: JOIN term table
                    object_name = (
                        self._get_term_name(conn, object_code, "object") if object_code else ""
                    )

                    # isEnumType: does this value's type_code also exist as an object type?
                    is_enum = self._check_is_enum_type(conn, value_type)

                    # referencedByProperties: only for enum types
                    referenced_by: list[dict] = (
                        self._resolve_referenced_by_properties(conn, value_term_id)
                        if is_enum
                        else []
                    )

                    # properties fallback (local adapter has no instance storage)
                    properties = {
                        "matchedValue": value_name,
                        "matchedProperty": property_code,
                    }

                    instance_items.append(
                        {
                            "sceneId": scene_id,
                            "objectCode": object_code,
                            "objectName": object_name,
                            "primaryKey": value_code,
                            "matchedProperty": property_code,
                            "matchedValue": value_name,
                            "isEnumType": is_enum,
                            "referencedByProperties": referenced_by,
                            "score": score,
                            "properties": properties,
                        }
                    )
                result["instances"] = instance_items
                result["totalCount"]["instances"] = len(result["instances"])

        return result

    def search_ontology_batch(
        self,
        base_id: str,
        scene_id: str,
        *,
        keywords: list[str],
        search_scope: str = "all",
        object_code: list[str] | None = None,  # noqa: ARG002  # reserved: future scope filter
        view_code: list[str] | None = None,  # noqa: ARG002  # reserved: future scope filter
        result_per_type: int = 5,  # noqa: ARG002  # reserved: future result count
    ) -> list[dict]:
        """Batch vector search for multiple keywords in a single scene.

        Builds UNION ALL SQL with one SELECT per keyword, each embedding its own
        pgvector <=> operator. Returns a flat list of hit dicts, each tagged with
        ``_keyword_index`` (int) for downstream fusion.
        """
        valid_keywords = [k for k in keywords if k]
        if not valid_keywords:
            return []

        vecs = [self._embed_and_encode(k) for k in valid_keywords]
        engine = self._get_search_engine()

        loader = None
        with suppress(Exception):
            loader = self._get_loader(base_id)

        hits: list[dict] = []

        with engine.connect() as conn:
            # -- metadata branch --
            if search_scope in ("metadata", "all"):
                selects: list[str] = []
                params: dict[str, str] = {}
                for i, vec in enumerate(vecs):
                    pname = f"vec_{i}"
                    selects.append(
                        f"SELECT {i} AS keyword_index,"
                        " tn.name_text, t.term_code, t.term_type_code,"
                        " t.term_name, t.desc_summary,"
                        f" 1 - (tn.name_embedding <=> :{pname}) AS score"
                        " FROM byai.term_name tn"
                        " JOIN byai.term t ON t.term_id = tn.term_id"
                        " WHERE t.term_type_code IN"
                        " ('object','view','prop','action','func')"
                        " AND tn.name_embedding IS NOT NULL"
                        f" ORDER BY tn.name_embedding <=> :{pname}"
                        " LIMIT 20"
                    )
                    params[pname] = vec

                union_sql = "\nUNION ALL\n".join(f"({s})" for s in selects)
                rows = conn.execute(text(union_sql), params).fetchall()

                for row in rows:
                    hit = self._build_metadata_hit(
                        conn=conn,
                        scene_id=scene_id,
                        term_code=row[2],
                        term_type=row[3],
                        term_name=row[4],
                        desc_summary=row[5] or "",
                        matched_value=row[1],
                        score=round(float(row[6]), 4),
                        loader=loader,
                    )
                    hit["_keyword_index"] = row[0]
                    hits.append(hit)

            # -- instance branch --
            if search_scope in ("instance", "all"):
                selects = []
                params = {}
                for i, vec in enumerate(vecs):
                    pname = f"vec_{i}"
                    selects.append(
                        f"SELECT {i} AS keyword_index,"
                        " tn.name_text, t.term_code, t.term_type_code,"
                        " t.term_name, t.term_id,"
                        f" 1 - (tn.name_embedding <=> :{pname}) AS score"
                        " FROM byai.term_name tn"
                        " JOIN byai.term t ON t.term_id = tn.term_id"
                        " JOIN byai.term_type tt ON tt.type_code = t.term_type_code"
                        " WHERE tt.type_category IN (1, 2)"
                        " AND tn.name_embedding IS NOT NULL"
                        f" ORDER BY tn.name_embedding <=> :{pname}"
                        " LIMIT 20"
                    )
                    params[pname] = vec

                union_sql = "\nUNION ALL\n".join(f"({s})" for s in selects)
                rows = conn.execute(text(union_sql), params).fetchall()

                for row in rows:
                    value_name = row[1]
                    value_code = row[2]
                    value_type = row[3]
                    value_term_id = row[5]
                    score = round(float(row[6]), 4)

                    prop_info = self._resolve_value_to_property(conn, value_term_id)
                    obj_code = prop_info.get("objectCode", "")
                    property_code = prop_info.get("propertyCode", value_type)
                    object_name = self._get_term_name(conn, obj_code, "object") if obj_code else ""
                    is_enum = self._check_is_enum_type(conn, value_type)
                    referenced_by: list[dict] = (
                        self._resolve_referenced_by_properties(conn, value_term_id)
                        if is_enum
                        else []
                    )

                    hits.append(
                        {
                            "sceneId": scene_id,
                            "objectCode": obj_code,
                            "objectName": object_name,
                            "primaryKey": value_code,
                            "matchedProperty": property_code,
                            "matchedValue": value_name,
                            "isEnumType": is_enum,
                            "referencedByProperties": referenced_by,
                            "score": score,
                            "properties": {
                                "matchedValue": value_name,
                                "matchedProperty": property_code,
                            },
                            "_keyword_index": row[0],
                        }
                    )

        return hits

    def _search_all_scenes(
        self,
        base_id: str,
        *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        result_per_type: int = 5,
    ) -> dict:
        """Iterate all scenes under the base, merge results."""
        scenes = self.list_scenes(base_id)
        all_metadata: list[dict] = []
        all_instances: list[dict] = []
        for s in scenes:
            result = self._search_single_scene(
                base_id,
                s.get("sceneId", ""),
                keyword=keyword,
                query_type=query_type,
                search_scope=search_scope,
                result_per_type=result_per_type,
            )
            all_metadata.extend(result.get("metadata", []))
            all_instances.extend(result.get("instances", []))
        return {
            "metadata": all_metadata,
            "instances": all_instances,
            "totalCount": {
                "metadata": len(all_metadata),
                "instances": len(all_instances),
            },
        }

    def graph_query(
        self,
        base_id: str,
        _scene_id: str,
        *,
        object_code: list[str],
        match_by: str = "name",  # noqa: ARG002  # reserved: future match mode
        values: list[str] | None = None,  # noqa: ARG002  # reserved: future match values
        step: int = 1,
    ) -> dict:
        """Build a graph of objects and their relations.

        Args:
            base_id: Ontology base identifier.
            scene_id: Scene identifier (unused in local adapter).
            object_code: Filter to these object codes.
            match_by: Match mode (unused in local adapter).
            values: Optional match values (unused in local adapter).
            step: Maximum hop depth (BFS expansion).

        Returns:
            {"nodes": [{"code": str, "label": str, "description": str}, ...],
             "edges": [{"source": str, "target": str, "relationCode": str,
                        "relationCardinality": str}, ...]}
        """
        loader = self._get_loader(base_id)
        object_codes = object_code if object_code else None
        # step=1 (default) means no BFS expansion — only filter by object codes.
        # step > 1 means BFS expand up to step hops from seed objects.
        depth = step if step > 1 else None

        nodes: dict[str, dict] = {}
        edges: list[dict] = []

        _add_nodes_and_edges(loader, object_codes, depth, nodes, edges)

        return {"nodes": list(nodes.values()), "edges": edges}

    def graph_path(
        self,
        base_id: str,
        _scene_id: str,
        *,
        match_by: str = "name",  # noqa: ARG002  # reserved: future match mode
        start_node: str,
        end_node: str = "",
        direction: str = "forward",  # noqa: ARG002  # reserved: future traversal direction
    ) -> dict:
        """Find shortest path between two objects in the relation graph.

        Args:
            base_id: Ontology base identifier.
            scene_id: Scene identifier (unused in local adapter).
            match_by: Match mode (unused in local adapter).
            start_node: Source object code.
            end_node: Target object code.
            direction: Path direction (unused in local adapter).

        Returns:
            {"path": [str, ...], "edges": [...], "hops": int}
            — hops == -1 when no path exists.
        """
        loader = self._get_loader(base_id)
        source = start_node
        target = end_node

        if not source or not target:
            return {"path": [], "edges": [], "hops": -1}

        # Build undirected adjacency
        adj: dict[str, list[tuple[str, dict]]] = {}
        for rel in loader._relations:
            s, t = rel.source_class, rel.target_class
            edge_data = {
                "source": s,
                "target": t,
                "relationCode": rel.relation_code,
                "relationCardinality": rel.relation_type,
            }
            adj.setdefault(s, []).append((t, edge_data))
            adj.setdefault(t, []).append((s, edge_data))

        # Same node
        if source == target:
            return {"path": [source], "edges": [], "hops": 0}

        # Source or target not in graph
        if source not in adj or target not in adj:
            return {"path": [], "edges": [], "hops": -1}

        # BFS
        queue: deque[list[str]] = deque([[source]])
        visited: set[str] = {source}
        while queue:
            path = queue.popleft()
            node = path[-1]
            if node == target:
                # Reconstruct edges from path
                hops = len(path) - 1
                path_edges: list[dict] = []
                for i in range(len(path) - 1):
                    u, v = path[i], path[i + 1]
                    # Find the matching edge
                    for neighbor, edge_data in adj[u]:
                        if neighbor == v:
                            path_edges.append(edge_data)
                            break
                return {"path": path, "edges": path_edges, "hops": hops}
            for neighbor, _edge_data in adj[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append([*path, neighbor])

        return {"path": [], "edges": [], "hops": -1}

    # -- helpers --

    @staticmethod
    def _embed_and_encode(keyword: str) -> str:
        """Embed keyword via DashScope and return pgvector string."""
        api_key = os.environ.get("DATACLOUD_EMBEDDING_API_KEY", "")
        api_base = os.environ.get(
            "DATACLOUD_EMBEDDING_API_BASE",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        model = os.environ.get("DATACLOUD_EMBEDDING_MODEL", "text-embedding-v4")

        resp = requests.post(
            f"{api_base}/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "input": [keyword]},
            timeout=10,
        )
        resp.raise_for_status()
        vec = resp.json()["data"][0]["embedding"]
        return "[" + ",".join(str(x) for x in vec) + "]"

    @staticmethod
    def _get_search_engine() -> object:
        """Create OpenGauss SQLAlchemy engine for vector search."""
        host = os.environ.get("DATACLOUD_DB_HOST", "10.10.168.200")
        port = os.environ.get("DATACLOUD_DB_PORT", "5432")
        user = os.environ.get("DATACLOUD_DB_USER", "gaussdb")
        password = os.environ.get("DATACLOUD_DB_PASS", "Admin@123")
        database = os.environ.get("DATACLOUD_DB_DATABASE", "postgres")

        url = f"opengauss+psycopg2://{user}:{quote_plus(password)}@{host}:{port}/{database}"
        return create_engine(url, echo=False)

    @staticmethod
    def _resolve_object_code(conn: object, term_code: str, term_type: str) -> str:
        """Resolve a term to its parent object_code.

        For 'prop' type: look up HAS_FIELD or parent_term_id.
        For 'object' type: return self.
        """
        if term_type == "object":
            return term_code

        # Try HAS_FIELD relation first (prop -> object)
        rows = conn.execute(
            text(
                """SELECT t_obj.term_code
                   FROM byai.term_relation tr
                   JOIN byai.term t_prop ON t_prop.term_id = tr.target_term_id
                   JOIN byai.term t_obj ON t_obj.term_id = tr.source_term_id
                   WHERE t_prop.term_code = :code
                     AND tr.relation_category = 'HAS_FIELD'
                     AND t_obj.term_type_code = 'object'
                   LIMIT 1"""
            ),
            {"code": term_code},
        ).fetchall()

        if rows:
            return rows[0][0]  # type: ignore[no-any-return]

        # Fallback: parent_term_id
        rows = conn.execute(
            text(
                """SELECT t_parent.term_code
                   FROM byai.term t
                   JOIN byai.term t_parent ON t_parent.term_id = t.parent_term_id
                   WHERE t.term_code = :code
                     AND t_parent.term_type_code = 'object'
                   LIMIT 1"""
            ),
            {"code": term_code},
        ).fetchall()

        return rows[0][0] if rows else ""

    @staticmethod
    def _resolve_value_to_property(conn: object, value_term_id: str) -> dict:
        """Resolve a value term to its owning property and object.

        Chain: value_term ->(parent_term_id)-> type_root <-(HAS_TERM)- prop
        """
        rows = conn.execute(
            text(
                """SELECT t_prop.term_code AS property_code,
                          t_obj.term_code AS object_code
                   FROM byai.term t_val
                   JOIN byai.term t_root ON t_root.term_id = t_val.parent_term_id
                   JOIN byai.term_relation tr
                     ON tr.target_term_id = t_root.term_id
                     AND tr.relation_category = 'HAS_TERM'
                   JOIN byai.term t_prop
                     ON t_prop.term_id = tr.source_term_id
                     AND t_prop.term_type_code = 'prop'
                   JOIN byai.term t_obj
                     ON t_obj.term_id = t_prop.parent_term_id
                     AND t_obj.term_type_code = 'object'
                   WHERE t_val.term_id = :tid
                   LIMIT 1"""
            ),
            {"tid": value_term_id},
        ).fetchall()

        if rows:
            return {"propertyCode": rows[0][0], "objectCode": rows[0][1]}
        return {"propertyCode": "", "objectCode": ""}

    # -- search ontology helpers --

    @staticmethod
    def _term_type_to_matched_field(term_type: str) -> str:
        """Map term_type_code to the actual field name that was matched."""
        return {
            "object": "objectName",
            "view": "viewName",
            "action": "actionName",
            "prop": "propertyName",
            "func": "functionName",
        }.get(term_type, "name")

    def _build_metadata_hit(
        self,
        conn: object,
        scene_id: str,
        term_code: str,
        term_type: str,
        term_name: str,
        desc_summary: str,
        matched_value: str,
        score: float,
        loader: object | None,
    ) -> dict:
        """Build a metadata hit dict with per-resultType fields.

        resultType=object: sceneId, objectCode, objectName, objectDesc, objectSource,
                           matchedField, matchedValue, score
        resultType=view:   sceneId, viewCode, viewName, description, matchedField,
                           matchedValue, score
        resultType=action: sceneId, actionCode, actionName, actionDesc, belongObjectCode,
                           matchedField, matchedValue, score
        resultType=prop/func: sceneId, propertyCode, propertyName, belongObjectCode,
                              matchedField, matchedValue, score
        """
        matched_field = self._term_type_to_matched_field(term_type)
        base: dict = {
            "sceneId": scene_id,
            "resultType": term_type,
            "matchedField": matched_field,
            "matchedValue": matched_value,
            "score": score,
        }

        if term_type == "object":
            object_desc = desc_summary
            object_source = ""
            if loader is not None:
                with suppress(Exception):
                    ont = loader._objects.get(term_code)  # type: ignore[union-attr]
                    if ont is not None:
                        object_desc = ont.description or desc_summary
                        object_source = ont.source_type or ""
            return {
                **base,
                "objectCode": term_code,
                "objectName": term_name,
                "objectDesc": object_desc,
                "objectSource": object_source,
            }

        if term_type == "view":
            view_desc = ""
            if loader is not None:
                with suppress(Exception):
                    view = loader._views.get(term_code)  # type: ignore[union-attr]
                    if view is not None:
                        view_desc = view.description or ""
            return {
                **base,
                "viewCode": term_code,
                "viewName": term_name,
                "description": view_desc,
            }

        if term_type == "action":
            belong_obj = self._resolve_object_code(conn, term_code, term_type)
            return {
                **base,
                "actionCode": term_code,
                "actionName": term_name,
                "actionDesc": desc_summary,
                "belongObjectCode": belong_obj,
            }

        if term_type in ("prop", "func"):
            belong_obj = self._resolve_object_code(conn, term_code, term_type)
            return {
                **base,
                "propertyCode": term_code,
                "propertyName": term_name,
                "belongObjectCode": belong_obj,
            }

        # Fallback for unknown types
        return {
            **base,
            "objectCode": self._resolve_object_code(conn, term_code, term_type),
            "objectName": term_name,
        }

    @staticmethod
    def _get_term_name(conn: object, term_code: str, term_type_code: str) -> str:
        """Get term_name for a term_code + type_code from the DB."""
        rows = conn.execute(
            text(
                """SELECT term_name FROM byai.term
                   WHERE term_code = :code AND term_type_code = :type
                   LIMIT 1"""
            ),
            {"code": term_code, "type": term_type_code},
        ).fetchall()
        return str(rows[0][0]) if rows else ""

    @staticmethod
    def _check_is_enum_type(conn: object, type_code: str) -> bool:
        """Check if a type_code also exists as an object type (is an enum)."""
        rows = conn.execute(
            text(
                """SELECT 1 FROM byai.term
                   WHERE term_code = :code AND term_type_code = 'object'
                   LIMIT 1"""
            ),
            {"code": type_code},
        ).fetchall()
        return bool(rows)

    @staticmethod
    def _resolve_referenced_by_properties(conn: object, value_term_id: int) -> list[dict]:
        """Find properties referencing this enum value type via HAS_TERM relation.

        Chain: value term → parent_term_id → type_root
               type_root ← term_relation.HAS_TERM(target_term_id) ← prop term
               prop term → parent_term_id → object term
        """
        rows = conn.execute(
            text(
                """SELECT t_obj.term_code AS object_code,
                          t_obj.term_name AS object_name,
                          t_prop.term_code AS property_code,
                          t_prop.term_name AS property_name
                   FROM byai.term t_val
                   JOIN byai.term t_root ON t_root.term_id = t_val.parent_term_id
                   JOIN byai.term_relation tr
                     ON tr.target_term_id = t_root.term_id
                     AND tr.relation_category = 'HAS_TERM'
                   JOIN byai.term t_prop
                     ON t_prop.term_id = tr.source_term_id
                     AND t_prop.term_type_code = 'prop'
                   JOIN byai.term t_obj
                     ON t_obj.term_id = t_prop.parent_term_id
                     AND t_obj.term_type_code = 'object'
                   WHERE t_val.term_id = :tid"""
            ),
            {"tid": value_term_id},
        ).fetchall()

        return [
            {
                "objectCode": row[0],
                "objectName": row[1],
                "propertyCode": row[2],
                "propertyName": row[3],
            }
            for row in rows
        ]

    @staticmethod
    def _extract_object_codes(scene: dict) -> list[str]:
        raw_objects = scene.get("objects", [])
        if raw_objects and isinstance(raw_objects[0], str):
            return raw_objects
        if raw_objects:
            return [item["object_code"] for item in raw_objects]
        return scene.get("object_ids", [])

    @staticmethod
    def _ontology_class_to_summary(ont_class: object) -> dict:
        """Convert OntologyClass to ObjectTypeSummary dict (fieldCount + actionCount)."""
        return {
            "objectCode": ont_class.object_code,
            "objectName": ont_class.object_name,
            "objectSource": ont_class.source_type,
            "objectDesc": ont_class.description,
            "conceptType": getattr(ont_class, "concept_type", None),
            "fieldCount": len(ont_class.fields),
            "actionCount": len(ont_class.actions),
        }

    @staticmethod
    def _ontology_class_to_detail(ont_class: object) -> dict:
        """Convert OntologyClass to full ObjectType dict with properties[].terminology, actions[].params[]."""
        return {
            "objectCode": ont_class.object_code,
            "objectName": ont_class.object_name,
            "objectDesc": ont_class.description,
            "objectSource": ont_class.source_type,
            "conceptType": getattr(ont_class, "concept_type", None),
            "objectType": getattr(ont_class, "object_type", None),
            "domainType": getattr(ont_class, "domain_type", None),
            "tableName": ont_class.table_name,
            "sourceConfig": getattr(ont_class, "source_config", None),
            "properties": [
                {
                    "propertyCode": f.field_code,
                    "propertyName": f.field_name,
                    "dataType": f.field_type,
                    "isRequired": 1 if f.required else 0,
                    "isName": 1 if f.is_primary_key else 0,
                    "propertyDesc": f.description,
                    "sourceColumn": getattr(f, "source_column", None),
                    "dataFormat": getattr(f, "data_format", None),
                    "terminology": None,
                }
                for f in ont_class.fields
            ],
            "actions": [
                {
                    "actionCode": a.action_code,
                    "actionName": a.action_name,
                    "actionType": getattr(a, "action_type", None),
                    "belongObjectCode": ont_class.object_code,
                    "actionDesc": a.description,
                    "params": [
                        {
                            "paramCode": getattr(p, "param_code", ""),
                            "paramName": getattr(p, "param_name", None),
                            "paramType": getattr(p, "param_type", None),
                            "isRequired": getattr(p, "is_required", 0),
                            "direction": getattr(p, "direction", None),
                            "mappingPath": getattr(p, "mapping_path", None),
                        }
                        for p in (getattr(a, "params", []) or [])
                    ],
                    "requestUrl": getattr(a, "request_url", None),
                    "requestMethod": getattr(a, "request_method", None),
                    "script": getattr(a, "script", None),
                }
                for a in ont_class.actions
            ],
        }

    @staticmethod
    def _json_obj_to_summary(data: dict) -> dict:
        """Convert JSON-stored object dict to summary format."""
        props = data.get("properties", data.get("fields", []))
        actions = data.get("actions", [])
        return {
            "objectCode": data.get("objectCode", data.get("object_code", "")),
            "objectName": data.get("objectName", data.get("object_name", "")),
            "objectSource": data.get("objectSource", data.get("object_source")),
            "objectDesc": data.get("objectDesc", data.get("object_desc")),
            "conceptType": data.get("conceptType", data.get("concept_type")),
            "fieldCount": len(props),
            "actionCount": len(actions),
        }

    @staticmethod
    def _json_obj_to_detail(data: dict) -> dict:
        """Normalize JSON-stored object dict to full detail format (properties + actions)."""
        props = data.get("properties", data.get("fields", []))
        actions = data.get("actions", [])
        normalized_props = [
            {
                "propertyCode": p.get("propertyCode", p.get("fieldCode", p.get("field_code", ""))),
                "propertyName": p.get("propertyName", p.get("fieldName", p.get("field_name", ""))),
                "dataType": p.get("dataType", p.get("fieldType", p.get("field_type", "STRING"))),
                "isRequired": p.get("isRequired", p.get("is_required", 0)),
                "isName": p.get("isName", p.get("isPrimaryKey", p.get("is_primary_key", 0))),
                "propertyDesc": p.get("propertyDesc", p.get("description", "")),
                "sourceColumn": p.get("sourceColumn", p.get("source_column")),
                "dataFormat": p.get("dataFormat", p.get("data_format")),
                "terminology": p.get("terminology"),
                "isInstantiation": p.get("isInstantiation", p.get("is_instantiation", 0)),
                "businessDefinition": p.get("businessDefinition", p.get("business_definition")),
                "technicalDefinition": p.get("technicalDefinition", p.get("technical_definition")),
                "synonyms": p.get("synonyms"),
                "propertyType": p.get("propertyType", p.get("property_type")),
                "propertyTypeCode": p.get("propertyTypeCode", p.get("property_type_code")),
                "propertySubType": p.get("propertySubType", p.get("property_sub_type")),
                "propertySubTypeCode": p.get(
                    "propertySubTypeCode", p.get("property_sub_type_code")
                ),
                "businessKey": p.get("businessKey", p.get("business_key", 0)),
                "sortNo": p.get("sortNo", p.get("sort_no", 0)),
                "status": p.get("status", 0),
                "dbId": p.get("dbId", p.get("db_id")),
                "columnId": p.get("columnId", p.get("column_id")),
                "apiId": p.get("apiId", p.get("api_id")),
                "apiSource": p.get("apiSource", p.get("api_source")),
                "docId": p.get("docId", p.get("doc_id")),
            }
            for p in props
        ]
        normalized_actions = []
        for a in actions:
            action_params = a.get("params", [])
            normalized_params = [
                {
                    "paramCode": ap.get("paramCode", ap.get("param_code", "")),
                    "paramName": ap.get("paramName", ap.get("param_name")),
                    "paramType": ap.get("paramType", ap.get("param_type")),
                    "isRequired": ap.get("isRequired", ap.get("is_required", 0)),
                    "direction": ap.get("direction"),
                    "mappingPath": ap.get("mappingPath", ap.get("mapping_path")),
                }
                for ap in action_params
            ]
            normalized_actions.append(
                {
                    "actionCode": a.get("actionCode", a.get("action_code", "")),
                    "actionName": a.get("actionName", a.get("action_name", "")),
                    "actionType": a.get("actionType", a.get("action_type")),
                    "belongObjectCode": a.get("belongObjectCode", a.get("belong_object_code", "")),
                    "actionDesc": a.get("actionDesc", a.get("action_desc")),
                    "params": normalized_params,
                    "requestUrl": a.get("requestUrl", a.get("request_url")),
                    "requestMethod": a.get("requestMethod", a.get("request_method")),
                    "script": a.get("script"),
                }
            )
        return {
            "objectCode": data.get("objectCode", data.get("object_code", "")),
            "objectName": data.get("objectName", data.get("object_name", "")),
            "objectDesc": data.get("objectDesc", data.get("object_desc")),
            "objectSource": data.get("objectSource", data.get("object_source")),
            "conceptType": data.get("conceptType", data.get("concept_type")),
            "objectType": data.get("objectType", data.get("object_type")),
            "domainType": data.get("domainType", data.get("domain_type")),
            "sceneId": data.get("sceneId", data.get("scene_id")),
            "sourceConfig": data.get("sourceConfig", data.get("source_config")),
            "tableName": data.get("tableName", data.get("table_name")),
            "properties": normalized_props,
            "actions": normalized_actions,
        }

    @staticmethod
    def _validate_object(obj: ObjectType) -> None:
        if not obj.object_code:
            raise ValueError("objectCode is required")
        if not obj.object_name:
            raise ValueError("objectName is required")

    @staticmethod
    def _parser_obj_to_writer(obj: dict) -> dict:
        """Convert OwlParser._build_content object dict (snake_case) to writer format (camelCase)."""
        fields = [
            {
                "propertyCode": f.get("field_code", ""),
                "propertyName": f.get("field_name", ""),
                "dataType": f.get("field_type", "STRING"),
                "isPrimaryKey": f.get("is_primary_key", False),
                "required": f.get("required", False),
                "description": f.get("description", ""),
                "sourceColumn": f.get("source_column"),
                "dataFormat": f.get("data_format"),
            }
            for f in obj.get("fields", [])
        ]
        return {
            "objectCode": obj.get("object_code", ""),
            "objectName": obj.get("object_name", ""),
            "description": obj.get("description", ""),
            "sourceType": obj.get("source_type", ""),
            "tableName": obj.get("table_name"),
            "datasourceAlias": obj.get("datasource_alias"),
            "sourceConfig": obj.get("source_config"),
            "tags": obj.get("tags", []),
            "properties": fields,
            "actions": obj.get("actions", []),
        }
