"""SceneServiceMixin — enforces "no orphan objects/views" invariant via auto-managed default scene."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.adapters.registry_sync import (
    obj_camel_to_owl,
    registry_sync_delete,
    registry_sync_upsert,
    view_camel_to_registry,
)
from datacloud_platform.backends._contracts import _HasOntologyBackend

logger = logging.getLogger(__name__)


class SceneServiceMixin:
    """Mixin enforcing "no orphan objects/views" invariant via auto-managed default scene.

    All object/view mutations that could create orphans are routed through this mixin.
    The default scene (scene_code="default") is lazily created when the first orphan
    appears and automatically destroyed when it becomes empty and no orphans exist.
    """

    DEFAULT_SCENE_CODE: str = "20"
    DEFAULT_SCENE_NAME: str = "平台能力"

    # ── Default scene lifecycle ──

    def _ensure_default_scene(self: _HasOntologyBackend, base_id: str) -> str:
        """Lazily get or create the default scene, return its scene_id. Idempotent.

        On first creation, automatically imports any pre-existing orphan objects/views
        (e.g. from ``_seed_from_owl_path`` at base creation) into the default scene.

        Migrates legacy default scene (code="default") → current code ("20").
        """
        backend = self._ontology_for(base_id)
        scenes = backend.list_scenes(base_id)
        for scene in scenes:
            if scene.get("scene_code") == SceneServiceMixin.DEFAULT_SCENE_CODE:
                return scene["scene_id"]  # type: ignore[no-any-return]

        # Migration: rename legacy default scene (code="default") to current code
        for scene in scenes:
            if scene.get("scene_code") == "default":
                scene_id = scene["scene_id"]
                backend.update_scene(base_id, scene_id, {
                    "scene_name": SceneServiceMixin.DEFAULT_SCENE_NAME,
                    "scene_code": SceneServiceMixin.DEFAULT_SCENE_CODE,
                    "scene_desc": scene.get("scene_desc", ""),
                })
                logger.info(
                    "_ensure_default_scene: migrated legacy default scene=%s "
                    "(code='default' → '%s', name='%s')",
                    scene_id,
                    SceneServiceMixin.DEFAULT_SCENE_CODE,
                    SceneServiceMixin.DEFAULT_SCENE_NAME,
                )
                return scene_id

        # Create default scene (first time)
        result = backend.create_scene(
            base_id,
            {
                "scene_name": SceneServiceMixin.DEFAULT_SCENE_NAME,
                "scene_code": SceneServiceMixin.DEFAULT_SCENE_CODE,
                "scene_desc": "",
            },
        )
        scene_id: str = (
            result.get("scene_id", "")
            if isinstance(result, dict)
            else str(getattr(result, "scene_id", ""))
        )
        logger.info(
            "_ensure_default_scene: created default scene=%s for base_id=%s",
            scene_id,
            base_id,
        )

        # On first creation, import any pre-existing orphans (e.g. startup OWL load)
        self._import_orphans_to_default(base_id)  # type: ignore[attr-defined]
        return scene_id

    def _get_default_scene_id(self: _HasOntologyBackend, base_id: str) -> str | None:
        """Return default scene's scene_id, or None if it doesn't exist."""
        backend = self._ontology_for(base_id)
        scenes = backend.list_scenes(base_id)
        for scene in scenes:
            if scene.get("scene_code") == SceneServiceMixin.DEFAULT_SCENE_CODE:
                return scene["scene_id"]  # type: ignore[no-any-return]
        return None

    def _maybe_destroy_default_scene(self: _HasOntologyBackend, base_id: str) -> None:
        """Destroy default scene if it's empty AND no orphans exist (all objects have a scene)."""
        default_id = self._get_default_scene_id(base_id)  # type: ignore[attr-defined]
        if default_id is None:
            return
        backend = self._ontology_for(base_id)
        obj_codes, vw_codes = backend.get_scene_members(base_id, default_id)
        if obj_codes or vw_codes:
            return
        orphan_obj, orphan_vw = self._collect_orphans(base_id)  # type: ignore[attr-defined]
        if orphan_obj or orphan_vw:
            backend.add_scene_members(base_id, default_id, orphan_obj, orphan_vw)
            logger.info(
                "_maybe_destroy_default_scene: absorbed %d objects + %d views into default scene=%s",
                len(orphan_obj),
                len(orphan_vw),
                default_id,
            )
            return
        backend.delete_scene(base_id, default_id)
        logger.info(
            "_maybe_destroy_default_scene: destroyed empty default scene for base_id=%s",
            base_id,
        )

    # ── Orphan detection ──

    def _collect_orphans(
        self: _HasOntologyBackend, base_id: str
    ) -> tuple[list[str], list[str]]:
        """Return (orphan_object_codes, orphan_view_codes) as sorted lists."""
        backend = self._ontology_for(base_id)
        try:
            base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]
            loader = backend.load_ontology(base_path)
        except (PermissionError, FileNotFoundError):
            logger.debug(
                "_collect_orphans: cannot load ontology for base_id=%s", base_id
            )
            return ([], [])

        all_object_codes: set[str] = set(loader._classes.keys())
        all_view_codes: set[str] = set()
        if loader._views is not None:
            all_view_codes.update(loader._views.keys())

        assigned_objects: set[str] = set()
        assigned_views: set[str] = set()
        scenes = backend.list_scenes(base_id)
        for scene in scenes:
            obj_codes, vw_codes = backend.get_scene_members(base_id, scene["scene_id"])
            assigned_objects.update(obj_codes)
            assigned_views.update(vw_codes)

        orphan_objects = sorted(all_object_codes - assigned_objects)
        orphan_views = sorted(all_view_codes - assigned_views)
        return (orphan_objects, orphan_views)

    def _has_orphans(self: _HasOntologyBackend, base_id: str) -> bool:
        """Check if any object/view exists that belongs to no scene at all."""
        orphan_obj, orphan_vw = self._collect_orphans(base_id)  # type: ignore[attr-defined]
        if orphan_obj or orphan_vw:
            logger.debug(
                "_has_orphans: base_id=%s orphan_objects=%d orphan_views=%d",
                base_id,
                len(orphan_obj),
                len(orphan_vw),
            )
            return True
        return False

    def _import_orphans_to_default(self: _HasOntologyBackend, base_id: str) -> None:
        """Find objects/views not in any scene and add them to the default scene.

        Called once when the default scene is first created, to absorb any
        pre-existing orphans (e.g. from ``_seed_from_owl_path`` at base creation).
        """
        orphan_obj, orphan_vw = self._collect_orphans(base_id)  # type: ignore[attr-defined]
        if orphan_obj or orphan_vw:
            default_id = self._get_default_scene_id(base_id)  # type: ignore[attr-defined]
            if default_id is None:
                return
            backend = self._ontology_for(base_id)
            backend.add_scene_members(base_id, default_id, orphan_obj, orphan_vw)
            logger.info(
                "_import_orphans_to_default: imported %d objects + %d views "
                "into default scene=%s for base_id=%s",
                len(orphan_obj),
                len(orphan_vw),
                default_id,
                base_id,
            )

    def _seed_from_owl_path(
        self: _HasOntologyBackend, base_id: str, owl_path: str
    ) -> dict[str, int]:
        """Parse OWL from a directory path and persist, then absorb into default scene.

        This is the Platform-layer replacement for the old ``_load_owl_if_configured``
        (which bypassed the Platform and created orphans).  Called by ``create_base``
        when ``backend_config.ontology.owl_path`` is configured.
        """
        from pathlib import Path

        backend = self._ontology_for(base_id)
        base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]

        parsed = backend.parse_owl(Path(owl_path))
        counts: dict[str, int] = backend.batch_import_ontology(
            base_path,
            parsed.objects,
            parsed.views,
            parsed.relations,
            parsed.actions,
            parsed.dbsources,
        )

        self._ensure_default_scene(base_id)  # type: ignore[attr-defined]

        logger.info(
            "_seed_from_owl_path: base_id=%s owl_path=%s "
            "objects=%d views=%d relations=%d actions=%d dbsources=%d",
            base_id,
            owl_path,
            counts.get("objects", 0),
            counts.get("views", 0),
            counts.get("relations", 0),
            counts.get("actions", 0),
            counts.get("dbsources", 0),
        )
        return counts

    def create_object_with_scene(
        self: _HasOntologyBackend, base_id: str, obj: Any, scene_id: str = ""
    ) -> Any:
        """Create object. If scene_id is empty, auto-add to default scene."""
        backend = self._ontology_for(base_id)
        result = backend.create_object(base_id, obj)
        result_dict: dict[str, Any] = result if isinstance(result, dict) else {}
        object_code: str = (
            result_dict.get("objectCode") or result_dict.get("object_code", "")
            if result_dict
            else str(
                getattr(result, "objectCode", "") or getattr(result, "object_code", "")
            )
        )
        if not scene_id:
            scene_id = self._ensure_default_scene(base_id)  # type: ignore[attr-defined]
        if object_code:
            backend.add_scene_members(base_id, scene_id, [object_code], [])
        if object_code and result_dict:
            base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]
            registry_sync_upsert(
                base_path,
                "objects",
                "object_code",
                object_code,
                obj_camel_to_owl(result_dict),
            )
        logger.info("create_object_with_scene: %s -> scene %s", object_code, scene_id)
        return result

    def create_view_with_scene(
        self: _HasOntologyBackend, base_id: str, view: Any, scene_id: str = ""
    ) -> Any:
        """Create view. If scene_id is empty, auto-add to default scene."""
        backend = self._ontology_for(base_id)
        result = backend.create_view(base_id, view)
        result_dict: dict[str, Any] = result if isinstance(result, dict) else {}
        view_code: str = (
            result_dict.get("viewCode")
            or result_dict.get("view_code")
            or result_dict.get("view_id", "")
            if result_dict
            else str(
                getattr(result, "viewCode", "")
                or getattr(result, "view_code", "")
                or getattr(result, "view_id", "")
            )
        )
        if not scene_id:
            scene_id = self._ensure_default_scene(base_id)  # type: ignore[attr-defined]
        if view_code:
            backend.add_scene_members(base_id, scene_id, [], [view_code])
        if view_code and result_dict:
            base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]
            registry_sync_upsert(
                base_path,
                "views",
                "view_id",
                view_code,
                view_camel_to_registry(result_dict),
            )
        logger.info("create_view_with_scene: %s -> scene %s", view_code, scene_id)
        return result

    def delete_object_from_all_scenes(
        self: _HasOntologyBackend, base_id: str, object_code: str
    ) -> None:
        """Delete object, removing it from ALL scenes first (including default)."""
        backend = self._ontology_for(base_id)
        backend.remove_object_from_all_scenes(base_id, object_code)
        backend.delete_object(base_id, object_code)
        base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]
        registry_sync_delete(base_path, "objects", "object_code", object_code)
        self._maybe_destroy_default_scene(base_id)  # type: ignore[attr-defined]
        logger.info("delete_object_from_all_scenes: %s deleted", object_code)

    def delete_view_from_all_scenes(
        self: _HasOntologyBackend, base_id: str, view_code: str
    ) -> None:
        """Delete view, removing it from ALL scenes first (including default)."""
        backend = self._ontology_for(base_id)
        backend.remove_view_from_all_scenes(base_id, view_code)
        backend.delete_view(base_id, view_code)
        base_path = self._base_path_for(base_id)  # type: ignore[attr-defined]
        registry_sync_delete(base_path, "views", "view_id", view_code)
        self._maybe_destroy_default_scene(base_id)  # type: ignore[attr-defined]
        logger.info("delete_view_from_all_scenes: %s deleted", view_code)

    def remove_object_from_scene_safe(
        self: _HasOntologyBackend, base_id: str, scene_id: str, object_code: str
    ) -> None:
        """Remove object from scene. If this was its last scene, move to default scene."""
        backend = self._ontology_for(base_id)
        backend.remove_scene_members(base_id, scene_id, [object_code], [])
        count = backend.get_object_scene_count(base_id, object_code)
        if count == 0:
            default_id = self._ensure_default_scene(base_id)  # type: ignore[attr-defined]
            backend.add_scene_members(base_id, default_id, [object_code], [])
            logger.debug(
                "remove_object_from_scene_safe: %s moved to default scene", object_code
            )

    def remove_view_from_scene_safe(
        self: _HasOntologyBackend, base_id: str, scene_id: str, view_code: str
    ) -> None:
        """Remove view from scene. If this was its last scene, move to default scene."""
        backend = self._ontology_for(base_id)
        backend.remove_scene_members(base_id, scene_id, [], [view_code])
        count = backend.get_view_scene_count(base_id, view_code)
        if count == 0:
            default_id = self._ensure_default_scene(base_id)  # type: ignore[attr-defined]
            backend.add_scene_members(base_id, default_id, [], [view_code])
            logger.debug(
                "remove_view_from_scene_safe: %s moved to default scene", view_code
            )

    def delete_scene_with_migration(
        self: _HasOntologyBackend, base_id: str, scene_id: str
    ) -> None:
        """Delete scene. Members migrate to default scene. Cannot delete default scene directly."""
        backend = self._ontology_for(base_id)
        scenes = backend.list_scenes(base_id)
        scene_info: dict[str, Any] | None = None
        for s in scenes:
            if s["scene_id"] == scene_id:
                scene_info = s
                break
        if scene_info is None:
            logger.debug(
                "delete_scene_with_migration: scene %s not found, nothing to do",
                scene_id,
            )
            return
        if scene_info.get("scene_code") == SceneServiceMixin.DEFAULT_SCENE_CODE:
            raise ValueError("不能直接删除默认场景")

        obj_codes, vw_codes = backend.get_scene_members(base_id, scene_id)
        if obj_codes or vw_codes:
            default_id = self._ensure_default_scene(base_id)  # type: ignore[attr-defined]
            backend.add_scene_members(base_id, default_id, obj_codes, vw_codes)
            backend.remove_scene_members(base_id, scene_id, obj_codes, vw_codes)

        backend.delete_scene(base_id, scene_id)
        self._maybe_destroy_default_scene(base_id)  # type: ignore[attr-defined]
        logger.info("delete_scene_with_migration: scene %s deleted", scene_id)
