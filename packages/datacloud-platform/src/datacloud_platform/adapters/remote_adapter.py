"""Remote adapter — HTTP-forwarding backends for remote ontology & knowledge services.

Refactored from datacloud_server/adapters/remote_adapter.py into two separate
Platform Backend classes: RemoteOntologyBackend (OntologyBackend Protocol) and
RemoteKnowledgeBackend (KnowledgeBackend Protocol).
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any, cast

logger = logging.getLogger(__name__)


def _normalize_remote_detail(detail: dict[str, Any]) -> None:
    """Normalize DtStudio camelCase scene detail → loader snake_case in-place.

    DtStudio /OntologyEntityController/sceneDetails returns:
      objects[].objectCode / objectName / objectDesc / properties / actions
      actions at top-level detail.actions with belongObjectCode

    load_from_content expects:
      objects[].object_code / object_name / description / fields / actions
      actions[].action_code / action_name / description / params / ...

    Also merges top-level actions into per-object actions by belongObjectCode.
    """
    # # Merge top-level actions into objects
    # top_acts = detail.get("actions")
    # if isinstance(top_acts, list) and top_acts:
    #     by_obj: dict[str, list[dict[str, Any]]] = {}
    #     for a in top_acts:
    #         boc = str(a.get("belongObjectCode") or "")
    #         if boc:
    #             by_obj.setdefault(boc, []).append(a)
    #     for obj in detail.get("objects") or []:
    #         obj_code = str(obj.get("objectCode") or "")
    #         if obj_code in by_obj:
    #             obj_actions = list(obj.get("actions") or [])
    #             obj["actions"] = obj_actions + by_obj[obj_code]

    # Normalize each object
    for obj in detail.get("objects") or []:
        _normalize_remote_object(obj)

    # Normalize each view — DtStudio returns views in camelCase (viewId/viewName/objectCodes),
    # but load_from_content expects snake_case (view_id/view_name).  Without this, accessing
    # view["view_id"] raises KeyError and the entire load_from_content call fails.
    for v in detail.get("views") or []:
        _normalize_remote_view(v)


def _normalize_remote_object(obj: dict[str, Any]) -> None:
    """Normalize a single remote object entry (camelCase → snake_case) in-place."""
    # Top-level object fields
    obj.setdefault("object_code", obj.pop("objectCode", ""))
    obj.setdefault("object_name", obj.pop("objectName", ""))
    obj.setdefault("source_type", obj.pop("sourceType", "DB"))
    obj.setdefault("ext_property", obj.pop("extProperty", {}))
    desc = obj.pop("objectDesc", None)
    if desc:
        obj.setdefault("description", desc)
    # Properties → fields
    props = obj.pop("properties", None)
    if isinstance(props, list):
        fields = []
        for p in props:
            fields.append(
                {
                    "field_code": p.get("propertyCode", ""),
                    "field_name": p.get("propertyName", ""),
                    "field_type": p.get("propertyType", "STRING"),
                    "description": p.get("propertyDesc") or p.get("description", ""),
                    "is_primary_key": bool(p.get("isPrimaryKey", False)),
                }
            )
        obj["fields"] = fields
    # Actions
    for a in obj.get("actions") or []:
        a.setdefault("action_code", a.pop("actionCode", ""))
        a.setdefault("action_name", a.pop("actionName", ""))
        adesc = a.pop("actionDesc", None)
        if adesc:
            a.setdefault("description", adesc)
        a.setdefault("action_type", a.get("actionType", "query"))
        # Params
        raw_params = a.pop("params", None) or a.pop("parameters", None) or []
        if isinstance(raw_params, list):
            params = []
            for p in raw_params:
                params.append(
                    {
                        "param_code": p.get("paramCode", ""),
                        "param_name": p.get("paramName", ""),
                        "param_type": p.get("paramType", "STRING"),
                        "description": p.get("paramDesc") or p.get("description", ""),
                        "is_required": bool(p.get("isRequired", False)),
                    }
                )
            a["params"] = params
        # Other fields
        a.setdefault("script", a.get("script"))
        a.setdefault("function_refs", a.get("functionRefs") or [])
        a.setdefault("request_url", a.get("requestUrl"))
        a.setdefault("request_method", a.get("requestMethod"))


def _normalize_remote_view(v: dict[str, Any]) -> None:
    """Normalize a single remote view entry (camelCase → snake_case) in-place.

    DtStudio returns views with: viewId/viewCode / viewName / viewDesc / objectCodes / actions.
    load_from_content expects: view_id / view_name / description.
    """
    # DtStudio may use viewId (UUID) or viewCode (code string) as the identifier.
    # Prefer viewId as view_id; if absent, fall back to viewCode.
    vid = v.pop("viewId", "") or v.pop("viewCode", "")
    if vid:
        v.setdefault("view_id", vid)
    v.setdefault("view_code", v.pop("viewCode", ""))
    v.setdefault("view_name", v.pop("viewName", ""))
    vdesc = v.pop("viewDesc", None)
    if vdesc:
        v.setdefault("description", vdesc)
    # Normalize objects list inside view (may contain objectCode refs)
    raw_objects = v.get("objects")
    if isinstance(raw_objects, list):
        for item in raw_objects:
            if isinstance(item, dict):
                item.setdefault("object_code", item.pop("objectCode", ""))
                item.setdefault("object_name", item.pop("objectName", ""))
    # Normalize actions inside view
    for a in v.get("actions") or []:
        a.setdefault("action_code", a.pop("actionCode", ""))
        a.setdefault("action_name", a.pop("actionName", ""))
        adesc = a.pop("actionDesc", None)
        if adesc:
            a.setdefault("description", adesc)
        a.setdefault("action_type", a.get("actionType", "query"))


def _normalize_remote_search_result(result: dict[str, Any]) -> None:
    """Normalize remote /search/ontology response fields to local expectations.

    Remote API returns: resultType, objectCode/actionCode, objectName/actionName.
    Local consumers expect: termType, termCode, nameText, belongObjectCode.

    For action items (resultType="action"), DtStudio returns:
      - objectCode = parent object code (the belongObjectCode)
      - actionCode = the action's own code (the termCode)
      - actionName = human-readable action name (the nameText)
    """
    for item in result.get("metadata", []) or []:
        if not isinstance(item, dict):
            continue
        rt = str(item.get("resultType", ""))
        if rt == "action":
            # Action mapping: consumer reads termType="ontology_action"
            item["termType"] = "ontology_action"
            item["termCode"] = item.get("actionCode", "")
            item["nameText"] = item.get("actionName", "")
            parent_obj = item.get("objectCode", "")
            if parent_obj:
                item["belongObjectCode"] = parent_obj
        elif rt in ("object", "view", "skill"):
            item["termType"] = rt
            tc = item.get("objectCode", "")
            if tc:
                item["termCode"] = tc
            nt = item.get("objectName", "")
            if nt:
                item["nameText"] = nt


class RemoteOntologyBackend:
    """OntologyBackend that forwards read operations to a remote HTTP service.

    Write operations always raise ``PermissionError``.
    """

    def __init__(
        self,
        source_url: str,
        auth_config: dict[str, Any] | None = None,
    ) -> None:
        self._source_url = source_url.rstrip("/")
        self._auth_config = auth_config
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy httpx client creation."""
        if self._client is None:
            import httpx  # noqa: PLC0415

            self._client = httpx.Client(timeout=httpx.Timeout(30.0))
        return self._client

    def _build_auth_headers(self) -> dict[str, str]:
        """Build authentication headers from auth_config."""
        if not self._auth_config:
            return {}
        # Direct headers passthrough (for custom auth like ssoType/accountCode)
        headers_dict = self._auth_config.get("headers")
        if isinstance(headers_dict, dict):
            return {str(k): str(v) for k, v in headers_dict.items()}
        auth_type = self._auth_config.get("type", "").lower()
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {self._auth_config.get('token', '')}"}
        if auth_type == "api_key":
            header_name = self._auth_config.get("headerName", "X-API-Key")
            return {header_name: self._auth_config.get("apiKey", "")}
        return {}

    def configure(
        self, source_url: str, auth_config: dict[str, Any] | None = None
    ) -> None:
        """Dynamically set source_url and auth_config after construction.

        Used by Platform to inject per-base configuration into backends created
        by zero-arg factories (which don't know about the base at factory time).
        """
        if source_url:
            self._source_url = source_url.rstrip("/")
        if auth_config is not None:
            self._auth_config = auth_config
        self._client = None  # Reset client to pick up new config

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            with suppress(Exception):
                self._client.close()
            self._client = None

    # ── OntologyBackend Protocol ────────────────────────────────────────

    def parse_owl(self, directory: Any) -> Any:
        """Remote ontology is read-only — OWL parsing is not supported."""
        from datacloud_platform.models.shared import ParsedOwlContent

        return ParsedOwlContent(objects=[], views=[], relations=[])

    def load_ontology(self, base_path: Any) -> Any:
        """Remote ontology is read-only — loading is not supported."""
        raise PermissionError("Remote ontology base is read-only")

    def load_terms(self, loader: Any, *, library_id: str = "PERSONAL_LIB") -> Any:
        """Remote ontology is read-only — term loading is not supported."""
        return None

    def create_table(self, object_code: str, fields: list[dict[str, Any]]) -> None:
        """Remote ontology is read-only — DDL is not supported."""
        raise PermissionError("Remote ontology base is read-only")

    def drop_table(self, object_code: str) -> None:
        """Remote ontology is read-only — DDL is not supported."""
        raise PermissionError("Remote ontology base is read-only")

    def get_objects(self, loader: Any, base_id: str) -> list[Any]:
        """Fetch objects from remote endpoint (no local cache — Platform handles caching)."""
        _ = loader
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listObjects"
        response = client.post(url, json={"baseId": base_id}, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return cast("list[Any]", result.get("data", {}).get("objects", []))

    def get_object_detail(self, loader: Any, object_code: str) -> Any | None:
        """Remote ontology does not support per-object detail."""
        return None

    # -- View CRUD (remote, read-only) --

    def get_views(self, loader: Any, base_id: str) -> list[Any]:
        """Fetch views from remote endpoint (no local cache — Platform handles caching)."""
        _ = loader
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listViews"
        response = client.post(url, json={"baseId": base_id}, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return cast("list[Any]", result.get("data", {}).get("views", []))

    def get_view_detail(self, loader: Any, base_id: str, view_code: str) -> Any | None:
        """Look up view detail from cached views."""
        _ = loader
        for v in self.get_views(loader, base_id):
            if v.get("viewCode") == view_code:
                return v
        return None

    def create_view(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_view(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_view(self, base_id: str, object_code: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Relation CRUD (remote, read-only) --

    def get_relations(self, loader: Any, base_id: str) -> list[Any]:
        """Fetch relations from remote endpoint (no local cache — Platform handles caching)."""
        _ = loader
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listRelations"
        response = client.post(url, json={"baseId": base_id}, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return cast("list[Any]", result.get("data", {}).get("relations", []))

    def get_relation_detail(
        self, loader: Any, base_id: str, rel_code: str
    ) -> Any | None:
        """Look up relation detail from cached relations."""
        _ = loader
        for r in self.get_relations(loader, base_id):
            if r.get("relationCode") == rel_code:
                return r
        return None

    def create_relation(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_relation(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_relation(self, base_id: str, object_code: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Datasource CRUD (remote, read-only) --

    def get_datasources(self, loader: Any, base_id: str) -> list[Any]:
        """Fetch datasources from remote endpoint (no local cache — Platform handles caching)."""
        _ = loader
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listDatasources"
        response = client.post(url, json={"baseId": base_id}, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return cast("list[Any]", result.get("data", {}).get("dbsources", []))

    def get_datasource_detail(
        self, loader: Any, base_id: str, db_id: str
    ) -> Any | None:
        """Look up datasource from cached datasources."""
        _ = loader
        for ds in self.get_datasources(loader, base_id):
            db_list = ds.get("db", [])
            if db_list and isinstance(db_list, list) and db_list:
                if str(db_list[0].get("dbId", "")) == db_id:
                    return ds
            elif str(ds.get("dbId", ds.get("db_id", ""))) == db_id:
                return ds
        return None

    def create_datasource(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Action CRUD (remote, read-only) --

    def get_actions(self, loader: Any, base_id: str, object_code: str) -> list[Any]:
        """Fetch actions from remote endpoint (no local cache — Platform handles caching)."""
        _ = loader
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listActions"
        response = client.post(
            url,
            json={"baseId": base_id, "objectCode": object_code},
            headers=headers,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return cast("list[Any]", result.get("data", {}).get("actions", []))

    def get_action_detail(
        self,
        loader: Any,
        base_id: str,
        object_code: str,
        action_code: str,
    ) -> Any | None:
        """Look up action from cached actions."""
        _ = loader
        for a in self.get_actions(loader, base_id, object_code):
            if a.get("actionCode") == action_code:
                return a
        return None

    def create_action(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_action(
        self,
        base_id: str,
        object_code: str,
        action_code: str,
        obj: Any,
    ) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_action(self, base_id: str, object_code: str, action_code: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Scene management (remote, read-only) --

    def list_scenes(self, base_id: str) -> list[Any]:
        """Fetch scenes from remote endpoint (no local cache — Platform handles caching)."""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/listScenes"
        response = client.post(url, json={"baseId": base_id}, headers=headers)
        response.raise_for_status()
        return cast("list[Any]", response.json())

    def get_scene_members(
        self, base_id: str, scene_id: str
    ) -> tuple[list[str], list[str]]:
        """Return (object_codes, view_codes) for a remote scene.

        Calls get_scene_details and extracts codes from the response.
        """
        try:
            detail = self.get_scene_details(None, base_id, scene_id)
        except Exception:
            logger.debug(
                "get_scene_members: get_scene_details failed base_id=%r scene_id=%r",
                base_id,
                scene_id,
                exc_info=True,
            )
            return [], []
        # obj_codes = [o.get("objectCode", "") for o in detail.get("objects", []) or []]
        obj_codes = [o.get("object_code", "") for o in detail.get("objects", []) or []]
        vw_codes = [
            v.get("view_code", "") or v.get("view_id", "")
            for v in (detail.get("views") or [])
        ]
        return [c for c in obj_codes if c], [c for c in vw_codes if c]

    def query_scenes(self, base_id: str, keyword: str | None) -> list[Any]:
        """Query scenes with keyword filter (client-side filter on cached)."""
        scenes = self.list_scenes(base_id)
        if not keyword:
            return scenes
        kw = keyword.strip().lower()
        return [
            s
            for s in scenes
            if kw in str(s.get("sceneName", "")).lower()
            or kw in str(s.get("sceneCode", "")).lower()
        ]

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        """Count scenes matching keyword."""
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
        """Fetch scene details from remote endpoint (no local cache — Platform handles caching)."""
        _ = loader
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologyEntityController/sceneDetails"
        body: dict[str, Any] = {"sceneId": scene_id}
        if view_code:
            body["viewCode"] = ",".join(view_code)
        if object_code:
            body["objectCode"] = ",".join(object_code)
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        raw = response.json()
        # Unwrap remote API envelope: {code: 200, data: {...}} -> {...}
        if isinstance(raw, dict) and "data" in raw and raw.get("code") == 200:
            detail = cast("dict[str, Any]", raw["data"])
        else:
            detail = cast("dict[str, Any]", raw)

        # DtStudio returns actions at top-level detail.actions (not nested under objects).
        # Merge them into objects by belongObjectCode so consumers see object.actions.
        top_acts = detail.get("actions")
        if isinstance(top_acts, list) and top_acts:
            act_by_obj: dict[str, list[dict[str, Any]]] = {}
            for a in top_acts:
                boc = str(a.get("belongObjectCode") or "")
                if boc:
                    act_by_obj.setdefault(boc, []).append(a)
            for obj in detail.get("objects") or []:
                obj_code = str(obj.get("objectCode") or "")
                if obj_code in act_by_obj:
                    obj_actions = list(obj.get("actions") or [])
                    obj["actions"] = obj_actions + act_by_obj[obj_code]

        _normalize_remote_detail(detail)

        return detail

    def query_ontologies_by_scene(
        self,
        loader: object,
        base_id: str,
        scene_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """Query ontologies by scene with pagination via remote OntologySceneController.

        Supports scene_id="-1" for all scenes (global search).
        """
        _ = loader
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologySceneController/queryOntologies"
        body: dict[str, Any] = {
            "sceneId": scene_id,
            "page": page,
            "pageSize": page_size,
        }
        if keyword:
            body["keyword"] = keyword
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        raw = response.json()
        # Unwrap remote API envelope
        if isinstance(raw, dict) and raw.get("code") == 200:
            data = raw.get("data", [])
            if isinstance(data, list):
                return {
                    "data": {"objects": data, "views": []},
                    "totalCount": raw.get("totalCount", len(data)),
                }
            return {
                "data": {"objects": [], "views": []},
                "totalCount": raw.get("totalCount", 0),
            }
        return {"data": {"objects": [], "views": []}, "totalCount": 0}

    # -- Scene CRUD (remote, read-only) --

    def create_scene(self, base_id: str, scene: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_scene(self, base_id: str, scene_id: str, updates: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_scene(self, base_id: str, scene_id: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def add_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def remove_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Scene reverse-lookup queries (remote, read-only) --

    def get_object_scene_count(self, base_id: str, object_code: str) -> int:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def get_view_scene_count(self, base_id: str, view_code: str) -> int:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def remove_object_from_all_scenes(self, base_id: str, object_code: str) -> int:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def remove_view_from_all_scenes(self, base_id: str, view_code: str) -> int:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def get_scenes_containing_object(self, base_id: str, object_code: str) -> list[str]:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Object CRUD (remote, read-only) --

    def create_object(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_object(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_object(self, base_id: str, object_code: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def get_term_scope_info(self, base_id: str, object_code: str) -> dict[str, Any]:
        """Return {library_id, scene_id} identifying which scene contains object_code.

        Queries remote list_scenes and checks scene members for the given object_code.
        Returns default (library_id="PERSONAL_LIB", scene_id="") when not found.
        """
        try:
            scenes = self.list_scenes(base_id)
        except Exception:
            logger.debug(
                "get_term_scope_info: list_scenes failed for base_id=%r",
                base_id,
                exc_info=True,
            )
            return {"library_id": "PERSONAL_LIB", "scene_id": ""}
        scene_list: list[Any] = scenes
        if isinstance(scenes, dict):
            scene_list = scenes.get("data", scenes.get("scenes", []))
        for s in scene_list:
            if not isinstance(s, dict):
                continue
            scene_id = str(s.get("sceneId") or s.get("scene_id") or "")
            try:
                obj_codes, _ = self.get_scene_members(base_id, scene_id)
            except Exception:
                continue
            if object_code in obj_codes:
                return {
                    "library_id": "PERSONAL_LIB",
                    "scene_id": scene_id,
                }
        return {"library_id": "PERSONAL_LIB", "scene_id": ""}


class RemoteKnowledgeBackend:
    """KnowledgeBackend that forwards search operations to a remote HTTP service.

    Graph query is not supported — always returns empty.
    """

    def __init__(
        self,
        source_url: str,
        auth_config: dict[str, Any] | None = None,
    ) -> None:
        self._source_url = source_url.rstrip("/")
        self._auth_config = auth_config
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy httpx client creation."""
        if self._client is None:
            import httpx  # noqa: PLC0415

            self._client = httpx.Client(timeout=httpx.Timeout(30.0))
        return self._client

    def _build_auth_headers(self) -> dict[str, str]:
        """Build authentication headers from auth_config."""
        if not self._auth_config:
            return {}
        # Direct headers passthrough (for custom auth like ssoType/accountCode)
        headers_dict = self._auth_config.get("headers")
        if isinstance(headers_dict, dict):
            return {str(k): str(v) for k, v in headers_dict.items()}
        auth_type = self._auth_config.get("type", "").lower()
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {self._auth_config.get('token', '')}"}
        if auth_type == "api_key":
            header_name = self._auth_config.get("headerName", "X-API-Key")
            return {header_name: self._auth_config.get("apiKey", "")}
        return {}

    def configure(
        self, source_url: str, auth_config: dict[str, Any] | None = None
    ) -> None:
        """Dynamically set source_url and auth_config after construction.

        Used by Platform to inject per-base configuration into backends created
        by zero-arg factories (which don't know about the base at factory time).
        """
        if source_url:
            self._source_url = source_url.rstrip("/")
        if auth_config is not None:
            self._auth_config = auth_config
        self._client = None  # Reset client to pick up new config

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            with suppress(Exception):
                self._client.close()
            self._client = None

    # ── KnowledgeBackend Protocol ───────────────────────────────────────

    def search_candidates(
        self, query: str, *, scope: str = "all", limit: int = 20
    ) -> list[Any]:
        """Forward candidate search to remote service."""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/search/candidates"
        body: dict[str, Any] = {"query": query, "scope": scope, "limit": limit}
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return cast("list[Any]", response.json())

    def disambiguate(self, candidates: list[Any], query: str) -> list[Any]:
        """Forward disambiguation to remote service."""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/search/disambiguate"
        body: dict[str, Any] = {"candidates": candidates, "query": query}
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return cast("list[Any]", response.json())

    def prepare_clarification(
        self, query: str, slots: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Forward clarification preparation to remote service."""
        return {}

    def finalize_clarification(self, clarification_id: str) -> dict[str, Any]:
        """Forward clarification finalization to remote service."""
        return {}

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        """Remote knowledge is read-only — term sync is not supported."""
        _ = entity_code, entity_name, entity_source, fields, backfill_vectors
        logger.debug("Remote knowledge: sync_terms skipped (read-only)")

    def remove_terms(self, entity_code: str) -> None:
        """Remote knowledge is read-only — term removal is not supported."""
        _ = entity_code
        logger.debug("Remote knowledge: remove_terms skipped (read-only)")

    def get_term(self, term_code: str, term_type_code: str) -> str | None:
        """Remote knowledge does not support per-term lookup."""
        return None

    def term_exists(self, term_code: str, term_type_code: str) -> bool:
        """Remote knowledge does not support existence checks."""
        return False

    def get_term_by_ids(
        self, keys: list[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """Remote knowledge does not support batch lookup."""
        return {}

    def get_type_codes_by_category(self, categories: list[int]) -> list[str]:
        """Remote knowledge does not support category lookup."""
        return []

    def embed(self, text: str) -> list[float]:
        """Remote knowledge does not support local embedding."""
        return [0.0] * 768

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Remote knowledge does not support local embedding."""
        return [[0.0] * 768 for _ in texts]

    def search_by_embedding(
        self, vector: list[float], term_types: list[str], limit: int = 20
    ) -> list[Any]:
        """Forward embedding search to remote service."""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/search/by-embedding"
        body: dict[str, Any] = {
            "vector": vector,
            "termTypes": term_types,
            "limit": limit,
        }
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        return cast("list[Any]", response.json())

    def resolve_dimension_value(self, value_term_id: str) -> Any:
        """Remote knowledge does not support dimension resolution."""
        from datacloud_platform.models.shared import DimensionProperty

        return DimensionProperty(property_code="", object_code="")

    def get_referenced_by(self, value_term_id: str) -> list[Any]:
        """Remote knowledge does not support reference lookup."""
        return []

    def resolve_object_for_property(self, property_code: str) -> str | None:
        """Remote knowledge does not support property resolution."""
        return None

    def search_ontology(
        self,
        base_id: str,
        scene_ids: list[str],
        *,
        keyword: str,
        query_type: str = "vector",
        search_scope: str = "all",
        ontology_type: list[str] | None = None,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
        property_code: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Forward ontology search to remote service (no caching — real-time).

        接口层传入的 scene_ids 已经是 scene_id，直接使用。
        """
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/search/ontology"
        # TODO(remote-api): 远程 /search/ontology 接受 sceneId（单字符串）而非 sceneIds（数组），
        # 暂传首个 scene_id。待远程团队支持 sceneIds 列表后改回。
        body: dict[str, Any] = {
            "keyword": keyword,
            "sceneId": scene_ids[0] if scene_ids else "",
            "queryType": query_type,
            "searchScope": search_scope,
            "pageSize": kwargs.get("page_size", 20),
            "resultPerType": kwargs.get("result_per_type", 5),
        }
        if ontology_type:
            body["ontologyType"] = ontology_type
        if object_code:
            body["objectCode"] = object_code
        if view_code:
            body["viewCode"] = view_code
        if property_code:
            body["propertyCode"] = property_code
        if "page_token" in kwargs:
            body["pageToken"] = kwargs["page_token"]
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        raw = response.json()
        # Unwrap remote API envelope: {code: 200, data: {...}} -> {...}
        if isinstance(raw, dict) and "data" in raw and raw.get("code") == 200:
            result = cast("dict[str, Any]", raw["data"])
        else:
            result = cast("dict[str, Any]", raw)
        # Normalize remote field names to local expectations
        _normalize_remote_search_result(result)
        return result

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
        """Remote knowledge does not support graph queries — returns empty."""
        _ = base_id, scene_id, object_code, match_by, values, step
        return {"nodes": [], "edges": []}

    def update_scores(self, records: list[Any]) -> None:
        """Remote knowledge does not support score updates."""
        _ = records
        logger.debug("Remote knowledge: update_scores skipped (read-only)")

    def search_instances(
        self,
        base_id: str,
        *,
        object_code: str,
        select: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Remote knowledge does not support instance search — returns empty."""
        _ = base_id, object_code, select, where
        logger.debug("Remote knowledge: search_instances skipped (not supported)")
        return {"data": [], "totalCount": 0}

    def graph_path(
        self,
        base_id: str,
        scene_id: str,
        *,
        match_by: str = "name",
        start_node: str,
        end_node: str = "",
        direction: str = "forward",
    ) -> dict[str, Any]:
        """Remote knowledge does not support graph path — returns empty."""
        _ = base_id, scene_id, match_by, start_node, end_node, direction
        logger.debug("Remote knowledge: graph_path skipped (not supported)")
        return {"path": [], "edges": [], "hops": -1}
