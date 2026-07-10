"""Remote adapter — HTTP-forwarding backends for remote ontology & term services.

Refactored from datacloud_server/adapters/remote_adapter.py into two separate
Platform Backend classes: RemoteOntologyBackend (OntologyBackend Protocol) and
RemoteTermBackend (TermBackend Protocol).
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

    # ── OntologyBackend Protocol ── helpers ─────────────────────────────

    def _find_in_scenes(
        self,
        base_id: str,
        *,
        object_code: list[str] | None = None,
        view_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Iterate scenes to find the first scene containing target objects/views."""
        scenes = self.list_scenes(base_id)
        for s in scenes:
            sid = str(s.get("sceneId", ""))
            if not sid:
                continue
            detail = self.get_scene_details(
                sid, base_id=base_id, object_code=object_code, view_code=view_code
            )
            if object_code and detail.get("objects"):
                return detail
            if view_code and detail.get("views"):
                return detail
        return {}

    # ── OntologyBackend Protocol ── parse / load ───────────────────────

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

    def batch_import_ontology(
        self,
        base_path: Any,
        objects: list[dict[str, Any]],
        views: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        dbsources: list[dict[str, Any]],
        *,
        base_id: str = "",
    ) -> dict[str, int]:
        """Remote ontology is read-only — batch import is not supported."""
        raise PermissionError("Remote ontology base is read-only")

    def create_table(self, object_code: str, fields: list[dict[str, Any]]) -> None:
        """Remote ontology is read-only — DDL is not supported."""
        raise PermissionError("Remote ontology base is read-only")

    def drop_table(self, object_code: str) -> None:
        """Remote ontology is read-only — DDL is not supported."""
        raise PermissionError("Remote ontology base is read-only")

    # ── Object queries ─────────────────────────────────────────────────

    def get_objects(
        self,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 200,
        **kw: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query objects via remote OntologySceneController (global search, sceneId=-1).

        Returns:
            (items, totalCount) tuple.
        """
        _ = owner_type, user_code, kw
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologySceneController/queryOntologies"
        body: dict[str, Any] = {
            "sceneId": "-1",
            "pageIndex": page,
            "pageSize": page_size,
        }
        if keyword:
            body["queryKeyWord"] = keyword
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        raw = response.json()
        if isinstance(raw, dict) and raw.get("code") == 200:
            data = raw.get("data", raw)
            if isinstance(data, list):
                items: list[dict[str, Any]] = [
                    self._normalize_query_ontology_item(item) for item in data
                ]
                return items, raw.get("totalCount", len(items))
            items = (
                data.get("records") or data.get("items") or data.get("objects") or []
            )
            total: int = raw.get("totalCount", len(items))
            return items, total
        return [], 0

    def get_object_detail(
        self, object_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single object detail via two-step remote lookup.

        1. queryOntologies with queryKeyword=object_code → verify existence
        2. sceneDetails with objectCode=[object_code] → full detail
        """
        # Step 1: global search for the object summary (all pages)
        items = self._query_ontologies_all_pages(
            keyword=object_code, query_type="object"
        )

        found = False
        matched_scene_id = ""
        for item in items:
            code = (
                item.get("ontologyCode")
                or item.get("code")
                or item.get("object_code", "")
            )
            if code == object_code:
                found = True
                matched_scene_id = str(item.get("sceneId", ""))
                break

        if not found:
            return None

        # Step 2: get full detail via sceneDetails with matched sceneId
        scene_id = matched_scene_id or "-1"
        detail = self.get_scene_details(scene_id, base_id=base_id)

        matched_obj: dict[str, Any] | None = None
        for obj in detail.get("objects", []) or []:
            code = obj.get("object_code") or obj.get("code", "")
            if code == object_code:
                matched_obj = dict(obj)
                break

        if matched_obj is None:
            return None

        # Enrich with actions belonging to this object
        actions = [
            a
            for a in (detail.get("actions") or [])
            if a.get("belongObjectCode") == object_code
        ]
        if actions:
            matched_obj["actions"] = actions

        # Enrich with relations involving this object
        relations = [
            r
            for r in (detail.get("relations") or [])
            if r.get("sourceObjectCode") == object_code
            or r.get("targetObjectCode") == object_code
        ]
        if relations:
            matched_obj["relations"] = relations

        return matched_obj

    def get_object_detail_from_raw(
        self, raw: dict[str, Any], object_code: str
    ) -> dict[str, Any] | None:
        """Remote ontology does not support raw-based detail."""
        return None

    def get_object_subtree(
        self, object_code: str, *, base_id: str = ""
    ) -> dict[str, Any]:
        """Get object subtree via two-step remote lookup.

        1. queryOntologies with queryKeyword=object_code → find sceneId
        2. sceneDetails with objectCode=[object_code] → full subtree
        """
        empty: dict[str, Any] = {
            "objects": [],
            "views": [],
            "relations": [],
            "actions": [],
            "dbsources": {"db": [], "doc": [], "api": []},
        }

        # Step 1: global search for the object summary (all pages)
        items = self._query_ontologies_all_pages(
            keyword=object_code, query_type="object"
        )

        matched_scene_id = ""
        for item in items:
            code = (
                item.get("ontologyCode")
                or item.get("code")
                or item.get("object_code", "")
            )
            if code == object_code:
                matched_scene_id = str(item.get("sceneId", ""))
                break

        if not matched_scene_id:
            return empty

        # Step 2: get scene details filtered by object_code
        detail = self.get_scene_details(
            matched_scene_id, base_id=base_id, object_code=[object_code]
        )
        if detail.get("objects"):
            return detail
        return empty

    def get_base_details(
        self,
        *,
        base_id: str = "",
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get comprehensive base detail — aggregated across all scenes."""
        scenes = self.list_scenes(base_id)
        all_objects: list[dict[str, Any]] = []
        all_views: list[dict[str, Any]] = []
        all_relations: list[dict[str, Any]] = []
        all_actions: list[dict[str, Any]] = []
        all_dbs: list[dict[str, Any]] = []
        seen_obj: set[str] = set()
        seen_vw: set[str] = set()
        seen_rel: set[str] = set()
        seen_db: set[str] = set()

        for s in scenes:
            sid = str(s.get("sceneId", ""))
            if not sid:
                continue
            detail = self.get_scene_details(
                sid,
                base_id=base_id,
                view_code=view_code,
                object_code=object_code,
            )
            for obj in detail.get("objects", []) or []:
                oc = obj.get("object_code", "")
                if oc and oc not in seen_obj:
                    seen_obj.add(oc)
                    all_objects.append(obj)
            for v in detail.get("views", []) or []:
                vc = v.get("view_code", "") or v.get("view_id", "")
                if vc and vc not in seen_vw:
                    seen_vw.add(vc)
                    all_views.append(v)
            for r in detail.get("relations", []) or []:
                rc = r.get("relation_code", "") or r.get("relationCode", "")
                if rc and rc not in seen_rel:
                    seen_rel.add(rc)
                    all_relations.append(r)
            for a in detail.get("actions", []) or []:
                all_actions.append(a)
            dbsources = detail.get("dbsources", {}) or {}
            for ds in dbsources.get("db", []) or []:
                db_id = str(ds.get("dbId", ds.get("db_id", "")))
                if db_id and db_id not in seen_db:
                    seen_db.add(db_id)
                    all_dbs.append(ds)

        return {
            "base": {"baseId": base_id},
            "scenes": scenes,
            "views": all_views,
            "objects": all_objects,
            "actions": all_actions,
            "relations": all_relations,
            "dbsources": {"db": all_dbs, "doc": [], "api": []},
            "version": "v0.1.0",
        }

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

    # -- View queries ───────────────────────────────────────────────────

    def get_views(
        self,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 200,
        **kw: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query views via remote OntologySceneController with type=view filter."""
        _ = owner_type, user_code, kw
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologySceneController/queryOntologies"
        body: dict[str, Any] = {
            "sceneId": "-1",
            "pageIndex": page,
            "pageSize": page_size,
            "type": "view",
        }
        if keyword:
            body["queryKeyWord"] = keyword
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        raw = response.json()
        if isinstance(raw, dict) and raw.get("code") == 200:
            data = raw.get("data", raw)
            if isinstance(data, list):
                items: list[dict[str, Any]] = [
                    self._normalize_query_view_item(item) for item in data
                ]
                return items, raw.get("totalCount", len(items))
            items = data.get("records") or data.get("items") or data.get("views") or []
            total: int = raw.get("totalCount", len(items))
            return items, total
        return [], 0

    def get_view_detail(
        self, view_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single view detail via two-step remote lookup.

        1. queryOntologies with queryKeyword=view_code, queryType=view → verify existence
        2. sceneDetails with viewCode=[view_code] → full detail
        """
        # Step 1: global search for the view summary (all pages)
        items = self._query_ontologies_all_pages(keyword=view_code, query_type="view")

        found = False
        matched_scene_id = ""
        for item in items:
            code = (
                item.get("ontologyCode")
                or item.get("code")
                or item.get("view_code", "")
            )
            if code == view_code:
                found = True
                matched_scene_id = str(item.get("sceneId", ""))
                break

        if not found:
            return None

        # Step 2: get full detail via sceneDetails with matched sceneId
        scene_id = matched_scene_id or "-1"
        detail = self.get_scene_details(
            scene_id, base_id=base_id, view_code=[view_code]
        )
        for v in detail.get("views", []) or []:
            code = v.get("view_code") or v.get("view_id") or v.get("code", "")
            if code == view_code:
                return cast("dict[str, Any]", v)
        return None

    def get_objects_by_view(
        self,
        view_code: str,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get object summaries referenced by a view via two-step remote lookup.

        1. queryOntologies with queryKeyword=view_code, queryType=view → find sceneId
        2. sceneDetails → extract objectCodes from view, return matching objects
        """
        _ = owner_type, user_code

        # Step 1: global search for the view summary (all pages)
        items = self._query_ontologies_all_pages(keyword=view_code, query_type="view")

        matched_scene_id = ""
        for item in items:
            code = (
                item.get("ontologyCode")
                or item.get("code")
                or item.get("view_code", "")
            )
            if code == view_code:
                matched_scene_id = str(item.get("sceneId", ""))
                break

        if not matched_scene_id:
            return []

        # Step 2: get scene details and extract objects referenced by the view
        detail = self.get_scene_details(matched_scene_id, base_id=base_id)
        obj_codes: set[str] = set()
        for v in detail.get("views", []) or []:
            if v.get("view_code") == view_code or v.get("view_id") == view_code:
                obj_codes.update(v.get("objectCodes", v.get("object_codes", [])) or [])
        if not obj_codes:
            return []
        result: list[dict[str, Any]] = []
        for obj in detail.get("objects", []) or []:
            if obj.get("object_code") in obj_codes:
                result.append(obj)
        if keyword:
            kw = keyword.strip().lower()
            result = [
                o
                for o in result
                if kw in str(o.get("objectName", o.get("object_name", ""))).lower()
                or kw in str(o.get("objectCode", o.get("object_code", ""))).lower()
                or kw in str(o.get("objectDesc", o.get("description", ""))).lower()
            ]
        return result

    # -- View CRUD (remote, read-only) --

    def create_view(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_view(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_view(self, base_id: str, object_code: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Relation queries ───────────────────────────────────────────────

    def get_relations(
        self,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 200,
        **kw: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get all relations by aggregating scene details across all scenes."""
        _ = owner_type, user_code, kw
        all_relations: list[dict[str, Any]] = []
        scenes = self.list_scenes(base_id)
        for s in scenes:
            sid = str(s.get("sceneId", ""))
            if not sid:
                continue
            detail = self.get_scene_details(sid, base_id=base_id)
            all_relations.extend(detail.get("relations", []) or [])
        if keyword:
            kw_lower = keyword.strip().lower()
            all_relations = [
                r
                for r in all_relations
                if kw_lower
                in str(r.get("relationName", r.get("relation_name", ""))).lower()
                or kw_lower
                in str(r.get("relationCode", r.get("relation_code", ""))).lower()
                or kw_lower
                in str(r.get("relationDesc", r.get("description", ""))).lower()
            ]
        total = len(all_relations)
        start = (page - 1) * page_size
        return all_relations[start : start + page_size], total

    def get_relation_detail(
        self, relation_code: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single relation detail by iterating scenes."""
        scenes = self.list_scenes(base_id)
        for s in scenes:
            sid = str(s.get("sceneId", ""))
            if not sid:
                continue
            detail = self.get_scene_details(sid, base_id=base_id)
            for r in detail.get("relations", []) or []:
                if (
                    r.get("relation_code") == relation_code
                    or r.get("relationCode") == relation_code
                ):
                    return cast("dict[str, Any]", r)
        return None

    def get_relations_by_object(
        self,
        object_code: str,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all relation details involving object_code via two-step remote lookup.

        1. queryOntologies with queryKeyword=object_code → find sceneId
        2. sceneDetails with matched sceneId → filter relations involving object_code
        """
        _ = owner_type, user_code
        result: list[dict[str, Any]] = []

        # Step 1: global search for the object summary (all pages)
        items = self._query_ontologies_all_pages(
            keyword=object_code, query_type="object"
        )

        matched_scene_id = ""
        for item in items:
            code = (
                item.get("ontologyCode")
                or item.get("code")
                or item.get("object_code", "")
            )
            if code == object_code:
                matched_scene_id = str(item.get("sceneId", ""))
                break

        if not matched_scene_id:
            return result

        # Step 2: get scene details and filter relations
        detail = self.get_scene_details(matched_scene_id, base_id=base_id)
        for r in detail.get("relations", []) or []:
            src = r.get("sourceObjectCode", r.get("source_class", ""))
            tgt = r.get("targetObjectCode", r.get("target_class", ""))
            if src == object_code or tgt == object_code:
                result.append(r)
        return result

    # -- Relation CRUD (remote, read-only) --

    def create_relation(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def update_relation(self, base_id: str, object_code: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_relation(self, base_id: str, object_code: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Datasource queries ─────────────────────────────────────────────

    def get_datasources(
        self,
        *,
        base_id: str = "",
        keyword: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get all datasources by aggregating scene details across all scenes."""
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        scenes = self.list_scenes(base_id)
        for s in scenes:
            sid = str(s.get("sceneId", ""))
            if not sid:
                continue
            detail = self.get_scene_details(sid, base_id=base_id)
            dbsources = detail.get("dbsources", {}) or {}
            for ds in dbsources.get("db", []) or []:
                db_id = str(ds.get("dbId", ds.get("db_id", "")))
                if db_id and db_id not in seen:
                    seen.add(db_id)
                    result.append(ds)
        if keyword:
            kw = keyword.strip().lower()
            result = [
                ds
                for ds in result
                if kw in str(ds.get("dbName", ds.get("db_name", ""))).lower()
                or kw in str(ds.get("dbId", ds.get("db_id", ""))).lower()
            ]
        return result, len(result)

    def get_datasource_detail(
        self, db_id: str, *, base_id: str = ""
    ) -> dict[str, Any] | None:
        """Get single datasource detail by iterating scenes."""
        scenes = self.list_scenes(base_id)
        for s in scenes:
            sid = str(s.get("sceneId", ""))
            if not sid:
                continue
            detail = self.get_scene_details(sid, base_id=base_id)
            dbsources = detail.get("dbsources", {}) or {}
            db_list = dbsources.get("db", []) or []
            for ds in db_list:
                if str(ds.get("dbId", ds.get("db_id", ""))) == db_id:
                    return cast("dict[str, Any]", ds)
        return None

    # -- Datasource CRUD (remote, read-only) --

    def create_datasource(self, base_id: str, obj: Any) -> Any:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    def delete_datasource(self, base_id: str, db_id: str) -> None:
        """Remote ontology is read-only — write forbidden."""
        raise PermissionError("Remote ontology base is read-only")

    # -- Action queries ─────────────────────────────────────────────────

    def get_actions(
        self,
        object_code: str,
        *,
        base_id: str = "",
        owner_type: str | None = None,
        user_code: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get all actions for an object by searching scene details."""
        _ = owner_type, user_code
        detail = self._find_in_scenes(base_id, object_code=[object_code])
        actions: list[dict[str, Any]] = []
        for obj in detail.get("objects", []) or []:
            if obj.get("object_code") == object_code:
                actions = list(obj.get("actions", []) or [])
                break
        if keyword:
            kw = keyword.strip().lower()
            actions = [
                a
                for a in actions
                if kw in str(a.get("actionName", a.get("action_name", ""))).lower()
                or kw in str(a.get("actionCode", a.get("action_code", ""))).lower()
                or kw in str(a.get("actionDesc", a.get("description", ""))).lower()
            ]
        return actions, len(actions)

    def get_action_detail(
        self,
        object_code: str,
        action_code: str,
        *,
        base_id: str = "",
    ) -> dict[str, Any] | None:
        """Get single action detail by iterating scenes."""
        detail = self._find_in_scenes(base_id, object_code=[object_code])
        for obj in detail.get("objects", []) or []:
            for a in obj.get("actions", []) or []:
                if (
                    a.get("action_code") == action_code
                    or a.get("actionCode") == action_code
                ):
                    return cast("dict[str, Any]", a)
        return None

    # -- Action CRUD (remote, read-only) --

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
        """Fetch scenes from remote endpoint."""
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologySceneController/query"
        body: dict[str, Any] = {"pageSize": 200, "pageIndex": 1}
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        raw = response.json()
        # Unwrap remote API envelope
        if isinstance(raw, dict) and raw.get("code") == 200:
            data = raw.get("data", [])
            if isinstance(data, list):
                return data
            return cast("list[Any]", data.get("records", data))
        return []

    def get_scene_members(
        self, base_id: str, scene_id: str
    ) -> tuple[list[str], list[str]]:
        """Return (object_codes, view_codes) for a remote scene."""
        try:
            detail = self.get_scene_details(scene_id, base_id=base_id)
        except Exception:
            logger.debug(
                "get_scene_members: get_scene_details failed base_id=%r scene_id=%r",
                base_id,
                scene_id,
                exc_info=True,
            )
            return [], []
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
        scene_id: str,
        *,
        base_id: str = "",
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch scene details from remote endpoint."""
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
        scene_id: str,
        *,
        base_id: str = "",
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        type: str | None = None,
        owner_type: str | None = None,
        user_code: str | None = None,
        cross_scene: bool = False,
    ) -> dict[str, Any]:
        """Query ontologies by scene with pagination via remote OntologySceneController.

        Supports scene_id="-1" for all scenes (global search).
        Returns a single page — call ``_query_ontologies_all_pages`` to fetch all pages.
        """
        _ = owner_type, user_code, cross_scene
        if cross_scene:
            scene_id = "-1"
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologySceneController/queryOntologies"
        body: dict[str, Any] = {
            "sceneId": scene_id,
            "pageIndex": page,
            "pageSize": page_size,
        }
        if keyword:
            body["queryKeyWord"] = keyword
        body["queryType"] = type or "object"
        response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        raw = response.json()
        if isinstance(raw, dict) and raw.get("code") == 200:
            data = raw.get("data", [])
            if isinstance(data, list):
                query_type = str(type or "object").lower()
                if query_type == "view":
                    views = [self._normalize_query_view_item(item) for item in data]
                    return {
                        "data": {"objects": [], "views": views},
                        "totalCount": raw.get("totalCount", len(data)),
                    }
                objects = [self._normalize_query_ontology_item(item) for item in data]
                return {
                    "data": {"objects": objects, "views": []},
                    "totalCount": raw.get("totalCount", len(data)),
                }
            return {
                "data": {"objects": [], "views": []},
                "totalCount": raw.get("totalCount", 0),
            }
        return {"data": {"objects": [], "views": []}, "totalCount": 0}

    def _query_ontologies_all_pages(
        self,
        *,
        keyword: str,
        query_type: str,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch ALL pages from queryOntologies (sceneId=-1) for a keyword search.

        Uses totalCount / nextPageToken to auto-paginate until all results are fetched.
        """
        _ = self  # method lives on self, unused in body
        client = self._get_client()
        headers = self._build_auth_headers()
        url = f"{self._source_url}/OntologySceneController/queryOntologies"

        all_data: list[dict[str, Any]] = []
        total_count = 0
        page_index = 1

        while True:
            body: dict[str, Any] = {
                "sceneId": "-1",
                "pageIndex": page_index,
                "pageSize": page_size,
                "queryKeyWord": keyword,
                "queryType": query_type,
            }
            response = client.post(url, json=body, headers=headers)
            response.raise_for_status()
            raw = response.json()

            if isinstance(raw, dict) and raw.get("code") == 200:
                data = raw.get("data", [])
                page_items: list[dict[str, Any]] = (
                    data if isinstance(data, list) else data.get("records", []) or []
                )
                all_data.extend(page_items)
                total_count = int(raw.get("totalCount") or len(all_data))
                next_token = raw.get("nextPageToken")
                if not next_token or len(all_data) >= total_count:
                    break
                page_index = int(str(next_token))
            else:
                break

        return all_data

    @staticmethod
    def _normalize_query_ontology_item(raw: dict[str, Any]) -> dict[str, Any]:
        """Convert remote queryOntologies object item to our object summary format."""
        return {
            "objectCode": raw.get("ontologyCode", ""),
            "objectName": raw.get("ontologyName", ""),
            "objectDesc": raw.get("ontologyDesc") or "",
            "objectSource": raw.get("ontologySource") or "",
            "fieldCount": 0,
            "actionCount": 0,
            "ownerType": "enterprise",
            "userCode": None,
            "sceneId": raw.get("sceneId", ""),
        }

    @staticmethod
    def _normalize_query_view_item(raw: dict[str, Any]) -> dict[str, Any]:
        """Convert remote queryOntologies view item to our view summary format."""
        return {
            "viewCode": raw.get("viewCode", ""),
            "viewName": raw.get("viewName", ""),
            "description": raw.get("viewDesc") or "",
            "objectCodes": [],
            "ownerType": "enterprise",
            "userCode": None,
            "_sceneId": raw.get("sceneId") or "",
        }

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

    # -- Atomic ontology methods (scene extraction) ─────────────────────

    def extract_objects_detail(
        self, object_codes: list[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract ObjectType JSON for each code by querying scene details."""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        scenes = self.list_scenes(base_id)
        for s in scenes:
            sid = str(s.get("sceneId", ""))
            if not sid:
                continue
            detail = self.get_scene_details(
                sid, base_id=base_id, object_code=object_codes
            )
            for obj in detail.get("objects", []) or []:
                oc = obj.get("object_code", "")
                if oc in object_codes and oc not in seen:
                    seen.add(oc)
                    result.append(obj)
        return result

    def extract_views_detail(
        self, view_codes: list[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract View JSON for each code by querying scene details."""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        scenes = self.list_scenes(base_id)
        for s in scenes:
            sid = str(s.get("sceneId", ""))
            if not sid:
                continue
            detail = self.get_scene_details(sid, base_id=base_id, view_code=view_codes)
            for v in detail.get("views", []) or []:
                vc = v.get("view_code", "") or v.get("view_id", "")
                if vc in view_codes and vc not in seen:
                    seen.add(vc)
                    result.append(v)
        return result

    def extract_relations(
        self, object_codes_set: set[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract bidirectional relations where both ends are in object_codes_set."""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        scenes = self.list_scenes(base_id)
        for s in scenes:
            sid = str(s.get("sceneId", ""))
            if not sid:
                continue
            detail = self.get_scene_details(sid, base_id=base_id)
            for r in detail.get("relations", []) or []:
                src = r.get("sourceObjectCode", r.get("source_class", ""))
                tgt = r.get("targetObjectCode", r.get("target_class", ""))
                if src in object_codes_set and tgt in object_codes_set:
                    rc = r.get("relation_code", "") or r.get("relationCode", "")
                    if rc and rc not in seen:
                        seen.add(rc)
                        result.append(r)
        return result

    def get_term_scope_info(self, base_id: str, object_code: str) -> dict[str, Any]:
        """Return {library_id, scene_id} identifying which scene contains object_code."""
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

    # ── Property resolution ───────────────────────────────────────────

    def resolve_property_name(
        self, name_text: str, scope_code: str, *, base_id: str = ""
    ) -> tuple[str, str] | None:
        """Resolve a single Chinese property name → (field_code, field_name).

        Iterates scenes, finds the object matching scope_code, then looks up
        the property by field_name / aliases in the object's fields.
        """
        detail = self._find_in_scenes(base_id, object_code=[scope_code])
        for obj in detail.get("objects", []) or []:
            if obj.get("object_code") != scope_code:
                continue
            fields = obj.get("fields", obj.get("properties", [])) or []
            for f in fields:
                fname = f.get("field_name", f.get("propertyName", ""))
                fcode = f.get("field_code", f.get("propertyCode", ""))
                aliases: list[str] = f.get("aliases", []) or []
                if fname == name_text or name_text in aliases:
                    return (fcode, fname)
        return None

    def resolve_property_names(
        self, name_texts: list[str], scope_code: str, *, base_id: str = ""
    ) -> dict[str, tuple[str, str]]:
        """Batch resolve property names → {name_text: (field_code, field_name)}."""
        result: dict[str, tuple[str, str]] = {}
        for name in name_texts:
            resolved = self.resolve_property_name(name, scope_code, base_id=base_id)
            if resolved is not None:
                result[name] = resolved
        return result

    def get_property_aliases(
        self, field_code: str, scope_code: str, *, base_id: str = ""
    ) -> list[str]:
        """Get all aliases (including field_name) for a given field_code."""
        detail = self._find_in_scenes(base_id, object_code=[scope_code])
        for obj in detail.get("objects", []) or []:
            if obj.get("object_code") != scope_code:
                continue
            fields = obj.get("fields", obj.get("properties", [])) or []
            for f in fields:
                fcode = f.get("field_code", f.get("propertyCode", ""))
                if fcode == field_code:
                    fname = f.get("field_name", f.get("propertyName", ""))
                    aliases: list[str] = list(f.get("aliases", []) or [])
                    return [fname, *aliases] if fname else aliases
        return []

    # ── Scope resolution helpers ───────────────────────────────────────

    def get_view_included_objects(
        self, ontology_code: str, *, base_id: str = ""
    ) -> list[str]:
        """Return object codes included in the view identified by ontology_code."""
        detail = self._find_in_scenes(base_id, view_code=[ontology_code])
        for v in detail.get("views", []) or []:
            if v.get("view_code") == ontology_code or v.get("view_id") == ontology_code:
                return list(v.get("objectCodes", v.get("object_codes", [])) or [])
        return []

    def get_joinkey_related_objects(
        self, ontology_code: str, field_codes: list[str], *, base_id: str = ""
    ) -> list[str]:
        """Return object codes related to ontology_code via join key fields."""
        result: set[str] = set()
        scenes = self.list_scenes(base_id)
        for s in scenes:
            sid = str(s.get("sceneId", ""))
            if not sid:
                continue
            detail = self.get_scene_details(sid, base_id=base_id)
            for r in detail.get("relations", []) or []:
                src = r.get("sourceObjectCode", r.get("source_class", ""))
                tgt = r.get("targetObjectCode", r.get("target_class", ""))
                join_keys = (
                    r.get("joinKeys")
                    or r.get("join_keys")
                    or r.get("mappingFields")
                    or []
                )
                if src == ontology_code or tgt == ontology_code:
                    for jk in join_keys:
                        if isinstance(jk, dict):
                            jk_src = jk.get("sourceField", jk.get("source_column", ""))
                            jk_tgt = jk.get("targetField", jk.get("target_column", ""))
                            if jk_src in field_codes or jk_tgt in field_codes:
                                if src != ontology_code:
                                    result.add(src)
                                if tgt != ontology_code:
                                    result.add(tgt)
        return list(result)

    # ── Property term bindings ─────────────────────────────────────────

    def get_object_property_term_bindings(
        self,
        object_codes: list[str],
        *,
        base_id: str = "",
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query object-level property term bindings (bulk).

        Returns only properties that have terminology bindings configured.
        """
        _ = term_master_type
        result: list[dict[str, Any]] = []
        detail = self._find_in_scenes(base_id, object_code=object_codes)
        for obj in detail.get("objects", []) or []:
            if obj.get("object_code") not in object_codes:
                continue
            fields = obj.get("fields", obj.get("properties", [])) or []
            for f in fields:
                fcode = f.get("field_code", f.get("propertyCode", ""))
                if property_codes and fcode not in property_codes:
                    continue
                term = f.get("terminology", f.get("termType"))
                if term:
                    result.append(
                        {
                            "object_code": obj.get("object_code", ""),
                            "property_code": fcode,
                            "property_name": f.get(
                                "field_name", f.get("propertyName", "")
                            ),
                            "term_type": (term if isinstance(term, str) else str(term)),
                        }
                    )
        return result

    def get_view_property_term_bindings(
        self,
        view_codes: list[str],
        *,
        base_id: str = "",
        term_master_type: str | None = None,
        property_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query view-level property term bindings (bulk).

        View properties reference source_object → source_object_property,
        and the terminology is resolved from the underlying Object's Property.terminology.
        """
        _ = term_master_type
        result: list[dict[str, Any]] = []
        detail = self._find_in_scenes(base_id, view_code=view_codes)
        # Build a lookup: object_code → {property_code → terminology}
        obj_term_map: dict[str, dict[str, Any]] = {}
        for obj in detail.get("objects", []) or []:
            oc = obj.get("object_code", "")
            if not oc:
                continue
            fields = obj.get("fields", obj.get("properties", [])) or []
            field_map: dict[str, Any] = {}
            for f in fields:
                fcode = f.get("field_code", f.get("propertyCode", ""))
                term = f.get("terminology", f.get("termType"))
                if term:
                    field_map[fcode] = term
            if field_map:
                obj_term_map[oc] = field_map

        for v in detail.get("views", []) or []:
            if (
                v.get("view_code") not in view_codes
                and v.get("view_id") not in view_codes
            ):
                continue
            mappings = v.get("mappings", v.get("properties", [])) or []
            for m in mappings:
                src_obj = m.get("source_object", m.get("sourceObject", ""))
                src_prop = m.get(
                    "source_object_property", m.get("sourceObjectProperty", "")
                )
                prop_code = m.get("property_code", m.get("propertyCode", ""))
                if property_codes and prop_code not in property_codes:
                    continue
                obj_terms = obj_term_map.get(src_obj, {})
                term = obj_terms.get(src_prop)
                if term:
                    result.append(
                        {
                            "view_code": v.get("view_code", "") or v.get("view_id", ""),
                            "property_code": prop_code,
                            "property_name": m.get(
                                "property_name", m.get("propertyName", "")
                            ),
                            "source_object": src_obj,
                            "source_object_property": src_prop,
                            "term_type": (term if isinstance(term, str) else str(term)),
                        }
                    )
        return result


class RemoteTermBackend:
    """TermBackend that forwards term operations to a remote HTTP service.

    NOTE: Remote term backend is not yet fully implemented.  Most methods
    return empty results or raise NotImplementedError until the remote
    term API is defined.
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
        """Dynamically set source_url and auth_config after construction."""
        if source_url:
            self._source_url = source_url.rstrip("/")
        if auth_config is not None:
            self._auth_config = auth_config
        self._client = None

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            with suppress(Exception):
                self._client.close()
            self._client = None

    # ── TermBackend Protocol ────────────────────────────────────────────

    def search_terms(
        self,
        *,
        dataset_ids: list[str] | None = None,
        keyword: str | None = None,
        term_name: str | None = None,
        term_type: str | None = None,
        query_type: str = "fulltext",
        parent_term_code: str | None = None,
        label_filters: list[dict[str, Any]] | None = None,
        label_condition: str = "and",
        term_ids: list[str] | None = None,
        top_k: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Remote term search — not yet implemented."""
        logger.debug("Remote term: search_terms not yet implemented")
        return {"data": [], "totalCount": 0}

    def get_term_detail(
        self, *, dataset_id: str, term_id: str
    ) -> dict[str, Any] | None:
        """Remote term detail — not yet implemented."""
        logger.debug("Remote term: get_term_detail not yet implemented")
        return None

    def list_terms(
        self,
        *,
        dataset_id: str,
        term_type: str | None = None,
        term_type_no_eq: str | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Remote term list — not yet implemented."""
        logger.debug("Remote term: list_terms not yet implemented")
        return {
            "data": [],
            "totalCount": 0,
            "pageIndex": page_index,
            "pageSize": page_size,
        }

    def create_term(self, *, term: dict[str, Any]) -> dict[str, Any]:
        """Remote term creation — not yet implemented."""
        raise NotImplementedError("Remote term creation not yet implemented")

    def import_terms(
        self, *, dataset_id: str, terms: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Remote term import — not yet implemented."""
        raise NotImplementedError("Remote term import not yet implemented")

    def update_term(
        self, *, dataset_id: str, term_id: str, updates: dict[str, Any]
    ) -> None:
        """Remote term update — not yet implemented."""
        raise NotImplementedError("Remote term update not yet implemented")

    def delete_term(self, *, term_id: str) -> None:
        """Remote term deletion — not yet implemented."""
        raise NotImplementedError("Remote term deletion not yet implemented")

    def query_term_relations(
        self,
        *,
        term_id: str,
        relation_category: str | None = None,
        direction: str = "both",
        depth: int = 1,
    ) -> dict[str, Any]:
        """Remote term relations — not yet implemented."""
        logger.debug("Remote term: query_term_relations not yet implemented")
        return {"data": [], "totalCount": 0}

    # ── TermRelation ────────────────────────────────────────────────────

    def list_term_relations(
        self,
        *,
        source_term_id: str | None = None,
        target_term_id: str | None = None,
        relation_category: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

    def get_term_relation(self, *, relation_id: str) -> dict[str, Any] | None:
        return None

    def create_term_relation(self, *, relation: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Remote term relation not yet implemented")

    def update_term_relation(
        self, *, relation_id: str, updates: dict[str, Any]
    ) -> None:
        raise NotImplementedError("Remote term relation not yet implemented")

    def delete_term_relation(self, *, relation_id: str) -> None:
        raise NotImplementedError("Remote term relation not yet implemented")

    # ── TermName ────────────────────────────────────────────────────────

    def list_term_names(
        self, *, term_id: str | None = None, name_text: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_term_name(self, *, name_id: str) -> dict[str, Any] | None:
        return None

    def create_term_name(self, *, name: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Remote term name not yet implemented")

    def update_term_name(self, *, name_id: str, updates: dict[str, Any]) -> None:
        raise NotImplementedError("Remote term name not yet implemented")

    def delete_term_name(self, *, name_id: str) -> None:
        raise NotImplementedError("Remote term name not yet implemented")

    # ── TermKnowledge ───────────────────────────────────────────────────

    def list_term_knowledges(
        self, *, term_id: str | None = None, ext_system: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_term_knowledge(self, *, knowledge_id: str) -> dict[str, Any] | None:
        return None

    def create_term_knowledge(self, *, knowledge: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Remote term knowledge not yet implemented")

    def update_term_knowledge(
        self, *, knowledge_id: str, updates: dict[str, Any]
    ) -> None:
        raise NotImplementedError("Remote term knowledge not yet implemented")

    def delete_term_knowledge(self, *, knowledge_id: str) -> None:
        raise NotImplementedError("Remote term knowledge not yet implemented")

    # ── TermLibrary ─────────────────────────────────────────────────────

    def list_term_libraries(
        self,
        *,
        library_code: str | None = None,
        library_name: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

    def get_term_library(self, *, library_id: str) -> dict[str, Any] | None:
        return None

    def create_term_library(self, *, library: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Remote term library not yet implemented")

    def update_term_library(self, *, library_id: str, updates: dict[str, Any]) -> None:
        raise NotImplementedError("Remote term library not yet implemented")

    def delete_term_library(self, *, library_id: str) -> None:
        raise NotImplementedError("Remote term library not yet implemented")

    # ── TermType ────────────────────────────────────────────────────────

    def list_term_types(
        self, *, type_category: int | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_term_type(self, *, type_code: str) -> dict[str, Any] | None:
        return None

    def create_term_type(self, *, term_type: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Remote term type not yet implemented")

    def update_term_type(self, *, type_code: str, updates: dict[str, Any]) -> None:
        raise NotImplementedError("Remote term type not yet implemented")

    def delete_term_type(self, *, type_code: str) -> None:
        raise NotImplementedError("Remote term type not yet implemented")

    # ── Domain ──────────────────────────────────────────────────────────

    def list_domains(self, *, parent_id: str | None = None) -> list[dict[str, Any]]:
        return []

    def get_domain(self, *, domain_id: str) -> dict[str, Any] | None:
        return None

    def create_domain(self, *, domain: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Remote domain not yet implemented")

    def update_domain(self, *, domain_id: str, updates: dict[str, Any]) -> None:
        raise NotImplementedError("Remote domain not yet implemented")

    def delete_domain(self, *, domain_id: str) -> None:
        raise NotImplementedError("Remote domain not yet implemented")

    def list_domain_term_types(self, *, domain_id: str) -> list[dict[str, Any]]:
        return []

    # ── Vector ──────────────────────────────────────────────────────────

    def embed(self, text: str) -> list[float]:
        """Remote does not support local embedding."""
        return [0.0] * 768

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Remote does not support local embedding."""
        return [[0.0] * 768 for _ in texts]

    def search_by_embedding(
        self, vector: list[float], term_types: list[str], limit: int = 20
    ) -> list[Any]:
        """Remote does not support embedding search."""
        logger.debug("Remote term: search_by_embedding not yet implemented")
        return []

    # ── Sync ────────────────────────────────────────────────────────────

    def sync_terms(
        self,
        entity_code: str,
        entity_name: str,
        entity_source: str,
        fields: list[dict[str, Any]],
        *,
        backfill_vectors: bool = True,
    ) -> None:
        """Remote term is read-only — term sync is not supported."""
        _ = entity_code, entity_name, entity_source, fields, backfill_vectors
        logger.debug("Remote term: sync_terms skipped (read-only)")

    def remove_terms(self, entity_code: str) -> None:
        """Remote term is read-only — term removal is not supported."""
        _ = entity_code
        logger.debug("Remote term: remove_terms skipped (read-only)")

    # ── TermSyncHandler ─────────────────────────────────────────────

    def ensure_term_type(self, *, type_code: str, type_name: str) -> None:
        """Remote term: sync methods not supported over HTTP adapter."""
        logger.debug("Remote term: ensure_term_type skipped (not supported)")

    def upsert_terms(self, *, terms: list[dict[str, Any]]) -> list[str]:
        """Remote term: sync methods not supported over HTTP adapter."""
        logger.debug("Remote term: upsert_terms skipped (not supported)")
        return []

    def delete_terms(
        self,
        *,
        term_ids: list[str] | None = None,
        terms: list[dict[str, Any]] | None = None,
    ) -> None:
        """Remote term: sync methods not supported over HTTP adapter."""
        logger.debug("Remote term: delete_terms skipped (not supported)")
