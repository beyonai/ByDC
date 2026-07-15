"""Scene management — list, query, CRUD, reverse lookup, member management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from datacloud_platform.adapters.data_adapter._base import (
    DataCloudDataBackendBase,
)

logger = logging.getLogger(__name__)


class SceneMixin(DataCloudDataBackendBase):
    """Scene management — list, query, CRUD, reverse lookup, member management."""

    # ── Scene management ──────────────────────────────────────────────────

    def _ensure_scenes_loaded(self) -> dict[str, dict[str, Any]]:
        """Load scenes index, invalidating cache on mtime change (cross-process safe).

        On first load, migrates legacy index entries that lack ``base_id`` and
        ``scene_code`` fields (written by the old ``_save_scenes``).  The
        full scene data is read from the ``EntityStore`` to backfill these
        fields, then the updated index is persisted.
        """
        if self._entity_store is None:
            self._scenes = {}
            return self._scenes
        current_version = self._entity_store.storage_version("scenes")
        if self._scenes is not None and self._scenes_version == current_version:
            return self._scenes
        try:
            self._scenes = dict(self._entity_store.load_index("scenes"))
            self._scenes_version = current_version
            self._reverse_index_built = False

            # Migrate legacy index entries (missing base_id / scene_code).
            # Also normalise field names so downstream code that expects
            # ``scene_id`` / ``scene_name`` doesn't crash on index-loaded
            # dicts that use ``code`` / ``name``.
            need_migration = self._scenes and not all(
                "base_id" in s for s in self._scenes.values()
            )
            if need_migration:
                migrated = 0
                for sid, scene in list(self._scenes.items()):
                    if "base_id" in scene and "scene_code" in scene:
                        continue
                    full = self._load_full_scene(sid)
                    if full is None:
                        continue
                    scene["base_id"] = full.get("base_id", "")
                    scene["scene_code"] = full.get("scene_code", "")
                    scene.setdefault("scene_id", scene.get("code", sid))
                    scene.setdefault("scene_name", scene.get("name", ""))
                    migrated += 1
                if migrated:
                    self._save_scenes()
        except Exception:
            logger.warning("Failed to load scenes index", exc_info=True)
            self._scenes = {}
            self._scenes_version = ""
        return self._scenes

    def _ensure_reverse_index(self) -> None:
        """Build reverse index from _scenes: object_code → {scene_ids}."""
        if self._reverse_index_built:
            return
        self._object_scene_map = {}
        self._view_scene_map = {}
        for sid, scene in (self._scenes or {}).items():
            for code in scene.get("member_object_codes", []):
                self._object_scene_map.setdefault(code, set()).add(sid)
            for code in scene.get("member_view_codes", []):
                self._view_scene_map.setdefault(code, set()).add(sid)
        self._reverse_index_built = True

    def _save_scenes(self) -> None:
        """Persist in-memory scenes to EntityStore index atomically.

        Normalizes entries to the ``{code, name, shard, field_count, base_id, scene_code}``
        index format required by ``load_index``.

        ``base_id`` and ``scene_code`` are included in the index so that
        ``list_scenes(base_id)`` and ``_ensure_default_scene`` survive
        a process restart without requiring a full-scene load.

        Handles both full-scene dicts (``scene_id``/``scene_name``, from
        ``create_scene``) and index-loaded dicts (``code``/``name``, from
        ``load_index``) via fallback reads.
        """
        if self._scenes is None or self._entity_store is None:
            return
        normalized: dict[str, dict[str, Any]] = {}
        for sid, scene in self._scenes.items():
            normalized[sid] = {
                "code": scene.get("scene_id") or scene.get("code", sid),
                "name": scene.get("scene_name") or scene.get("name", ""),
                "shard": str(sid)[:2].lower(),
                "field_count": len(scene.get("member_object_codes", []))
                + len(scene.get("member_view_codes", [])),
                "base_id": scene.get("base_id", ""),
                "scene_code": scene.get("scene_code", ""),
            }
        self._entity_store.save_index("scenes", normalized)
        logger.info("Saved %d scenes to EntityStore", len(normalized))

    def _save_scene(self, scene_id: str, scene: dict[str, Any]) -> None:
        """Persist a single scene file and the index atomically."""
        if self._entity_store is not None:
            self._entity_store.save("scenes", scene_id, scene)
        self._save_scenes()

    def _delete_scene(self, scene_id: str) -> None:
        """Delete a single scene file and update the index."""
        if self._entity_store is not None:
            self._entity_store.delete("scenes", scene_id)
        self._save_scenes()

    def list_scenes(self, base_id: str) -> list[dict[str, Any]]:
        """Return all scenes under a base."""
        scenes = self._ensure_scenes_loaded()
        return [s for s in scenes.values() if s.get("base_id") == base_id]

    def query_scenes(self, base_id: str, keyword: str | None) -> list[dict[str, Any]]:
        """Query scenes with optional keyword filter on scene_name / scene_code."""
        all_scenes = self.list_scenes(base_id)
        if not keyword:
            return all_scenes
        kw = keyword.strip().lower()
        return [
            s
            for s in all_scenes
            if kw in str(s.get("scene_name", "")).lower()
            or kw in str(s.get("scene_code", "")).lower()
        ]

    def count_scenes(self, base_id: str, keyword: str | None) -> int:
        """Count scenes matching optional keyword filter."""
        return len(self.query_scenes(base_id, keyword))

    # ── Atomic ontology methods (used by get_scene_details) ──────────────

    def _load_full_scene(self, scene_id: str) -> dict[str, Any] | None:
        """Load full scene data from EntityStore (includes member lists)."""
        if self._entity_store is None:
            return None
        try:
            return self._entity_store.get("scenes", scene_id)
        except Exception:
            logger.warning(
                "Failed to load full scene %s from EntityStore", scene_id, exc_info=True
            )
            return None

    def get_scene_members(
        self, base_id: str, scene_id: str
    ) -> tuple[list[str], list[str]]:
        """Return (object_codes, view_codes) for a scene — pure metadata query.

        On a cold start the in-memory index only has summary fields
        (``code``, ``name``, ``shard``, ``field_count``, ``base_id``,
        ``scene_code``).  When member data is missing we load the full
        scene from the ``EntityStore``, merge it into the in-memory dict,
        and then return the members.  Subsequent calls use the cached copy.

        Args:
            base_id: Base / project identifier.
            scene_id: Target scene ID.

        Returns:
            Tuple of (member_object_codes, member_view_codes). Empty lists if scene
            not found.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            return ([], [])

        # Fast path: member data already loaded (in-process create/update/add_members)
        if "member_object_codes" in scene or "member_view_codes" in scene:
            return (
                list(scene.get("member_object_codes", [])),
                list(scene.get("member_view_codes", [])),
            )

        # Cold-start path: index lacks member data → load full scene from store
        full = self._load_full_scene(scene_id)
        if full is not None:
            # Merge into in-memory dict so subsequent calls hit the fast path.
            # The full scene carries all fields (base_id, scene_code, members, etc.).
            scenes[scene_id] = full
            return (
                list(full.get("member_object_codes", [])),
                list(full.get("member_view_codes", [])),
            )

        return ([], [])

    def extract_objects_detail(
        self, object_codes: list[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract ObjectType JSON for each code — stub (shadowed by OntologyBackendMixin)."""
        _ = object_codes, base_id
        return []

    def extract_views_detail(
        self, view_codes: list[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract View JSON for each code — stub (shadowed by OntologyBackendMixin)."""
        _ = view_codes, base_id
        return []

    def extract_relations(
        self, object_codes_set: set[str], *, base_id: str = ""
    ) -> list[dict[str, Any]]:
        """Extract bidirectional Relation JSON — stub (shadowed by OntologyBackendMixin)."""
        _ = object_codes_set, base_id
        return []

    def get_term_scope_info(self, base_id: str, object_code: str) -> dict[str, Any]:
        """Return {library_id, scene_id} identifying which scene contains object_code.

        Searches all scenes under *base_id* for one that lists *object_code* as a member.
        Returns the first match found.

        Args:
            base_id: Base / project identifier.
            object_code: Object code to look up.

        Returns:
            Dict with ``library_id`` (str) and ``scene_id`` (str, empty if not found).
        """
        scenes = self._ensure_scenes_loaded()
        for scene in scenes.values():
            if scene.get("base_id") != base_id:
                continue
            if object_code in scene.get("member_object_codes", []):
                return {
                    "library_id": "PERSONAL_LIB",
                    "scene_id": scene.get("scene_id", ""),
                }
        return {"library_id": "PERSONAL_LIB", "scene_id": ""}

    def get_scene_details(
        self,
        scene_id: str,
        *,
        base_id: str = "",
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get scene details — stub (shadowed by OntologyBackendMixin)."""
        _ = scene_id, base_id, view_code, object_code
        return {}

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
        ext_property_filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query ontologies — stub (shadowed by OntologyBackendMixin)."""
        _ = (
            scene_id,
            base_id,
            page,
            page_size,
            keyword,
            type,
            owner_type,
            user_code,
            cross_scene,
            ext_property_filters,
        )
        return {}

    def get_base_details(
        self,
        *,
        base_id: str = "",
        view_code: list[str] | None = None,
        object_code: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get comprehensive base-level detail — stub (shadowed by OntologyBackendMixin)."""
        _ = base_id, view_code, object_code
        return {}

    def get_object_subtree(
        self,
        object_code: str,
        *,
        base_id: str = "",
    ) -> dict[str, Any]:
        """Get a single object's full subtree — stub (shadowed by OntologyBackendMixin)."""
        _ = object_code, base_id
        return {}

    # ── Scene CRUD ────────────────────────────────────────────────────────

    def _generate_scene_id(self) -> str:
        """Generate a unique scene ID (snowflake)."""
        from datacloud_platform.base_entry import generate_snowflake

        return generate_snowflake()

    def create_scene(self, base_id: str, scene: Any) -> dict[str, Any]:
        """Create a scene (grouping container) with EntityStore persistence.

        Args:
            base_id: Base / project identifier.
            scene: Scene-like object or dict with scene_name, scene_code, scene_desc.
                   scene_id is always auto-generated; scene_code defaults to scene_name.
        """
        scenes = self._ensure_scenes_loaded()

        # Extract fields from dict or object
        if isinstance(scene, dict):
            scene_name = scene.get("scene_name", scene.get("sceneName", ""))
            scene_code = scene.get("scene_code", scene.get("sceneCode"))
            scene_desc = scene.get("scene_desc", scene.get("sceneDesc"))
        else:
            scene_name = getattr(scene, "scene_name", "")
            scene_code = getattr(scene, "scene_code", None)
            scene_desc = getattr(scene, "scene_desc", None)

        scene_id = self._generate_scene_id()
        scene_code = scene_code or scene_name

        # 幂等：scene_code + base_id 已存在时返回已有场景（不重复创建）
        for _sid, _s in scenes.items():
            if _s.get("scene_code") == scene_code and _s.get("base_id") == base_id:
                logger.info(
                    "Scene with scene_code=%r already exists (scene_id=%s), skipping create",
                    scene_code,
                    _sid,
                )
                return _s

        if scene_id in scenes:
            raise ValueError(f"Scene already exists: {scene_id}")

        new_scene: dict[str, Any] = {
            "scene_id": scene_id,
            "scene_name": scene_name,
            "scene_code": scene_code,
            "scene_desc": scene_desc,
            "base_id": base_id,
            "member_object_codes": [],
            "member_view_codes": [],
        }
        scenes[scene_id] = new_scene
        self._save_scene(scene_id, new_scene)
        logger.info(
            "Created scene: base_id=%s scene_id=%s scene_code=%s",
            base_id,
            scene_id,
            scene_code,
        )
        self._invoke_sync_hook(
            "on_create",
            "SCENE",
            resource_code=scene_id,
            resource_name=scene_name,
            resource_desc=scene_desc or "",
            base_code=base_id,
        )
        return new_scene

    def update_scene(self, base_id: str, scene_id: str, updates: Any) -> dict[str, Any]:
        """Update scene metadata.

        Args:
            base_id: Base / project identifier.
            scene_id: Target scene ID.
            updates: Dict or object with scene_name / scene_desc fields to patch.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        if scene.get("base_id") != base_id:
            raise KeyError(f"Scene {scene_id} not owned by base {base_id}")

        if isinstance(updates, dict):
            if "scene_name" in updates or "sceneName" in updates:
                scene["scene_name"] = updates.get(
                    "scene_name", updates.get("sceneName")
                )
            if "scene_code" in updates or "sceneCode" in updates:
                scene["scene_code"] = updates.get(
                    "scene_code", updates.get("sceneCode")
                )
            if "scene_desc" in updates or "sceneDesc" in updates:
                scene["scene_desc"] = updates.get(
                    "scene_desc", updates.get("sceneDesc")
                )
        else:
            if hasattr(updates, "scene_name") and updates.scene_name is not None:
                scene["scene_name"] = updates.scene_name
            if hasattr(updates, "scene_desc") and updates.scene_desc is not None:
                scene["scene_desc"] = updates.scene_desc

        self._save_scene(scene_id, scene)
        logger.info("Updated scene: base_id=%s scene_id=%s", base_id, scene_id)
        self._invoke_sync_hook(
            "on_update",
            "SCENE",
            resource_code=scene_id,
            resource_name=scene.get("scene_name", ""),
            resource_desc=scene.get("scene_desc", ""),
            base_code=base_id,
        )
        return scene

    def delete_scene(self, base_id: str, scene_id: str) -> None:
        """Delete a scene — does NOT delete member resources.

        Only removes the grouping container. Member objects/views are unaffected.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            return
        if scene.get("base_id") != base_id:
            return
        del scenes[scene_id]
        self._delete_scene(scene_id)
        logger.info("Deleted scene: base_id=%s scene_id=%s", base_id, scene_id)
        self._invoke_sync_hook(
            "on_delete",
            "SCENE",
            resource_code=scene_id,
            base_code=base_id,
        )

    # ── Scene reverse-lookup queries ────────────────────────────────────────

    def get_object_scene_count(self, base_id: str, object_code: str) -> int:
        """Return how many scenes this object belongs to."""
        self._ensure_scenes_loaded()
        self._ensure_reverse_index()
        return len(self._object_scene_map.get(object_code, set()))

    def get_view_scene_count(self, base_id: str, view_code: str) -> int:
        """Return how many scenes this view belongs to."""
        self._ensure_scenes_loaded()
        self._ensure_reverse_index()
        return len(self._view_scene_map.get(view_code, set()))

    def remove_object_from_all_scenes(self, base_id: str, object_code: str) -> int:
        """Remove object from all scenes. Returns count of scenes removed from."""
        self._ensure_scenes_loaded()
        count = 0
        for scene_id, scene in list((self._scenes or {}).items()):
            if scene.get("base_id") != base_id:
                continue
            obj_set: set[str] = set(scene.get("member_object_codes", []))
            if object_code in obj_set:
                obj_set.discard(object_code)
                scene["member_object_codes"] = list(obj_set)
                self._save_scene(scene_id, scene)
                count += 1
        if count > 0:
            self._reverse_index_built = False
        return count

    def remove_view_from_all_scenes(self, base_id: str, view_code: str) -> int:
        """Remove view from all scenes. Returns count of scenes removed from."""
        self._ensure_scenes_loaded()
        count = 0
        for scene_id, scene in list((self._scenes or {}).items()):
            if scene.get("base_id") != base_id:
                continue
            view_set: set[str] = set(scene.get("member_view_codes", []))
            if view_code in view_set:
                view_set.discard(view_code)
                scene["member_view_codes"] = list(view_set)
                self._save_scene(scene_id, scene)
                count += 1
        if count > 0:
            self._reverse_index_built = False
        return count

    def get_scenes_containing_object(self, base_id: str, object_code: str) -> list[str]:
        """Return scene_ids that contain this object."""
        self._ensure_scenes_loaded()
        self._ensure_reverse_index()
        return list(self._object_scene_map.get(object_code, set()))

    # ── Scene member management ────────────────────────────────────────────

    def add_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> dict[str, Any]:
        """Add objects/views to a scene (idempotent — duplicates are ignored).

        Args:
            base_id: Base / project identifier.
            scene_id: Target scene ID.
            object_codes: Object codes to add as members.
            view_codes: View codes to add as members.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        if scene.get("base_id") != base_id:
            raise KeyError(f"Scene {scene_id} not owned by base {base_id}")

        existing_objs: set[str] = set(scene.get("member_object_codes", []))
        existing_views: set[str] = set(scene.get("member_view_codes", []))

        added_objs = [oc for oc in object_codes if oc not in existing_objs]
        added_views = [vc for vc in view_codes if vc not in existing_views]

        scene["member_object_codes"] = list(existing_objs | set(object_codes))
        scene["member_view_codes"] = list(existing_views | set(view_codes))
        self._save_scene(scene_id, scene)
        self._reverse_index_built = False
        # B-domain: fill term domain_codes after scene association (deferred sync)
        if hasattr(self, "_sync_entity_domains"):
            self._sync_entity_domains(base_id, scene_id, "object", added_objs)
            self._sync_entity_domains(base_id, scene_id, "view", added_views)
        logger.info(
            "Added scene members: scene_id=%s objects=%d views=%d (synced=%d+%d)",
            scene_id,
            len(added_objs),
            len(added_views),
            len(added_objs),
            len(added_views),
        )
        self._invoke_sync_hook(
            "on_update",
            "SCENE",
            resource_code=scene_id,
            resource_name=scene.get("scene_name", ""),
            resource_desc=scene.get("scene_desc", ""),
            base_code=base_id,
        )
        return scene

    def remove_scene_members(
        self,
        base_id: str,
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> dict[str, Any]:
        """Remove objects/views from a scene — does NOT delete resources.

        Args:
            base_id: Base / project identifier.
            scene_id: Target scene ID.
            object_codes: Object codes to remove from scene membership.
            view_codes: View codes to remove from scene membership.
        """
        scenes = self._ensure_scenes_loaded()
        scene = scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        if scene.get("base_id") != base_id:
            raise KeyError(f"Scene {scene_id} not owned by base {base_id}")

        obj_set: set[str] = set(scene.get("member_object_codes", []))
        view_set: set[str] = set(scene.get("member_view_codes", []))

        obj_set.difference_update(object_codes)
        view_set.difference_update(view_codes)

        scene["member_object_codes"] = list(obj_set)
        scene["member_view_codes"] = list(view_set)
        self._save_scene(scene_id, scene)
        self._reverse_index_built = False
        # B-domain: remove scene_id from term.domain_ids after scene disassociation
        if hasattr(self, "_remove_entity_domains"):
            self._remove_entity_domains(base_id, scene_id, "object", object_codes)
            self._remove_entity_domains(base_id, scene_id, "view", view_codes)
        logger.info(
            "Removed scene members: scene_id=%s objects=%d views=%d",
            scene_id,
            len(object_codes),
            len(view_codes),
        )
        self._invoke_sync_hook(
            "on_update",
            "SCENE",
            resource_code=scene_id,
            resource_name=scene.get("scene_name", ""),
            resource_desc=scene.get("scene_desc", ""),
            base_code=base_id,
        )
        return scene
