# mypy: ignore-errors
"""Tests for SceneServiceMixin — scene membership consistency architecture.

Tests the invariant: every object/view must belong to at least one scene.
Uses FakeSceneMembershipBackend (in-memory, fully isolated).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from datacloud_platform.mixins.scene_service import SceneServiceMixin

BASE_ID = "test_base"

# ── Fake Backend ────────────────────────────────────────────────────────────────


class FakeSceneMembershipBackend:
    """In-memory fake backing for SceneServiceMixin tests.

    Maintains _objects, _views, _scenes dicts and reverse indices
    (_object_scene_map, _view_scene_map) for efficient lookup.
    Every mutation updates both self._scenes and the reverse index.
    """

    def __init__(self) -> None:
        self._objects: dict[str, dict[str, Any]] = {}
        self._views: dict[str, dict[str, Any]] = {}
        self._scenes: dict[str, dict[str, Any]] = {}
        self._object_scene_map: dict[str, set[str]] = {}
        self._view_scene_map: dict[str, set[str]] = {}

    # -- Scene CRUD --

    def create_scene(self, base_id: str, scene: Any) -> dict[str, Any]:  # noqa: ARG002
        """Create a scene. Generates scene_id from scene_code or uuid."""
        if isinstance(scene, dict):
            scene_name = scene.get("scene_name", scene.get("sceneName", ""))
            scene_code = scene.get("scene_code", scene.get("sceneCode"))
            scene_desc = scene.get("scene_desc", scene.get("sceneDesc"))
        else:
            scene_name = getattr(scene, "scene_name", "")
            scene_code = getattr(scene, "scene_code", None)
            scene_desc = getattr(scene, "scene_desc", None)
        scene_id: str = scene_code or f"scene_{uuid4().hex[:12]}"
        if scene_id in self._scenes:
            raise ValueError(f"Scene already exists: {scene_id}")
        new_scene: dict[str, Any] = {
            "scene_id": scene_id,
            "scene_name": scene_name,
            "scene_code": scene_id,
            "scene_desc": scene_desc,
            "base_id": base_id,
            "member_object_codes": [],
            "member_view_codes": [],
        }
        self._scenes[scene_id] = new_scene
        return new_scene

    def delete_scene(self, base_id: str, scene_id: str) -> None:  # noqa: ARG002
        """Delete a scene and update reverse indices."""
        scene = self._scenes.pop(scene_id, None)
        if scene is None:
            return
        for obj_code in scene.get("member_object_codes", []):
            self._object_scene_map.get(obj_code, set()).discard(scene_id)
        for vw_code in scene.get("member_view_codes", []):
            self._view_scene_map.get(vw_code, set()).discard(scene_id)

    def list_scenes(self, base_id: str) -> list[dict[str, Any]]:  # noqa: ARG002
        """Return all scenes."""
        return list(self._scenes.values())

    def get_scene_members(
        self,
        base_id: str,
        scene_id: str,  # noqa: ARG002
    ) -> tuple[list[str], list[str]]:
        """Return (object_codes, view_codes) for a scene."""
        scene = self._scenes.get(scene_id)
        if scene is None:
            return ([], [])
        return (
            list(scene.get("member_object_codes", [])),
            list(scene.get("member_view_codes", [])),
        )

    def add_scene_members(
        self,
        base_id: str,  # noqa: ARG002
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> dict[str, Any]:
        """Add objects/views to a scene (idempotent). Updates reverse indices."""
        scene = self._scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        existing_objs: set[str] = set(scene.get("member_object_codes", []))
        existing_views: set[str] = set(scene.get("member_view_codes", []))
        scene["member_object_codes"] = list(existing_objs | set(object_codes))
        scene["member_view_codes"] = list(existing_views | set(view_codes))
        for obj_code in object_codes:
            self._object_scene_map.setdefault(obj_code, set()).add(scene_id)
        for vw_code in view_codes:
            self._view_scene_map.setdefault(vw_code, set()).add(scene_id)
        return scene

    def remove_scene_members(
        self,
        base_id: str,  # noqa: ARG002
        scene_id: str,
        object_codes: list[str],
        view_codes: list[str],
    ) -> dict[str, Any]:
        """Remove objects/views from a scene. Updates reverse indices."""
        scene = self._scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"Scene not found: {scene_id}")
        obj_set: set[str] = set(scene.get("member_object_codes", []))
        view_set: set[str] = set(scene.get("member_view_codes", []))
        obj_set.difference_update(object_codes)
        view_set.difference_update(view_codes)
        scene["member_object_codes"] = list(obj_set)
        scene["member_view_codes"] = list(view_set)
        for obj_code in object_codes:
            self._object_scene_map.get(obj_code, set()).discard(scene_id)
        for vw_code in view_codes:
            self._view_scene_map.get(vw_code, set()).discard(scene_id)
        return scene

    # -- Object CRUD --

    def create_object(self, base_id: str, obj: Any) -> dict[str, Any]:  # noqa: ARG002
        """Store object and return it."""
        if isinstance(obj, dict):
            object_code = obj.get("object_code", f"obj_{uuid4().hex[:8]}")
            object_name = obj.get("object_name", object_code)
            stored: dict[str, Any] = {
                "object_code": object_code,
                "object_name": object_name,
                "object_desc": obj.get("object_desc", ""),
            }
        else:
            object_code = getattr(obj, "object_code", f"obj_{uuid4().hex[:8]}")
            object_name = getattr(obj, "object_name", object_code)
            stored = {
                "object_code": object_code,
                "object_name": object_name,
                "object_desc": getattr(obj, "object_desc", ""),
            }
        self._objects[object_code] = stored
        return stored

    def delete_object(self, base_id: str, object_code: str) -> None:  # noqa: ARG002
        """Delete object from store."""
        self._objects.pop(object_code, None)

    # -- View CRUD --

    def create_view(self, base_id: str, view: Any) -> dict[str, Any]:  # noqa: ARG002
        """Store view and return it."""
        if isinstance(view, dict):
            view_code = view.get("view_code", f"view_{uuid4().hex[:8]}")
            view_name = view.get("view_name", view_code)
            stored_view: dict[str, Any] = {
                "view_code": view_code,
                "view_name": view_name,
            }
        else:
            view_code = getattr(view, "view_code", f"view_{uuid4().hex[:8]}")
            view_name = getattr(view, "view_name", view_code)
            stored_view = {
                "view_code": view_code,
                "view_name": view_name,
            }
        self._views[view_code] = stored_view
        return stored_view

    def delete_view(self, base_id: str, view_code: str) -> None:  # noqa: ARG002
        """Delete view from store."""
        self._views.pop(view_code, None)

    # -- Ontology loading --

    def load_ontology(self, base_path: Any) -> SimpleNamespace:  # noqa: ARG002
        """Return a SimpleNamespace with _classes and _views populated from internal store."""
        classes: dict[str, SimpleNamespace] = {}
        for code, obj in self._objects.items():
            classes[code] = SimpleNamespace(
                object_code=obj.get("object_code", code),
                object_name=obj.get("object_name", code),
                fields=[],
            )
        views_copy: dict[str, dict[str, Any]] = dict(self._views)
        return SimpleNamespace(
            _classes=classes,
            _relations=[],
            _views=views_copy,
        )

    def get_objects(
        self,
        loader: Any,
        base_id: str,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        """Return list of object summaries from loader._classes."""
        return [
            {"object_code": code, "object_name": cls.object_name}
            for code, cls in loader._classes.items()
        ]

    # -- Reverse-lookup queries --

    def get_object_scene_count(
        self,
        base_id: str,
        object_code: str,  # noqa: ARG002
    ) -> int:
        """Return how many scenes this object belongs to."""
        return len(self._object_scene_map.get(object_code, set()))

    def get_view_scene_count(
        self,
        base_id: str,
        view_code: str,  # noqa: ARG002
    ) -> int:
        """Return how many scenes this view belongs to."""
        return len(self._view_scene_map.get(view_code, set()))

    def remove_object_from_all_scenes(
        self,
        base_id: str,
        object_code: str,  # noqa: ARG002
    ) -> int:
        """Remove object from all scenes. Returns count of scenes removed from."""
        scene_ids = self._object_scene_map.pop(object_code, set())
        for sid in scene_ids:
            scene = self._scenes.get(sid)
            if scene is not None:
                scene["member_object_codes"] = [
                    c for c in scene.get("member_object_codes", []) if c != object_code
                ]
        return len(scene_ids)

    def remove_view_from_all_scenes(
        self,
        base_id: str,
        view_code: str,  # noqa: ARG002
    ) -> int:
        """Remove view from all scenes. Returns count of scenes removed from."""
        scene_ids = self._view_scene_map.pop(view_code, set())
        for sid in scene_ids:
            scene = self._scenes.get(sid)
            if scene is not None:
                scene["member_view_codes"] = [
                    c for c in scene.get("member_view_codes", []) if c != view_code
                ]
        return len(scene_ids)

    def get_scenes_containing_object(
        self,
        base_id: str,
        object_code: str,  # noqa: ARG002
    ) -> list[str]:
        """Return scene_ids that contain this object."""
        return list(self._object_scene_map.get(object_code, set()))


# ── Fake Platform Composite ─────────────────────────────────────────────────────


class FakeSceneServicePlatform(SceneServiceMixin):
    """Composite: backend + scene service mixin.

    Provides _ontology_for and _base_path_for as required by the mixin
    (via _HasOntologyBackend protocol + _base_path_for usage).
    """

    def __init__(self, backend: FakeSceneMembershipBackend, tmp_path: Path | None = None) -> None:
        self._backend = backend
        self._tmp_path = tmp_path or Path("/tmp/fake_scene_test")

    def _ontology_for(self, base_id: str) -> FakeSceneMembershipBackend:  # noqa: ARG002
        return self._backend

    def _base_path_for(self, base_id: str) -> Path:  # noqa: ARG002
        p = self._tmp_path / base_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def create_base(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Simulate LibraryMixin.create_base + DatacloudPlatform.create_base."""
        base_id: str = entry.get("base_id", "")
        try:
            self._ensure_default_scene(base_id)
        except PermissionError:
            pass
        # Simulate Platform.create_base owl_path auto-seeding
        _owl_path: str = (
            entry.get("backend_config", {}).get("ontology", {}).get("owl_path", "")
        )
        if _owl_path:
            try:
                self._seed_from_owl_path(base_id, _owl_path)
            except (PermissionError, AttributeError):
                pass
        return entry


# ── Helpers ──────────────────────────────────────────────────────────────────────


def _make_obj(object_code: str, *, object_name: str = "") -> dict[str, Any]:
    return {
        "object_code": object_code,
        "object_name": object_name or object_code,
        "object_desc": "",
    }


def _make_view(view_code: str, *, view_name: str = "") -> dict[str, Any]:
    return {
        "view_code": view_code,
        "view_name": view_name or view_code,
    }


def _default_scene_code() -> str:
    return "default"


@pytest.fixture
def backend() -> FakeSceneMembershipBackend:
    """Fresh FakeSceneMembershipBackend for each test."""
    return FakeSceneMembershipBackend()


@pytest.fixture
def p(backend: FakeSceneMembershipBackend, tmp_path: Path) -> FakeSceneServicePlatform:
    """Fresh FakeSceneServicePlatform wrapping the backend."""
    return FakeSceneServicePlatform(backend, tmp_path)


# ═══════════════════════════════════════════════════════════════════════════════════
# Test: Default Scene Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════════


class TestDefaultSceneLifecycle:
    """Tests for default scene auto-create and auto-destroy."""

    def test_default_scene_created_when_orphan_appears(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """When object is created without scene, default scene appears."""
        p.create_object_with_scene(BASE_ID, _make_obj("obj1"))

        scenes = backend.list_scenes(BASE_ID)
        assert len(scenes) == 1
        assert scenes[0]["scene_code"] == _default_scene_code()
        obj_codes, _ = backend.get_scene_members(BASE_ID, scenes[0]["scene_id"])
        assert "obj1" in obj_codes

    def test_default_scene_not_created_when_no_orphans(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """Creating objects WITH scene should NOT create default scene."""
        scene = backend.create_scene(
            BASE_ID, {"scene_name": "自定义", "scene_code": "custom"}
        )
        p.create_object_with_scene(
            BASE_ID, _make_obj("obj1"), scene_id=scene["scene_id"]
        )

        scenes = backend.list_scenes(BASE_ID)
        scene_codes = [s["scene_code"] for s in scenes]
        assert _default_scene_code() not in scene_codes
        assert "custom" in scene_codes

    def test_default_scene_destroyed_when_all_orphans_resolved(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """Default scene disappears when no members or orphans remain."""
        p.create_object_with_scene(BASE_ID, _make_obj("obj1"))

        assert len(backend.list_scenes(BASE_ID)) == 1

        p.delete_object_from_all_scenes(BASE_ID, "obj1")

        scenes = backend.list_scenes(BASE_ID)
        scene_codes = [s["scene_code"] for s in scenes]
        assert _default_scene_code() not in scene_codes

    def test_default_scene_stays_when_has_members(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """Default scene with members persists even if other scenes exist."""
        p.create_object_with_scene(BASE_ID, _make_obj("obj1"))
        p.create_object_with_scene(BASE_ID, _make_obj("obj2"))

        assert len(backend.list_scenes(BASE_ID)) == 1

        p.delete_object_from_all_scenes(BASE_ID, "obj1")

        scenes = backend.list_scenes(BASE_ID)
        scene_codes = [s["scene_code"] for s in scenes]
        assert _default_scene_code() in scene_codes

        obj_codes, _ = backend.get_scene_members(BASE_ID, scenes[0]["scene_id"])
        assert obj_codes == ["obj2"]

    def test_delete_object_then_create_again_reuses_default(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """After default scene destroyed, creating orphan re-creates it."""
        p.create_object_with_scene(BASE_ID, _make_obj("obj1"))
        p.delete_object_from_all_scenes(BASE_ID, "obj1")
        assert len(backend.list_scenes(BASE_ID)) == 0

        p.create_object_with_scene(BASE_ID, _make_obj("obj2"))
        scenes = backend.list_scenes(BASE_ID)
        assert len(scenes) == 1
        assert scenes[0]["scene_code"] == _default_scene_code()


# ═══════════════════════════════════════════════════════════════════════════════════
# Test: Object Scene Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════════


class TestObjectSceneLifecycle:
    """Tests for object CRUD with scene coupling."""

    def test_create_object_auto_adds_to_default_scene(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """create_object_with_scene with empty scene_id -> object in default scene."""
        result = p.create_object_with_scene(BASE_ID, _make_obj("obj1"))
        assert result["object_code"] == "obj1"

        scenes = backend.list_scenes(BASE_ID)
        assert len(scenes) == 1
        obj_codes, _ = backend.get_scene_members(BASE_ID, scenes[0]["scene_id"])
        assert obj_codes == ["obj1"]

    def test_create_object_with_explicit_scene(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """create_object_with_scene with explicit scene_id."""
        scene = backend.create_scene(
            BASE_ID, {"scene_name": "产品场景", "scene_code": "product"}
        )
        result = p.create_object_with_scene(
            BASE_ID, _make_obj("by_product"), scene_id=scene["scene_id"]
        )
        assert result["object_code"] == "by_product"

        obj_codes, _ = backend.get_scene_members(BASE_ID, "product")
        assert "by_product" in obj_codes

    def test_delete_object_removes_from_all_scenes(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """After delete, object removed from ALL scenes and deleted."""
        p.create_object_with_scene(BASE_ID, _make_obj("obj1"))
        scene_id = backend.list_scenes(BASE_ID)[0]["scene_id"]

        p.delete_object_from_all_scenes(BASE_ID, "obj1")

        assert "obj1" not in backend._objects
        obj_codes, _ = backend.get_scene_members(BASE_ID, scene_id)
        assert "obj1" not in obj_codes

    def test_object_cross_scene(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """Same object can be in multiple scenes."""
        scene_a = backend.create_scene(BASE_ID, {"scene_name": "A", "scene_code": "A"})
        scene_b = backend.create_scene(BASE_ID, {"scene_name": "B", "scene_code": "B"})

        p.create_object_with_scene(
            BASE_ID, _make_obj("obj_x"), scene_id=scene_a["scene_id"]
        )
        backend.add_scene_members(BASE_ID, scene_b["scene_id"], ["obj_x"], [])

        assert backend.get_object_scene_count(BASE_ID, "obj_x") == 2

    def test_remove_from_last_scene_moves_to_default(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """When removed from its last scene, object goes to default."""
        scene = backend.create_scene(BASE_ID, {"scene_name": "S", "scene_code": "S"})
        p.create_object_with_scene(
            BASE_ID, _make_obj("obj1"), scene_id=scene["scene_id"]
        )

        p.remove_object_from_scene_safe(BASE_ID, scene["scene_id"], "obj1")

        default_id = None
        for s in backend.list_scenes(BASE_ID):
            if s["scene_code"] == _default_scene_code():
                default_id = s["scene_id"]
                break
        assert default_id is not None
        obj_codes, _ = backend.get_scene_members(BASE_ID, default_id)
        assert "obj1" in obj_codes

    def test_remove_from_one_of_many_scenes_does_not_move(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """Removing from one scene when others exist does NOT trigger move."""
        scene_a = backend.create_scene(BASE_ID, {"scene_name": "A", "scene_code": "A"})
        scene_b = backend.create_scene(BASE_ID, {"scene_name": "B", "scene_code": "B"})

        p.create_object_with_scene(
            BASE_ID, _make_obj("obj1"), scene_id=scene_a["scene_id"]
        )
        backend.add_scene_members(BASE_ID, scene_b["scene_id"], ["obj1"], [])

        p.remove_object_from_scene_safe(BASE_ID, scene_a["scene_id"], "obj1")

        assert backend.get_object_scene_count(BASE_ID, "obj1") == 1
        obj_codes, _ = backend.get_scene_members(BASE_ID, scene_b["scene_id"])
        assert "obj1" in obj_codes

        scene_codes = [s["scene_code"] for s in backend.list_scenes(BASE_ID)]
        assert _default_scene_code() not in scene_codes

    def test_create_view_with_scene(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """create_view_with_scene adds view to default scene."""
        result = p.create_view_with_scene(BASE_ID, _make_view("v_lookup"))
        assert result["view_code"] == "v_lookup"

        scenes = backend.list_scenes(BASE_ID)
        assert len(scenes) == 1
        _, vw_codes = backend.get_scene_members(BASE_ID, scenes[0]["scene_id"])
        assert "v_lookup" in vw_codes

    def test_delete_view_from_all_scenes(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """delete_view_from_all_scenes removes view from everywhere and deletes."""
        p.create_view_with_scene(BASE_ID, _make_view("v_lookup"))
        scene_id = backend.list_scenes(BASE_ID)[0]["scene_id"]

        p.delete_view_from_all_scenes(BASE_ID, "v_lookup")

        assert "v_lookup" not in backend._views
        _, vw_codes = backend.get_scene_members(BASE_ID, scene_id)
        assert "v_lookup" not in vw_codes


# ═══════════════════════════════════════════════════════════════════════════════════
# Test: Delete Scene With Migration
# ═══════════════════════════════════════════════════════════════════════════════════


class TestDeleteSceneWithMigration:
    """Tests for delete_scene_with_migration."""

    def test_delete_scene_migrates_members_to_default(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """Members move to default when scene is deleted."""
        scene = backend.create_scene(
            BASE_ID, {"scene_name": "待删", "scene_code": "to_delete"}
        )
        p.create_object_with_scene(
            BASE_ID, _make_obj("obj1"), scene_id=scene["scene_id"]
        )
        p.create_object_with_scene(
            BASE_ID, _make_obj("obj2"), scene_id=scene["scene_id"]
        )

        p.delete_scene_with_migration(BASE_ID, scene["scene_id"])

        assert "to_delete" not in backend._scenes
        default_id = None
        for s in backend.list_scenes(BASE_ID):
            if s["scene_code"] == _default_scene_code():
                default_id = s["scene_id"]
                break
        assert default_id is not None
        obj_codes, _ = backend.get_scene_members(BASE_ID, default_id)
        assert "obj1" in obj_codes
        assert "obj2" in obj_codes

    def test_cannot_delete_default_scene_directly(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """Raises ValueError when trying to delete default scene."""
        p.create_object_with_scene(BASE_ID, _make_obj("obj1"))
        default_id = backend.list_scenes(BASE_ID)[0]["scene_id"]

        with pytest.raises(ValueError, match="不能直接删除默认场景"):
            p.delete_scene_with_migration(BASE_ID, default_id)

    def test_delete_scene_without_members_no_default_created(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """Deleting an empty scene does not create a default scene."""
        scene = backend.create_scene(
            BASE_ID, {"scene_name": "空的", "scene_code": "empty"}
        )
        p.delete_scene_with_migration(BASE_ID, scene["scene_id"])
        assert "empty" not in backend._scenes
        scene_codes = [s["scene_code"] for s in backend.list_scenes(BASE_ID)]
        assert _default_scene_code() not in scene_codes

    def test_delete_nonexistent_scene_is_idempotent(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """delete_scene_with_migration returns silently for non-existent scenes."""
        p.delete_scene_with_migration(BASE_ID, "no_such_scene")
        assert "no_such_scene" not in backend._scenes

    def test_delete_scene_with_empty_default_after_migration(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """After migration + scene deletion, default may stay if not empty."""
        scene_a = backend.create_scene(BASE_ID, {"scene_name": "A", "scene_code": "A"})
        scene_b = backend.create_scene(BASE_ID, {"scene_name": "B", "scene_code": "B"})

        p.create_object_with_scene(
            BASE_ID, _make_obj("obj1"), scene_id=scene_a["scene_id"]
        )
        p.create_object_with_scene(
            BASE_ID, _make_obj("obj2"), scene_id=scene_b["scene_id"]
        )

        p.delete_scene_with_migration(BASE_ID, scene_a["scene_id"])

        scene_codes = [s["scene_code"] for s in backend.list_scenes(BASE_ID)]
        assert _default_scene_code() in scene_codes
        default_id = None
        for s in backend.list_scenes(BASE_ID):
            if s["scene_code"] == _default_scene_code():
                default_id = s["scene_id"]
                break
        assert default_id is not None
        obj_codes, _ = backend.get_scene_members(BASE_ID, default_id)
        assert "obj1" in obj_codes


# ═══════════════════════════════════════════════════════════════════════════════════
# Test: Backend Reverse-Lookup Methods
# ═══════════════════════════════════════════════════════════════════════════════════


class TestBackendMethods:
    """Tests for new backend reverse-lookup methods."""

    def test_get_object_scene_count_zero(
        self, backend: FakeSceneMembershipBackend
    ) -> None:
        """New object with no scenes returns 0."""
        backend.create_object(BASE_ID, _make_obj("orphan"))
        assert backend.get_object_scene_count(BASE_ID, "orphan") == 0

    def test_get_object_scene_count_multiple(
        self, backend: FakeSceneMembershipBackend
    ) -> None:
        """Object in multiple scenes returns correct count."""
        backend.create_object(BASE_ID, _make_obj("obj_x"))
        s1 = backend.create_scene(BASE_ID, {"scene_name": "S1", "scene_code": "S1"})
        s2 = backend.create_scene(BASE_ID, {"scene_name": "S2", "scene_code": "S2"})
        backend.add_scene_members(BASE_ID, s1["scene_id"], ["obj_x"], [])
        backend.add_scene_members(BASE_ID, s2["scene_id"], ["obj_x"], [])
        assert backend.get_object_scene_count(BASE_ID, "obj_x") == 2

    def test_remove_object_from_all_scenes(
        self, backend: FakeSceneMembershipBackend
    ) -> None:
        """remove_object_from_all_scenes clears all scene memberships."""
        backend.create_object(BASE_ID, _make_obj("obj_x"))
        s1 = backend.create_scene(BASE_ID, {"scene_name": "S1", "scene_code": "S1"})
        s2 = backend.create_scene(BASE_ID, {"scene_name": "S2", "scene_code": "S2"})
        backend.add_scene_members(BASE_ID, s1["scene_id"], ["obj_x"], [])
        backend.add_scene_members(BASE_ID, s2["scene_id"], ["obj_x"], [])

        removed = backend.remove_object_from_all_scenes(BASE_ID, "obj_x")
        assert removed == 2
        assert backend.get_object_scene_count(BASE_ID, "obj_x") == 0

    def test_get_scenes_containing_object(
        self, backend: FakeSceneMembershipBackend
    ) -> None:
        """get_scenes_containing_object returns correct scene_ids."""
        backend.create_object(BASE_ID, _make_obj("obj_x"))
        s1 = backend.create_scene(BASE_ID, {"scene_name": "S1", "scene_code": "S1"})
        s2 = backend.create_scene(BASE_ID, {"scene_name": "S2", "scene_code": "S2"})
        backend.add_scene_members(BASE_ID, s1["scene_id"], ["obj_x"], [])
        backend.add_scene_members(BASE_ID, s2["scene_id"], ["obj_x"], [])

        scenes = backend.get_scenes_containing_object(BASE_ID, "obj_x")
        assert set(scenes) == {"S1", "S2"}

    def test_get_scenes_containing_object_none(
        self, backend: FakeSceneMembershipBackend
    ) -> None:
        """Object not in any scene returns empty list."""
        backend.create_object(BASE_ID, _make_obj("lonely"))
        scenes = backend.get_scenes_containing_object(BASE_ID, "lonely")
        assert scenes == []

    def test_remove_view_from_all_scenes(
        self, backend: FakeSceneMembershipBackend
    ) -> None:
        """remove_view_from_all_scenes clears view from all scenes."""
        backend.create_view(BASE_ID, _make_view("vx"))
        s1 = backend.create_scene(BASE_ID, {"scene_name": "S1", "scene_code": "S1"})
        s2 = backend.create_scene(BASE_ID, {"scene_name": "S2", "scene_code": "S2"})
        backend.add_scene_members(BASE_ID, s1["scene_id"], [], ["vx"])
        backend.add_scene_members(BASE_ID, s2["scene_id"], [], ["vx"])

        removed = backend.remove_view_from_all_scenes(BASE_ID, "vx")
        assert removed == 2
        assert backend.get_view_scene_count(BASE_ID, "vx") == 0

    def test_get_view_scene_count(self, backend: FakeSceneMembershipBackend) -> None:
        """get_view_scene_count works correctly."""
        backend.create_view(BASE_ID, _make_view("vx"))
        s1 = backend.create_scene(BASE_ID, {"scene_name": "S1", "scene_code": "S1"})
        backend.add_scene_members(BASE_ID, s1["scene_id"], [], ["vx"])
        assert backend.get_view_scene_count(BASE_ID, "vx") == 1

    def test_load_ontology_reflects_store(
        self, backend: FakeSceneMembershipBackend
    ) -> None:
        """load_ontology returns objects and views from the fake store."""
        backend.create_object(BASE_ID, _make_obj("obj_a"))
        backend.create_view(BASE_ID, _make_view("v_a"))

        loader = backend.load_ontology(Path("/fake"))
        assert "obj_a" in loader._classes
        assert loader._classes["obj_a"].object_code == "obj_a"
        assert "v_a" in loader._views

    def test_get_objects_from_loader(self, backend: FakeSceneMembershipBackend) -> None:
        """get_objects extracts summaries from loader."""
        backend.create_object(BASE_ID, _make_obj("obj_a"))
        backend.create_object(BASE_ID, _make_obj("obj_b"))
        loader = backend.load_ontology(Path("/fake"))
        objects = backend.get_objects(loader, BASE_ID)
        codes = {o["object_code"] for o in objects}
        assert codes == {"obj_a", "obj_b"}


# ═══════════════════════════════════════════════════════════════════════════════════
# Test: Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Tests for edge cases and invariants."""

    def test_default_scene_idempotent(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """Multiple _ensure_default_scene calls are idempotent."""
        sid1 = p._ensure_default_scene(BASE_ID)
        sid2 = p._ensure_default_scene(BASE_ID)
        assert sid1 == sid2
        assert len(backend._scenes) == 1

    def test_has_orphans_true_when_object_not_in_any_scene(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """_has_orphans returns True when an object exists without scene membership."""
        backend.create_object(BASE_ID, _make_obj("orphan"))
        assert p._has_orphans(BASE_ID)

    def test_has_orphans_false_when_all_assigned(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """_has_orphans returns False when every object is in a scene."""
        p.create_object_with_scene(BASE_ID, _make_obj("obj1"))
        assert not p._has_orphans(BASE_ID)

    def test_maybe_destroy_default_scene_noop_when_has_members(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """_maybe_destroy_default_scene does nothing when default has members."""
        p.create_object_with_scene(BASE_ID, _make_obj("obj1"))
        p._maybe_destroy_default_scene(BASE_ID)
        scene_codes = [s["scene_code"] for s in backend.list_scenes(BASE_ID)]
        assert _default_scene_code() in scene_codes

    def test_create_view_with_scene_no_default_when_explicit(
        self, p: FakeSceneServicePlatform, backend: FakeSceneMembershipBackend
    ) -> None:
        """Creating a view with explicit scene does not trigger default."""
        scene = backend.create_scene(BASE_ID, {"scene_name": "V", "scene_code": "V"})
        p.create_view_with_scene(BASE_ID, _make_view("vx"), scene_id=scene["scene_id"])
        scene_codes = [s["scene_code"] for s in backend.list_scenes(BASE_ID)]
        assert _default_scene_code() not in scene_codes


# ═══════════════════════════════════════════════════════════════════════════════════
# Test: create_base Auto-Default Scene
# ═══════════════════════════════════════════════════════════════════════════════════


class TestCreateBaseAutoDefaultScene:
    """Tests that create_base auto-creates default scene for LOCAL,
    and gracefully skips for read-only backends.
    """

    BASE_ID = "auto_test_base"

    def test_create_base_local_creates_default_scene(self) -> None:
        """LOCAL base: default scene is auto-created and orphans absorbed."""
        backend = FakeSceneMembershipBackend()
        backend.create_object(
            self.BASE_ID,
            {"object_code": "obj_pre", "object_name": "Pre-loaded Object"},
        )

        plat = FakeSceneServicePlatform(backend)

        result = plat.create_base(
            {
                "base_id": self.BASE_ID,
                "display_name": "Test Base",
                "source_type": "LOCAL",
                "manual_backends": {},
                "backend_config": {"ontology": {"base_path": "/fake"}},
                "owner_type": "test",
            }
        )

        scenes = backend.list_scenes(self.BASE_ID)
        default_scene = next(
            (s for s in scenes if s.get("scene_code") == "default"), None
        )
        assert default_scene is not None, "create_base should auto-create default scene"
        assert default_scene["scene_id"] != ""

        obj_codes, _ = backend.get_scene_members(
            self.BASE_ID, default_scene["scene_id"]
        )
        assert "obj_pre" in obj_codes, (
            "Pre-loaded orphan should be absorbed into default scene"
        )
        assert result["base_id"] == self.BASE_ID

    def test_create_base_remote_skips_default_scene(self) -> None:
        """REMOTE base: PermissionError caught, no crash, no default scene."""
        backend = FakeSceneMembershipBackend()
        original_create_scene = backend.create_scene

        def _read_only_create_scene(base_id: str, scene: Any) -> dict[str, Any]:
            raise PermissionError("Read-only")

        backend.create_scene = _read_only_create_scene  # type: ignore[method-assign]

        plat = FakeSceneServicePlatform(backend)

        result = plat.create_base(
            {
                "base_id": self.BASE_ID,
                "display_name": "Remote Base",
                "source_type": "REMOTE",
                "manual_backends": {},
                "backend_config": {"ontology": {"base_path": "/fake"}},
                "owner_type": "test",
            }
        )

        assert result["base_id"] == self.BASE_ID
        scenes = backend.list_scenes(self.BASE_ID)
        default_found = any(s.get("scene_code") == "default" for s in scenes)
        assert not default_found, "REMOTE base should not create default scene"

        backend.create_scene = original_create_scene  # type: ignore[method-assign]

    def test_create_base_idempotent_default_scene(self) -> None:
        """Calling create_base twice for the same base_id is idempotent."""
        backend = FakeSceneMembershipBackend()
        plat = FakeSceneServicePlatform(backend)

        plat.create_base(
            {
                "base_id": self.BASE_ID,
                "display_name": "First",
                "source_type": "LOCAL",
                "manual_backends": {},
                "backend_config": {"ontology": {"base_path": "/fake"}},
                "owner_type": "test",
            }
        )

        plat.create_base(
            {
                "base_id": self.BASE_ID,
                "display_name": "First (again)",
                "source_type": "LOCAL",
                "manual_backends": {},
                "backend_config": {"ontology": {"base_path": "/fake"}},
                "owner_type": "test",
            }
        )

        default_scenes = [
            s
            for s in backend.list_scenes(self.BASE_ID)
            if s.get("scene_code") == "default"
        ]
        assert len(default_scenes) == 1, "create_base must be idempotent"

    def test_new_orphans_absorbed_when_default_empty(self) -> None:
        """Orphans added after default scene exists are absorbed when discovered."""
        backend = FakeSceneMembershipBackend()
        plat = FakeSceneServicePlatform(backend)

        plat.create_base(
            {
                "base_id": self.BASE_ID,
                "display_name": "Test",
                "source_type": "LOCAL",
                "manual_backends": {},
                "backend_config": {"ontology": {"base_path": "/fake"}},
                "owner_type": "test",
            }
        )

        default_id = backend._scenes.get("default", {}).get("scene_id", "default")
        obj, vw = backend.get_scene_members(self.BASE_ID, default_id)
        assert len(obj) == 0

        backend.create_object(
            self.BASE_ID, {"object_code": "new_orphan", "object_name": "New Orphan"}
        )

        backend.create_object(
            self.BASE_ID, {"object_code": "temp_obj", "object_name": "Temp"}
        )
        backend.add_scene_members(self.BASE_ID, default_id, ["temp_obj"], [])
        plat.delete_object_from_all_scenes(self.BASE_ID, "temp_obj")

        obj, vw = backend.get_scene_members(self.BASE_ID, default_id)
        assert "new_orphan" in obj, "New orphan should be absorbed into default scene"

    def test_create_base_with_owl_path_does_not_crash(self) -> None:
        """create_base with owl_path triggers _seed_from_owl_path, handles fake backends."""
        backend = FakeSceneMembershipBackend()
        plat = FakeSceneServicePlatform(backend)

        result = plat.create_base(
            {
                "base_id": "owl_test",
                "display_name": "OWL Test",
                "source_type": "LOCAL",
                "manual_backends": {},
                "backend_config": {
                    "ontology": {
                        "base_path": "/fake/base",
                        "owl_path": "/fake/owl/path",
                    }
                },
                "owner_type": "test",
            }
        )

        assert result["base_id"] == "owl_test"
        # Default scene created by _ensure_default_scene
        scenes = backend.list_scenes("owl_test")
        assert any(s.get("scene_code") == "default" for s in scenes), (
            "create_base should create default scene"
        )
        # _seed_from_owl_path raised AttributeError on fake backend → caught
        # The test passes because the exception is handled gracefully
