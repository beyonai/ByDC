"""FakeOntologyRepository - in-memory ontology store for service layer unit tests.

Uses duck typing; no need to explicitly inherit from Protocol.
"""

from __future__ import annotations


class FakeOntologyRepository:
    """In-memory ontology repository for testing."""

    def __init__(self) -> None:
        self._scenes: dict[str, list[dict]] = {}
        self._objects: dict[str, dict] = {}
        self._views: dict[str, dict] = {}
        self._relations: dict[str, list[dict]] = {}

    def _key(self, base_id: str, scene_id: str, code: str | None = None) -> str:
        k = f"{base_id}:{scene_id}"
        if code:
            k += f":{code}"
        return k

    # -- read --

    def list_scenes(self, base_id: str) -> list[dict]:
        return self._scenes.get(base_id, [])

    def get_scene(self, base_id: str, scene_id: str) -> dict | None:
        scenes = self._scenes.get(base_id, [])
        for s in scenes:
            if s.get("sceneId") == scene_id:
                return s
        return None

    def get_objects(self, base_id: str, scene_id: str) -> list[dict]:
        prefix = self._key(base_id, scene_id)
        return [obj for k, obj in self._objects.items() if k.startswith(prefix)]

    def get_object_detail(self, base_id: str, scene_id: str, object_code: str) -> dict | None:
        return self._objects.get(self._key(base_id, scene_id, object_code))

    def get_views(self, base_id: str, scene_id: str) -> list[dict]:
        prefix = self._key(base_id, scene_id)
        return [v for k, v in self._views.items() if k.startswith(prefix)]

    def get_relations(self, base_id: str, scene_id: str) -> list[dict]:
        return self._relations.get(self._key(base_id, scene_id), [])

    # -- write --

    def create_object(self, base_id: str, scene_id: str, obj_data: dict) -> dict:
        code = obj_data["objectCode"]
        key = self._key(base_id, scene_id, code)
        if key in self._objects:
            raise ValueError(f"Object '{code}' already exists")
        self._objects[key] = obj_data
        return obj_data

    def update_object(self, base_id: str, scene_id: str, object_code: str, obj_data: dict) -> dict:
        key = self._key(base_id, scene_id, object_code)
        if key not in self._objects:
            raise KeyError(f"Object '{object_code}' not found")
        self._objects[key] = obj_data
        return obj_data

    def delete_object(self, base_id: str, scene_id: str, object_code: str) -> None:
        key = self._key(base_id, scene_id, object_code)
        if key in self._objects:
            del self._objects[key]

    def create_view(self, base_id: str, scene_id: str, view_data: dict) -> dict:
        code = view_data.get("viewCode", view_data.get("view_id", ""))
        key = self._key(base_id, scene_id, code)
        if key in self._views:
            raise ValueError(f"View '{code}' already exists")
        self._views[key] = view_data
        return view_data

    # -- application services (stubs) --

    def search_instances(self, _base_id: str, _query: dict) -> dict:
        return {"data": [], "totalCount": 0}

    def search_ontology(self, _base_id: str, _scene_id: str, _request: dict) -> dict:
        return {"metadata": [], "instances": [], "totalCount": {"metadata": 0, "instances": 0}}

    def graph_query(self, _base_id: str, _scene_id: str, _query: dict) -> dict:
        return {"nodes": [], "edges": []}
