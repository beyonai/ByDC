"""SceneLoaderMixin — scene-based ontology loading for DatacloudPlatform.

Provides methods to load ontology subsets from scenes, object/view codes,
or keyword-based semantic search.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

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

        # 3. Load the full ontology
        base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]
        loader: OntologyQueryable = backend.load_ontology(base_path)

        # 4. Build content dict from the loaded ontology filtered to matching codes
        content = _build_content(loader, list(all_obj_codes), list(all_vw_codes))
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

        1. Load the full ontology once.
        2. Extract only the matching classes and views into a new loader.

        Args:
            base_id: Ontology base identifier.
            object_codes: Object codes to include.
            view_codes: Optional view codes to include.

        Returns:
            A new :class:`OntologyLoader` containing only the matching objects and views,
            with virtual actions injected.
        """
        backend: OntologyBackend = self._ontology_for(base_id)  # type: ignore[attr-defined]
        base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]
        loader: OntologyQueryable = backend.load_ontology(base_path)

        vw_codes = view_codes if view_codes is not None else []
        content = _build_content(loader, object_codes, vw_codes)
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
        self.inject_virtual_actions(base_id, loader)  # type: ignore[attr-defined]
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
        A dict ``{"objects": [...], "views": [...]}`` suitable for
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

    return {"objects": objects, "views": views}
