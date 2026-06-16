"""Local ontology adapter - reads OWL/JSON via datacloud-data SDK, writes via JSONWriter."""

from __future__ import annotations

import json as _json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_server.storage.json_writer import JSONWriter

from datacloud_data_sdk.ontology.loader import OntologyLoader

logger = logging.getLogger(__name__)


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

    # -- metadata: read --

    def list_scenes(self, base_id: str) -> list[dict]:
        base_path = self.data_dir / base_id
        if not base_path.exists():
            return []
        return [
            {"sceneId": item.name, "sceneName": item.name, "baseId": base_id}
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
            "description": "",
            "baseId": base_id,
        }

    def get_objects(self, base_id: str, scene_id: str) -> list[dict]:
        loader = self._get_loader(base_id)
        objects: list[dict] = []
        seen_codes: set[str] = set()

        for ont_class in loader._classes.values():
            objects.append(self._ontology_class_to_dict(ont_class))
            seen_codes.add(ont_class.object_code)

        scene_path = self._scene_path(base_id, scene_id)
        objects_dir = scene_path / "objects"
        if objects_dir.exists():
            for json_file in sorted(objects_dir.glob("*.json")):
                code = json_file.stem
                if code not in seen_codes:
                    data = _json.loads(json_file.read_text(encoding="utf-8"))
                    objects.append(data)
                    seen_codes.add(code)

        return objects

    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None:
        loader = self._get_loader(base_id)
        try:
            ont_class = loader.get_ontology_class(object_code)
            return self._ontology_class_to_dict(ont_class)
        except Exception:
            logger.debug("Object '%s' not found in loader, trying JSON", object_code)

        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "objects" / f"{object_code}.json"
        if file_path.exists():
            return _json.loads(file_path.read_text(encoding="utf-8"))

        logger.warning("Object '%s' not found", object_code)
        return None

    def get_views(self, base_id: str, _scene_id: str) -> list[dict]:
        loader = self._get_loader(base_id)
        return [
            {
                "viewCode": vid,
                "viewName": scene.get("view_name", vid),
                "description": scene.get("description", ""),
                "objectCodes": self._extract_object_codes(scene),
            }
            for vid, scene in loader._scenes.items()
        ]

    def get_relations(self, base_id: str, _scene_id: str) -> list[dict]:
        loader = self._get_loader(base_id)
        return [
            {
                "relationCode": r.relation_code or "",
                "relationName": getattr(r, "relation_name", ""),
                "sourceClass": r.source_class,
                "targetClass": r.target_class,
                "relationType": r.relation_type,
                "joinKeys": r.join_keys,
            }
            for r in loader._relations
        ]

    # -- metadata: write --

    def create_object(self, base_id: str, scene_id: str, obj_data: dict) -> dict:
        self._validate_object(obj_data)
        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "objects" / f"{obj_data['objectCode']}.json"
        if file_path.exists():
            raise ValueError(f"Object '{obj_data['objectCode']}' already exists")
        self.writer.write_object(scene_path, obj_data)
        self._reload_loader(base_id)
        return obj_data

    def update_object(self, base_id: str, scene_id: str, _object_code: str, obj_data: dict) -> dict:
        self._validate_object(obj_data)
        scene_path = self._scene_path(base_id, scene_id)
        self.writer.write_object(scene_path, obj_data)
        self._reload_loader(base_id)
        return obj_data

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        self.writer.delete_object(self._scene_path(base_id, scene_id), object_code)
        self._reload_loader(base_id)

    # -- application services (stubs) --

    def search_instances(self, _base_id: str, _query: dict) -> dict:
        return {"data": [], "totalCount": 0}

    def search_ontology(self, _base_id: str, _scene_id: str, _request: dict) -> dict:
        return {"metadata": [], "instances": [], "totalCount": {"metadata": 0, "instances": 0}}

    def graph_query(self, _base_id: str, _scene_id: str, _query: dict) -> dict:
        return {"nodes": [], "edges": []}

    # -- helpers --

    @staticmethod
    def _extract_object_codes(scene: dict) -> list[str]:
        raw_objects = scene.get("objects", [])
        if raw_objects and isinstance(raw_objects[0], str):
            return raw_objects
        if raw_objects:
            return [item["object_code"] for item in raw_objects]
        return scene.get("object_ids", [])

    @staticmethod
    def _ontology_class_to_dict(ont_class: object) -> dict:
        """Convert OntologyClass to API response dict."""
        return {
            "objectCode": ont_class.object_code,
            "objectName": ont_class.object_name,
            "description": ont_class.description,
            "sourceType": ont_class.source_type,
            "tableName": ont_class.table_name,
            "fields": [
                {
                    "fieldCode": f.field_code,
                    "fieldName": f.field_name,
                    "fieldType": f.field_type,
                    "isPrimaryKey": f.is_primary_key,
                    "required": f.required,
                    "description": f.description,
                }
                for f in ont_class.fields
            ],
            "actions": [
                {
                    "actionCode": a.action_code,
                    "actionName": a.action_name,
                    "description": a.description,
                }
                for a in ont_class.actions
            ],
        }

    @staticmethod
    def _validate_object(obj_data: dict) -> None:
        if "objectCode" not in obj_data:
            raise ValueError("objectCode is required")
        if "objectName" not in obj_data:
            raise ValueError("objectName is required")
