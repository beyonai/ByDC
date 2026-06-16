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


def _add_nodes_and_edges(
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
            "relationType": rel.relation_type,
        }
        adj.setdefault(s, []).append(edge_data)
        adj.setdefault(t, []).append(
            {
                "source": t,
                "target": s,
                "relationCode": rel.relation_code,
                "relationType": rel.relation_type,
            }
        )

    # Determine seed object codes
    seed_codes: set[str]
    if object_codes:
        seed_codes = set(object_codes)
    else:
        seed_codes = set(loader._classes.keys())

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
            }

        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "views" / f"{view_code}.json"
        if file_path.exists():
            return _json.loads(file_path.read_text(encoding="utf-8"))

        return None

    def get_relations(self, base_id: str, scene_id: str) -> list[dict]:
        loader = self._get_loader(base_id)
        seen_codes: set[str] = set()
        relations: list[dict] = []

        for r in loader._relations:
            rel = {
                "relationCode": r.relation_code or "",
                "relationName": getattr(r, "relation_name", ""),
                "sourceClass": r.source_class,
                "targetClass": r.target_class,
                "relationType": r.relation_type,
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
                    relations.append(rel)
                    seen_codes.add(code)

        return relations

    def get_relation_detail(self, base_id: str, scene_id: str, rel_code: str) -> dict | None:
        relations = self.get_relations(base_id, scene_id)
        for r in relations:
            if r.get("relationCode") == rel_code:
                return r
        return None

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

    def create_view(self, base_id: str, scene_id: str, view_data: dict) -> dict:
        scene_path = self._scene_path(base_id, scene_id)
        view_code = view_data.get("viewCode", view_data.get("view_id", ""))
        file_path = scene_path / "views" / f"{view_code}.json"
        if file_path.exists():
            raise ValueError(f"View '{view_code}' already exists")
        self.writer.write_view(scene_path, view_data)
        self._reload_loader(base_id)
        return view_data

    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None:
        self.writer.delete_view(self._scene_path(base_id, scene_id), view_code)
        self._reload_loader(base_id)

    def create_relation(self, base_id: str, scene_id: str, rel_data: dict) -> dict:
        scene_path = self._scene_path(base_id, scene_id)
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
        return rel_data

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
        result: list[dict] = []
        for json_file in sorted(ds_dir.glob("*.json")):
            result.append(_json.loads(json_file.read_text(encoding="utf-8")))
        return result

    def get_datasource_detail(self, base_id: str, scene_id: str, db_id: str) -> dict | None:
        scene_path = self._scene_path(base_id, scene_id)
        file_path = scene_path / "datasources" / f"{db_id}.json"
        if file_path.exists():
            return _json.loads(file_path.read_text(encoding="utf-8"))
        return None

    def create_datasource(self, base_id: str, scene_id: str, ds_data: dict) -> dict:
        scene_path = self._scene_path(base_id, scene_id)
        db_id = ds_data.get("dbId", ds_data.get("db_id", ""))
        ds_dir = scene_path / "datasources"
        self.writer.ensure_dir(ds_dir)
        file_path = ds_dir / f"{db_id}.json"
        if file_path.exists():
            raise ValueError(f"Datasource '{db_id}' already exists")
        self.writer._atomic_write(file_path, ds_data)  # noqa: SLF001
        return ds_data

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
        self, base_id: str, scene_id: str, object_code: str, action_data: dict
    ) -> dict:
        """Create an action on an object."""
        scene_path = self._scene_path(base_id, scene_id)
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
        self.writer._atomic_write(file_path, obj)  # noqa: SLF001
        self._reload_loader(base_id)
        return action_data

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
        self.writer._atomic_write(file_path, obj)  # noqa: SLF001
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
        import io as _io
        import tempfile as _tempfile
        import zipfile as _zipfile

        from datacloud_data_sdk.ontology.owl_parser import OwlParser

        tmp_path = Path(_tempfile.mkdtemp(prefix="owl_import_"))
        try:
            with _zipfile.ZipFile(_io.BytesIO(zip_bytes)) as zf:
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
            import shutil as _shutil

            _shutil.rmtree(tmp_path, ignore_errors=True)

    # -- application services --

    def search_instances(self, base_id: str, query: dict) -> dict:
        """Search ontology objects by keyword.

        Args:
            base_id: Ontology base identifier.
            query: {
                "keyword": str,
                "objectCode": str | None,   # optional: filter to single object
                "page": int,                 # default 1
                "pageSize": int,             # default 20
            }

        Returns:
            {"data": [object_dict, ...], "totalCount": N}
        """
        loader = self._get_loader(base_id)
        keyword = (query.get("keyword") or "").strip().lower()
        filter_code = query.get("objectCode")
        page = max(int(query.get("page", 1)), 1)
        page_size = max(int(query.get("pageSize", 20)), 1)

        if not keyword:
            classes = list(loader._classes.values())
            total = len(classes)
            start = (page - 1) * page_size
            data = [self._ontology_class_to_dict(c) for c in classes[start : start + page_size]]
            return {"data": data, "totalCount": total}

        matches: list[dict] = []
        for cls in loader._classes.values():
            if filter_code and cls.object_code != filter_code:
                continue
            if not self._class_matches_keyword(cls, keyword):
                continue
            matches.append(self._ontology_class_to_dict(cls))

        total = len(matches)
        start = (page - 1) * page_size
        data = matches[start : start + page_size]
        return {"data": data, "totalCount": total}

    @staticmethod
    def _class_matches_keyword(cls: object, keyword: str) -> bool:
        """Check if OntologyClass matches a keyword (case-insensitive)."""
        if keyword in cls.object_code.lower():
            return True
        if keyword in cls.object_name.lower():
            return True
        if keyword in cls.description.lower():
            return True
        for field in cls.fields:
            if keyword in field.field_code.lower():
                return True
            if keyword in field.field_name.lower():
                return True
        return False

    def search_ontology(self, _base_id: str, _scene_id: str, request: dict) -> dict:
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

    def graph_query(self, base_id: str, _scene_id: str, query: dict) -> dict:
        """Build a graph of objects and their relations.

        Args:
            base_id: Ontology base identifier.
            _scene_id: Scene identifier (unused in local adapter).
            query: {
                "objectCodes": list[str] | None,  # filter to these objects
                "depth": int | None,              # maximum hop depth (BFS expansion)
            }

        Returns:
            {"nodes": [{"code": str, "label": str, "description": str}, ...],
             "edges": [{"source": str, "target": str, "relationCode": str,
                        "relationType": str}, ...]}
        """
        loader = self._get_loader(base_id)
        object_codes: list[str] | None = query.get("objectCodes")
        depth: int | None = query.get("depth")

        nodes: dict[str, dict] = {}
        edges: list[dict] = []

        _add_nodes_and_edges(loader, object_codes, depth, nodes, edges)

        return {"nodes": list(nodes.values()), "edges": edges}

    def graph_path(self, base_id: str, _scene_id: str, query: dict) -> dict:
        """Find shortest path between two objects in the relation graph.

        Args:
            base_id: Ontology base identifier.
            _scene_id: Scene identifier (unused in local adapter).
            query: {
                "sourceObjectCode": str,
                "targetObjectCode": str,
            }

        Returns:
            {"path": [str, ...], "edges": [...], "hops": int}
            — hops == -1 when no path exists.
        """
        loader = self._get_loader(base_id)
        source = query.get("sourceObjectCode", "")
        target = query.get("targetObjectCode", "")

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
                "relationType": rel.relation_type,
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
        from collections import deque

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

    @staticmethod
    def _parser_obj_to_writer(obj: dict) -> dict:
        """Convert OwlParser._build_content object dict (snake_case) to writer format (camelCase)."""
        fields = [
            {
                "fieldCode": f.get("field_code", ""),
                "fieldName": f.get("field_name", ""),
                "fieldType": f.get("field_type", "STRING"),
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
            "fields": fields,
            "actions": obj.get("actions", []),
        }
