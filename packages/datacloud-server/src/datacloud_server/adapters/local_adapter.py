# ruff: noqa: PLC0415
"""Local ontology adapter - reads OWL/JSON via datacloud-data SDK, writes via JSONWriter.

Uses lazy imports for optional deps (sqlalchemy, requests) needed only for vector search.
"""

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

    def search_ontology(
        self, _base_id: str, _scene_id: str, request: dict
    ) -> dict:
        """Vector search across metadata and instance terms.

        Uses embedding model to encode keyword, then pgvector cosine distance.

        Returns:
            {"metadata": [...], "instances": [...], "totalCount": {...}}
        """
        keyword = request.get("keyword", "")
        search_scope = request.get("searchScope", "all")

        if not keyword:
            return {"metadata": [], "instances": [], "totalCount": {"metadata": 0, "instances": 0}}

        vec_str = self._embed_and_encode(keyword)
        engine = self._get_search_engine()

        result: dict = {
            "metadata": [],
            "instances": [],
            "totalCount": {"metadata": 0, "instances": 0},
        }

        with engine.connect() as conn:
            from sqlalchemy import text

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
                    {
                        "matchedField": row[1],  # term_code
                        "objectCode": self._resolve_object_code(conn, row[1], row[2]),
                        "objectName": row[3],  # term_name
                        "matchedValue": row[0],  # name_text
                        "resultType": row[2],  # term_type_code
                        "score": round(float(row[5]), 4),
                    }
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
                    score = round(float(row[5]), 4)

                    # Resolve: value term -> property -> object
                    prop_info = self._resolve_value_to_property(conn, row[4])
                    instance_items.append(
                        {
                            "objectCode": prop_info.get("objectCode", ""),
                            "matchedProperty": prop_info.get("propertyCode", value_type),
                            "matchedValue": value_name,
                            "primaryKey": value_code,
                            "score": score,
                        }
                    )
                result["instances"] = instance_items
                result["totalCount"]["instances"] = len(result["instances"])

        return result

    def graph_query(self, _base_id: str, _scene_id: str, _query: dict) -> dict:
        return {"nodes": [], "edges": []}

    # -- helpers --

    @staticmethod
    def _embed_and_encode(keyword: str) -> str:
        """Embed keyword via DashScope and return pgvector string."""
        import os

        import requests

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
        import os
        from urllib.parse import quote_plus

        from sqlalchemy import create_engine

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

        from sqlalchemy import text

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

        return rows[0][0] if rows else ""  # type: ignore[no-any-return]

    @staticmethod
    def _resolve_value_to_property(conn: object, value_term_id: str) -> dict:
        """Resolve a value term to its owning property and object.

        Chain: value_term ->(parent_term_id)-> type_root <-(HAS_TERM)- prop
        """
        from sqlalchemy import text

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
            return {"propertyCode": rows[0][0], "objectCode": rows[0][1]}  # type: ignore[no-any-return]
        return {"propertyCode": "", "objectCode": ""}

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
