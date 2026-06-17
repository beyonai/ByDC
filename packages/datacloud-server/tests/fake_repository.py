"""FakeOntologyRepository - in-memory ontology store for service layer unit tests.

Uses duck typing; no need to explicitly inherit from Protocol.
"""
# ruff: noqa: ARG002  # stub parameters must match Protocol signature

from __future__ import annotations


class FakeOntologyRepository:
    """In-memory ontology repository for testing."""

    def __init__(self) -> None:
        self._scenes: dict[str, list[dict]] = {}
        self._objects: dict[str, dict] = {}
        self._views: dict[str, dict] = {}
        self._relations: dict[str, list[dict]] = {}
        self._datasources: dict[str, dict] = {}
        self._actions: dict[str, dict] = {}

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

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict]:
        scenes = self._scenes.get(base_id, [])
        if not keyword:
            return scenes
        kw = keyword.strip().lower()
        return [s for s in scenes if kw in s.get("sceneName", "").lower() or kw in s.get("sceneCode", "").lower()]

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
        """Return full scene dump (simplified for tests)."""
        return {
            "scene": self.get_scene(base_id, scene_id),
            "views": self.get_views(base_id, scene_id),
            "objects": self.get_objects(base_id, scene_id),
            "actions": [],
            "relations": self.get_relations(base_id, scene_id),
            "dbsources": self.get_datasources(base_id, scene_id),
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
        return {"data": [], "totalCount": 0}

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

    def get_relation_detail(self, base_id: str, scene_id: str, rel_code: str) -> dict | None:
        relations = self._relations.get(self._key(base_id, scene_id), [])
        for r in relations:
            if r.get("relationCode") == rel_code:
                return r
        return None

    def create_relation(self, base_id: str, scene_id: str, rel_data: dict) -> dict:
        key = self._key(base_id, scene_id)
        if key not in self._relations:
            self._relations[key] = []
        for r in self._relations[key]:
            if r.get("relationCode") == rel_data.get("relationCode"):
                raise ValueError(f"Relation '{rel_data['relationCode']}' already exists")
        self._relations[key].append(rel_data)
        return rel_data

    def update_relation(self, base_id: str, scene_id: str, rel_code: str, rel_data: dict) -> dict:
        key = self._key(base_id, scene_id)
        if key not in self._relations:
            raise KeyError(f"Relation '{rel_code}' not found")
        for i, r in enumerate(self._relations[key]):
            if r.get("relationCode") == rel_code:
                self._relations[key][i] = rel_data
                return rel_data
        raise KeyError(f"Relation '{rel_code}' not found")

    def delete_relation(self, base_id: str, scene_id: str, rel_code: str) -> None:
        key = self._key(base_id, scene_id)
        if key in self._relations:
            self._relations[key] = [
                r for r in self._relations[key] if r.get("relationCode") != rel_code
            ]

    # -- datasource read --

    def get_datasources(self, base_id: str, scene_id: str) -> list[dict]:
        prefix = self._key(base_id, scene_id)
        return [v for k, v in self._datasources.items() if k.startswith(prefix)]

    def get_datasource_detail(self, base_id: str, scene_id: str, db_id: str) -> dict | None:
        return self._datasources.get(self._key(base_id, scene_id, db_id))

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

    def update_view(self, base_id: str, scene_id: str, view_code: str, view_data: dict) -> dict:
        key = self._key(base_id, scene_id, view_code)
        if key not in self._views:
            raise KeyError(f"View '{view_code}' not found")
        self._views[key] = view_data
        return view_data

    def get_view_detail(self, base_id: str, scene_id: str, view_code: str) -> dict | None:
        return self._views.get(self._key(base_id, scene_id, view_code))

    def delete_view(self, base_id: str, scene_id: str, view_code: str) -> None:
        key = self._key(base_id, scene_id, view_code)
        if key in self._views:
            del self._views[key]

    def create_datasource(self, base_id: str, scene_id: str, ds_data: dict) -> dict:
        db_id = ds_data.get("dbId", ds_data.get("db_id", ""))
        key = self._key(base_id, scene_id, db_id)
        if key in self._datasources:
            raise ValueError(f"Datasource '{db_id}' already exists")
        self._datasources[key] = ds_data
        return ds_data

    def delete_datasource(self, base_id: str, scene_id: str, db_id: str) -> None:
        key = self._key(base_id, scene_id, db_id)
        if key in self._datasources:
            del self._datasources[key]

    # -- action --

    def get_actions(self, base_id: str, scene_id: str, object_code: str) -> list[dict]:
        prefix = self._key(base_id, scene_id) + f":{object_code}"
        return [v for k, v in self._actions.items() if k.startswith(prefix)]

    def get_action_detail(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> dict | None:
        return self._actions.get(self._key(base_id, scene_id) + f":{object_code}:{action_code}")

    def create_action(
        self, base_id: str, scene_id: str, object_code: str, action_data: dict
    ) -> dict:
        action_code = action_data.get("actionCode", action_data.get("action_code", ""))
        key = self._key(base_id, scene_id) + f":{object_code}:{action_code}"
        if key in self._actions:
            raise ValueError(f"Action '{action_code}' already exists")
        self._actions[key] = action_data
        return action_data

    def update_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str, action_data: dict
    ) -> dict:
        key = self._key(base_id, scene_id) + f":{object_code}:{action_code}"
        if key not in self._actions:
            raise KeyError(f"Action '{action_code}' not found")
        self._actions[key] = action_data
        return action_data

    def delete_action(
        self, base_id: str, scene_id: str, object_code: str, action_code: str
    ) -> None:
        key = self._key(base_id, scene_id) + f":{object_code}:{action_code}"
        if key in self._actions:
            del self._actions[key]

    # -- application services (stubs) --

    def search_instances(self, base_id: str, query: dict) -> dict:
        return {"data": [], "totalCount": 0}

    def search_ontology(
        self, base_id: str, scene_id: str, *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        property_code: list[str] | None = None,
        result_per_type: int = 5,
        page_size: int = 20,
        page_token: str | None = None,
    ) -> dict:
        return {"metadata": [], "instances": [], "totalCount": {"metadata": 0, "instances": 0}}

    def graph_query(self, base_id: str, scene_id: str, query: dict) -> dict:
        return {"nodes": [], "edges": []}

    def graph_path(self, base_id: str, scene_id: str, query: dict) -> dict:
        return {"path": [], "edges": [], "hops": -1}

    def import_owl(self, base_id: str, scene_id: str, zip_bytes: bytes) -> dict:
        return {"objects": 0, "views": 0, "relations": 0}
