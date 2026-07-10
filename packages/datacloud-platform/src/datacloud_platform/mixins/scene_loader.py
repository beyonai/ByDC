"""SceneLoaderMixin — scene-based ontology loading for DatacloudPlatform.

Provides methods to load ontology subsets from scenes, object/view codes,
or keyword-based semantic search.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from datacloud_data_sdk.ontology.loader import OntologyLoader

if TYPE_CHECKING:
    from datacloud_platform.backends.ontology import OntologyBackend, OntologyQueryable

logger = logging.getLogger(__name__)


class SceneLoaderMixin:
    """Mixin that provides scene-scoped and code-scoped ontology loading.

    Designed to be mixed into :class:`DatacloudPlatform`. All methods operate on
    ``self``, relying on the platform's ``_ontology_for``, ``_knowledge_for``,
    ``_base_path_for``, and ``inject_virtual_actions`` interfaces.
    """

    # ── Public API ──────────────────────────────────────────────────────────

    def load_ontology_from_scenes(
        self,
        base_id: str,
        scene_ids: list[str],
        *,
        object_codes: list[str] | None = None,
        view_codes: list[str] | None = None,
    ) -> OntologyLoader:
        """Load an ontology subset scoped to one or more scenes.

        1. Collect all member object/view codes from each scene.
        2. Intersect with optional *object_codes* / *view_codes* filters.
        3. Load the full ontology once.
        4. Extract only the filtered classes and views into a new loader.

        Args:
            base_id: Ontology base identifier.
            scene_ids: One or more scene IDs whose members define the scope.
            object_codes: Optional whitelist of object codes to further restrict scope.
            view_codes: Optional whitelist of view codes to further restrict scope.

        Returns:
            A new :class:`OntologyLoader` containing only the scoped objects and views,
            with virtual actions injected.
        """
        backend: OntologyBackend = self._ontology_for(base_id)  # type: ignore[attr-defined]

        # 1. Collect member codes from all scenes
        all_obj_codes: set[str] = set()
        all_vw_codes: set[str] = set()
        for sid in scene_ids:
            obj_codes, vw_codes = backend.get_scene_members(base_id, sid)
            all_obj_codes.update(obj_codes)
            all_vw_codes.update(vw_codes)

        # 2. Apply optional filters
        if object_codes is not None:
            allowed_obj = set(object_codes)
            all_obj_codes &= allowed_obj
        if view_codes is not None:
            allowed_vw = set(view_codes)
            all_vw_codes &= allowed_vw

        if not all_obj_codes and not all_vw_codes:
            logger.info(
                "load_ontology_from_scenes: no codes after filtering for base_id=%s",
                base_id,
            )
            return self._build_loader_from_content(
                base_id, {"objects": [], "views": []}
            )

        # 3. Load the full ontology (fall back to remote scene details if read-only)
        try:
            base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]
            loader: OntologyQueryable = backend.load_ontology(
                base_path, base_id=base_id
            )
            # 4. Build content dict from the loaded ontology filtered to matching codes
            content = _build_content(loader, list(all_obj_codes), list(all_vw_codes))
        except PermissionError:
            # Remote backend: load_ontology is not supported, build from scene details
            content = _build_content_from_remote_scenes(
                backend, base_id, scene_ids, list(all_obj_codes), list(all_vw_codes)
            )
        logger.info(
            "load_ontology_from_scenes: base_id=%s scenes=%d objects=%d views=%d",
            base_id,
            len(scene_ids),
            len(content.get("objects", [])),
            len(content.get("views", [])),
        )
        return self._build_loader_from_content(base_id, content)

    def load_ontology_from_codes(
        self,
        base_id: str,
        object_codes: list[str],
        *,
        view_codes: list[str] | None = None,
    ) -> OntologyLoader:
        """Load an ontology subset directly from object and view codes.

        1. Bulk-query the entity store when available.
        2. Fall back to remote scene details for backends without entity store.

        Args:
            base_id: Ontology base identifier.
            object_codes: Object codes to include.
            view_codes: Optional view codes to include.

        Returns:
            A new :class:`OntologyLoader` containing only the matching objects and views,
            with virtual actions injected.
        """
        backend: OntologyBackend = self._ontology_for(base_id)  # type: ignore[attr-defined]

        vw_codes = view_codes if view_codes is not None else []

        if hasattr(backend, "_entity_store"):
            store = backend._entity_store.sub_store(base_id)
            objs, _ = (
                store.search(
                    "objects",
                    codes=object_codes,
                    page=1,
                    page_size=max(len(object_codes), 1),
                )
                if object_codes
                else ([], 0)
            )
            vws, _ = (
                store.search(
                    "views",
                    codes=vw_codes,
                    page=1,
                    page_size=max(len(vw_codes), 1),
                )
                if vw_codes
                else ([], 0)
            )
            content: dict[str, Any] = {"objects": objs, "views": vws}
        else:
            content = _build_content_from_remote_scenes(
                backend, base_id, ["-1"], object_codes, vw_codes
            )
        logger.info(
            "load_ontology_from_codes: base_id=%s objects=%d views=%d",
            base_id,
            len(content.get("objects", [])),
            len(content.get("views", [])),
        )
        return self._build_loader_from_content(base_id, content)

    def search_and_load(
        self,
        base_id: str,
        keyword: str,
        *,
        type_filter: str = "object",
        top_k: int = 3,
    ) -> OntologyLoader:
        """Semantic search for objects or actions, then load the matching ontology subset.

        Args:
            base_id: Ontology base identifier.
            keyword: Search keyword for vector/semantic matching.
            type_filter: ``"object"`` to search object metadata, ``"action"`` to search
                action metadata.
            top_k: Maximum number of search results.

        Returns:
            A new :class:`OntologyLoader` containing the matched objects (and their
            owning objects for action matches), with virtual actions injected.

        Raises:
            ValueError: If *type_filter* is not ``"object"`` or ``"action"``.
        """
        if type_filter not in ("object", "action"):
            raise ValueError(
                f"type_filter must be 'object' or 'action', got {type_filter!r}"
            )

        if type_filter == "object":
            result = self.search_ontology(  # type: ignore[attr-defined]
                base_id,
                scene_ids=["-1"],
                keyword=keyword,
                search_scope="metadata",
                ontology_type=["object"],
                limit=top_k,
            )
            codes = [
                h.get("termCode", "")
                for h in result.get("metadata", [])
                if h.get("termCode")
            ]
            logger.info(
                "search_and_load: object search keyword=%r hits=%d",
                keyword,
                len(codes),
            )
        else:
            result = self.search_ontology(  # type: ignore[attr-defined]
                base_id,
                scene_ids=["-1"],
                keyword=keyword,
                search_scope="metadata",
                ontology_type=["action"],
                limit=top_k,
            )
            # Deduplicate by belongObjectCode
            codes_set: dict[str, None] = {}
            for h in result.get("metadata", []):
                boc = h.get("belongObjectCode")
                if boc:
                    codes_set[boc] = None
            codes = list(codes_set.keys())
            logger.info(
                "search_and_load: action search keyword=%r hits=%d objects=%d",
                keyword,
                len(result.get("metadata", [])),
                len(codes),
            )

        if not codes:
            logger.info("search_and_load: no matches for keyword=%r", keyword)
            return self._build_loader_from_content(
                base_id, {"objects": [], "views": []}
            )

        return self.load_ontology_from_codes(base_id, codes)

    # ── Internal ────────────────────────────────────────────────────────────

    def _build_loader_from_content(
        self,
        base_id: str,
        content: dict[str, Any],
    ) -> OntologyLoader:
        """Build a new :class:`OntologyLoader` from a content dict and inject virtual actions.

        Args:
            base_id: Ontology base identifier.
            content: A dict with ``"objects"`` and ``"views"`` keys in the format
                :meth:`OntologyLoader.load_from_content` expects.

        Returns:
            A fully configured :class:`OntologyLoader` with virtual actions injected.
        """
        loader = OntologyLoader()
        loader.load_from_content(content)
        try:
            self.inject_virtual_actions(base_id, loader)  # type: ignore[attr-defined]
        except PermissionError:
            # Remote backends may not support execution (execution="none")
            logger.debug(
                "_build_loader_from_content: inject_virtual_actions skipped "
                "for base_id=%r (execution unavailable)",
                base_id,
            )
        return loader


# ── module-level helpers ────────────────────────────────────────────────────


def _build_content(
    loader: OntologyQueryable,
    object_codes: list[str],
    view_codes: list[str],
) -> dict[str, Any]:
    """Build a content dict from an already-loaded ontology, filtered by codes.

    Args:
        loader: An already-loaded :class:`OntologyQueryable`.
        object_codes: Object codes to include.
        view_codes: View codes to include.

    Returns:
        A dict ``{"objects": [...], "views": [...], "functions": {...}}`` suitable for
        :meth:`OntologyLoader.load_from_content`.
    """
    objects: list[dict[str, Any]] = []
    for code in object_codes:
        cls = loader._classes.get(code)
        if cls is not None:
            objects.append(asdict(cls))

    views: list[dict[str, Any]] = []
    raw_views: dict[str, dict[str, Any]] = getattr(loader, "_views", None) or {}
    for vc in view_codes:
        view_data = raw_views.get(vc)
        if view_data is not None:
            views.append(view_data)

    functions: dict[str, dict[str, Any]] = getattr(loader, "_functions", None) or {}
    return {"objects": objects, "views": views, "functions": functions}


def _build_content_from_remote_scenes(
    backend: Any,
    base_id: str,
    scene_ids: list[str],
    object_codes: list[str],
    view_codes: list[str],
) -> dict[str, Any]:
    """Build a content dict from remote scene details.

    1. queryOntologies per code → discover sceneId for each object/view
    2. Merge + deduplicate sceneIds
    3. sceneDetails per unique sceneId with grouped codes

    Used as fallback when ``backend.load_ontology()`` is not available
    (e.g. :class:`RemoteOntologyBackend`).
    """
    all_objects: list[dict[str, Any]] = []
    all_views: list[dict[str, Any]] = []

    obj_code_set = set(object_codes)
    vw_code_set = set(view_codes)

    # ── Step 1: discover sceneId for each code ──
    # sceneId → {objects: set, views: set}
    scene_map: dict[str, dict[str, set[str]]] = {}

    def _resolve_by_code(code: str, query_type: str) -> str | None:
        """One queryOntologies call per code to find its sceneId."""
        try:
            result = backend.query_ontologies_by_scene(
                "-1",
                base_id=base_id,
                page=1,
                page_size=20,
                keyword=code,
                type=query_type,
            )
        except Exception:
            logger.debug(
                "_build_content_from_remote_scenes: queryOntologies failed for %s",
                code,
                exc_info=True,
            )
            return None
        data = result.get("data", {}) if isinstance(result, dict) else {}
        items: list[dict[str, Any]] = (
            data.get("objects", []) or data.get("views", []) or []
        )
        for item in items:
            item_code = (
                item.get("objectCode")
                or item.get("viewCode")
                or item.get("code")
                or item.get("object_code", "")
            )
            if item_code == code:
                return str(item.get("_sceneId") or item.get("sceneId") or "")
        return None

    for code in object_codes:
        sid = _resolve_by_code(code, "object")
        if sid:
            scene_map.setdefault(sid, {"objects": set(), "views": set()})
            scene_map[sid]["objects"].add(code)

    for code in view_codes:
        sid = _resolve_by_code(code, "view")
        if sid:
            scene_map.setdefault(sid, {"objects": set(), "views": set()})
            scene_map[sid]["views"].add(code)

    # ── Step 2: sceneDetails per unique sceneId ──
    for sid, codes in scene_map.items():
        obj_list = list(codes["objects"])
        vw_list = list(codes["views"])
        try:
            detail = backend.get_scene_details(
                sid,
                base_id=base_id,
                object_code=obj_list or None,
                view_code=vw_list or None,
            )
        except Exception:
            logger.debug(
                "_build_content_from_remote_scenes: sceneDetails failed for scene %s",
                sid,
                exc_info=True,
            )
            continue

        for obj in detail.get("objects", []) or []:
            obj_code = str(obj.get("object_code") or "")
            if obj_code in obj_code_set:
                all_objects.append(obj)

        for vw in detail.get("views", []) or []:
            vid = str(vw.get("view_id") or vw.get("view_code") or "")
            if vid in vw_code_set:
                all_views.append(vw)

    functions = _generate_remote_function_configs(all_objects)
    return {"objects": all_objects, "views": all_views, "functions": functions}


def _normalize_remote_properties(props: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert remote ``properties`` (camelCase) to ``fields`` (snake_case)."""
    fields: list[dict[str, Any]] = []
    for p in props:
        fields.append(
            {
                "field_code": p.get("propertyCode", ""),
                "field_name": p.get("propertyName", ""),
                "field_type": p.get("propertyType") or p.get("dataType") or "STRING",
                "description": p.get("propertyDesc") or p.get("description", ""),
                "is_primary_key": bool(p.get("isPrimaryKey", False)),
                "db_id": p.get("dbId", ""),
                "is_nullable": bool(p.get("isNullable", True)),
            }
        )
    return fields


def _normalize_remote_actions(
    actions: list[dict[str, Any]], object_code: str
) -> list[dict[str, Any]]:
    """Convert remote ``actions`` (camelCase) to the format expected by
    :meth:`OntologyLoader.load_from_content`."""
    result: list[dict[str, Any]] = []
    for a in actions:
        result.append(
            {
                "action_code": a.get("actionCode", ""),
                "action_name": a.get("actionName", ""),
                "description": a.get("actionDesc") or a.get("description", ""),
                "action_type": a.get("actionType", "query"),
                "object_code": object_code,
                "params": _normalize_remote_params(
                    a.get("params") or a.get("parameters") or []
                ),
                "output_fields": a.get("outputFields") or [],
                "script": a.get("script"),
                "function_refs": a.get("functionRefs") or [],
                "request_url": a.get("requestUrl"),
                "request_method": a.get("requestMethod"),
            }
        )
    return result


def _normalize_remote_params(params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert remote action params (camelCase) to snake_case."""
    result: list[dict[str, Any]] = []
    for p in params:
        result.append(
            {
                "param_code": p.get("paramCode", ""),
                "param_name": p.get("paramName", ""),
                "param_type": p.get("paramType", "STRING"),
                "description": p.get("paramDesc") or p.get("description", ""),
                "is_required": bool(p.get("isRequired", False)),
                "default_value": p.get("defaultValue"),
            }
        )
    return result


def _generate_remote_function_configs(
    objects: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Generate minimal OpenAPI function configs from remote action definitions.

    For remote actions that have ``request_url`` (but no ``script``), builds
    an OpenAPI 3.0-style function config so that ``Action._execute_api()`` can
    resolve ``servers[0].url`` and ``paths`` without needing a local OWL file.
    """
    functions: dict[str, dict[str, Any]] = {}
    action_count = 0
    generated_count = 0
    skipped_no_url = 0
    skipped_has_script = 0
    skipped_no_path = 0
    for obj in objects:
        for a in obj.get("actions", []) or []:
            action_count += 1
            script = a.get("script")
            request_url = a.get("request_url")
            if script:
                skipped_has_script += 1
                continue
            if not request_url:
                skipped_no_url += 1
                continue

            function_refs: list[str] = list(a.get("function_refs", []) or [])
            if not function_refs:
                function_code = _build_generated_function_code(a.get("action_code", ""))
                function_refs = [function_code]
                a["function_refs"] = function_refs
                generated_count += 1
                logger.debug(
                    "_generate_remote_function_configs: generated function_refs=%s "
                    "for action_code=%r request_url=%r",
                    function_refs,
                    a.get("action_code"),
                    request_url,
                )

            server_url, path = _split_request_url(request_url)
            if not path:
                skipped_no_path += 1
                continue

            method = (a.get("request_method") or "POST").lower()
            action_name = a.get("action_name") or a.get("action_code", "")

            config: dict[str, Any] = {
                "openapi": "3.0.3",
                "info": {"title": action_name, "version": "1.0.0"},
                "paths": {path: {method: {"summary": a.get("description", "")}}},
            }
            if server_url:
                config["servers"] = [{"url": server_url}]

            for fn_code in function_refs:
                functions.setdefault(fn_code, config)

    logger.debug(
        "_generate_remote_function_configs: total_actions=%d generated_refs=%d "
        "skipped(no_url=%d has_script=%d no_path=%d) "
        "total_functions=%d",
        action_count,
        generated_count,
        skipped_no_url,
        skipped_has_script,
        skipped_no_path,
        len(functions),
    )

    return functions


def _split_request_url(request_url: str) -> tuple[str, str]:
    """Split a request URL into server base URL and path.

    Returns:
        tuple[str, str]: (server_url, path)
    """
    if not request_url:
        return "", ""
    parsed = urlsplit(request_url)
    if parsed.scheme and parsed.netloc:
        base = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/"
        return base, path
    return "", request_url


def _build_generated_function_code(action_code: str) -> str:
    """Generate a stable function code from an action code."""
    fragment = re.sub(r"[^0-9A-Za-z_]+", "_", action_code).strip("_")
    if not fragment:
        fragment = "action"
    if fragment[0].isdigit():
        fragment = f"n_{fragment}"
    return f"fn_{fragment}"
