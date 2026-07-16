#!/usr/bin/env python3
"""端到端验证脚本：测试 load_ontology_from_codes 视图关联对象展开。

运行方式:
    cd packages/datacloud-platform
    uv run python tests/verify_view_included_objects.py

验证场景:
    A. 实体存储路径 (entity store)
      A1: 仅 view_codes，视图通过 relations (HAS_OBJECT) 关联对象
      A2: 仅 view_codes，视图通过 view dict 的 objects 字段关联对象
      A3: view_codes + object_codes 同时传入
      A4: 无 view_codes 不展开（回归）

    B. 远程适配器路径 (remote fallback)
      B1: 仅 view_codes，远程 API 返回 objectCodes (camelCase)
      B2: view_codes + object_codes 同时传入
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datacloud_platform.adapters.json_entity_store import JsonEntityStore
from datacloud_data_sdk.ontology.loader import resolve_view_object_ids

BASE_ID = "BYCLAW_DATACLOUD"

# ═══════════════════════════════════════════════════════════════════════════════
# 辅助: _extract_view_object_codes — 委托给共享实现 resolve_view_object_ids
# ═══════════════════════════════════════════════════════════════════════════════


def _extract_view_object_codes(view_data: dict[str, Any]) -> list[str]:
    """从 view dict 中提取对象编码，委托给 shared helper。"""
    return resolve_view_object_ids(view_data)


# ═══════════════════════════════════════════════════════════════════════════════
# Mock backend
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeBackendWithEntityStore:
    """最小化的 entity store backend。"""

    def __init__(self, entity_store: JsonEntityStore) -> None:
        self._entity_store = entity_store

    def get_view_included_objects(
        self, ontology_code: str, *, base_id: str = ""
    ) -> list[str]:
        store = self._entity_store.sub_store(base_id)
        all_rels = store.list_all("relations")
        result: list[str] = []
        for r in all_rels:
            source = r.get("source_class", r.get("source_object_code", "")) or ""
            category = r.get("relation_category", "") or ""
            if source != ontology_code:
                continue
            if category not in ("HAS_OBJECT", "MANY_TO_ONE"):
                continue
            target = r.get("target_class", r.get("target_object_code", "")) or ""
            if target and target not in result:
                result.append(target)
        return result


class _FakePlatform:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def _ontology_for(self, base_id: str) -> Any:
        return self._backend

    def inject_virtual_actions(self, base_id: str, loader: Any) -> None:
        pass


def make_platform(backend: Any) -> Any:
    from datacloud_platform.mixins.scene_loader import SceneLoaderMixin

    class _TestPlatform(SceneLoaderMixin, _FakePlatform):
        pass

    return _TestPlatform(backend)


# ═══════════════════════════════════════════════════════════════════════════════
# 场景 A: 实体存储路径
# ═══════════════════════════════════════════════════════════════════════════════


def _build_entity_store_with_relations(data_dir: Path) -> JsonEntityStore:
    """视图通过 HAS_OBJECT relation 关联对象。"""
    store = JsonEntityStore(data_dir)
    scoped = store.sub_store(BASE_ID)
    scoped.save(
        "objects",
        "by_project",
        {
            "object_code": "by_project",
            "object_name": "项目管理",
            "fields": [],
            "actions": [],
        },
    )
    scoped.save(
        "views",
        "scene_project_management",
        {
            "view_id": "scene_project_management",
            "view_code": "scene_project_management",
            "view_name": "项目管理工作台",
            "objects": ["by_project"],  # objects field populated (real scenario)
            "actions": [],
        },
    )
    scoped.save(
        "relations",
        "rel_view_project",
        {
            "relation_code": "rel_view_project",
            "source_class": "scene_project_management",
            "target_class": "by_project",
            "relation_category": "HAS_OBJECT",
        },
    )
    return store


def _build_entity_store_view_field(data_dir: Path) -> JsonEntityStore:
    """视图通过自身的 objects 字段（非 relations）关联对象。"""
    store = JsonEntityStore(data_dir)
    scoped = store.sub_store(BASE_ID)
    scoped.save(
        "objects",
        "by_project",
        {
            "object_code": "by_project",
            "object_name": "项目管理",
            "fields": [],
            "actions": [],
        },
    )
    scoped.save(
        "views",
        "scene_project_management",
        {
            "view_id": "scene_project_management",
            "view_code": "scene_project_management",
            "view_name": "项目管理工作台",
            "objects": ["by_project"],  # objects field directly
            "actions": [],
        },
    )
    # No relations — view's own objects field is the sole source
    return store


def test_entity_store_relations_only() -> None:
    """A1: 仅 view_codes，视图通过 relations 关联对象。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _build_entity_store_with_relations(Path(tmpdir))
        platform = make_platform(_FakeBackendWithEntityStore(store))
        loader = platform.load_ontology_from_codes(
            BASE_ID, object_codes=[], view_codes=["scene_project_management"]
        )
        classes = getattr(loader, "_classes", {})
        assert "by_project" in classes, f"by_project 应在 _classes: {list(classes)}"
        view = loader.get_view("scene_project_management")
        assert any(o.object_code == "by_project" for o in view.objects), (
            "View 应包含 by_project"
        )
        print("  ✅ A1: Relations 展开正确")


def test_entity_store_view_field_only() -> None:
    """A2: 仅 view_codes，视图通过自身的 objects 字段关联对象（无 relations）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _build_entity_store_view_field(Path(tmpdir))
        platform = make_platform(_FakeBackendWithEntityStore(store))
        loader = platform.load_ontology_from_codes(
            BASE_ID, object_codes=[], view_codes=["scene_project_management"]
        )
        classes = getattr(loader, "_classes", {})
        assert "by_project" in classes, f"by_project 应在 _classes: {list(classes)}"
        view = loader.get_view("scene_project_management")
        assert any(o.object_code == "by_project" for o in view.objects), (
            "View 应包含 by_project"
        )
        print("  ✅ A2: View objects 字段展开正确 (无 relations)")


def test_entity_store_with_object_codes() -> None:
    """A3: view_codes + object_codes 同时传入。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _build_entity_store_with_relations(Path(tmpdir))
        scoped = store.sub_store(BASE_ID)
        scoped.save(
            "objects",
            "by_task",
            {
                "object_code": "by_task",
                "object_name": "任务管理",
                "fields": [],
                "actions": [],
            },
        )
        scoped.save(
            "relations",
            "rel_view_task",
            {
                "relation_code": "rel_view_task",
                "source_class": "scene_project_management",
                "target_class": "by_task",
                "relation_category": "HAS_OBJECT",
            },
        )

        platform = make_platform(_FakeBackendWithEntityStore(store))
        loader = platform.load_ontology_from_codes(
            BASE_ID,
            object_codes=["by_project"],
            view_codes=["scene_project_management"],
        )
        classes = getattr(loader, "_classes", {})
        assert "by_project" in classes
        assert "by_task" in classes, "view 关联的 by_task 应展开"
        print("  ✅ A3: object_codes + view_codes 正确展开")


def test_entity_store_no_view_codes() -> None:
    """A4: 无 view_codes 不展开（回归）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _build_entity_store_with_relations(Path(tmpdir))
        platform = make_platform(_FakeBackendWithEntityStore(store))
        loader = platform.load_ontology_from_codes(
            BASE_ID, object_codes=["by_project"], view_codes=None
        )
        classes = getattr(loader, "_classes", {})
        assert "by_project" in classes
        assert set(classes.keys()) == {"by_project"}, f"不应展开: {set(classes)}"
        print("  ✅ A4: 无 view_codes 不展开 (回归)")


# ═══════════════════════════════════════════════════════════════════════════════
# 场景 B: 远程适配器路径 (remote fallback)
# ═══════════════════════════════════════════════════════════════════════════════


def _make_remote_mock(
    scene_objects: list[dict[str, Any]],
    scene_views: list[dict[str, Any]],
    view_included_object_codes: list[str],
    scene_id: str = "scene-1",
) -> MagicMock:
    """创建一个模拟远端 backend，无 _entity_store，触发 remote fallback 路径。"""
    backend = MagicMock()
    del backend._entity_store  # 确保走 remote 路径

    # query_ontologies_by_scene: 返回包含目标代码的 items
    def _query_side_effect(scene_id: str, **kwargs: Any) -> dict[str, Any]:
        keyword = kwargs.get("keyword", "")
        qtype = kwargs.get("type", "object")
        items: list[dict[str, Any]] = []
        if qtype == "object" and keyword:
            items = [{"objectCode": keyword, "_sceneId": scene_id}]
        if qtype == "view" and keyword:
            items = [{"viewCode": keyword, "_sceneId": scene_id}]
        return {"data": {qtype + "s": items}}

    backend.query_ontologies_by_scene.side_effect = _query_side_effect

    # get_scene_details: 返回给定的 objects 和 views
    backend.get_scene_details.return_value = {
        "objects": scene_objects,
        "views": scene_views,
    }

    # get_view_included_objects: 返回给定的对象编码
    backend.get_view_included_objects.return_value = list(view_included_object_codes)

    return backend


def test_remote_view_codes_only() -> None:
    """B1: 仅 view_codes，远程 API 返回 objectCodes → 展开正确。"""
    backend = _make_remote_mock(
        scene_objects=[
            {
                "object_code": "by_project",
                "object_name": "项目管理",
                "fields": [],
                "actions": [],
            },
        ],
        scene_views=[
            {
                "view_id": "scene_project_management",
                "view_code": "scene_project_management",
                "objects": ["by_project"],  # 经 _normalize_remote_view 后应为 objects
            }
        ],
        view_included_object_codes=["by_project"],
    )

    platform = make_platform(backend)
    loader = platform.load_ontology_from_codes(
        BASE_ID, object_codes=[], view_codes=["scene_project_management"]
    )

    classes = getattr(loader, "_classes", {})
    assert "by_project" in classes, f"by_project 应在 _classes: {list(classes)}"
    view = loader.get_view("scene_project_management")
    assert any(o.object_code == "by_project" for o in view.objects)
    # 验证 get_scene_details 被调用时传入了展开后的 object_code
    call_kwargs = backend.get_scene_details.call_args[1]
    assert "by_project" in call_kwargs.get("object_code", []), (
        f"get_scene_details 应传入展开后的 object_code，"
        f"实际: {call_kwargs.get('object_code')}"
    )
    print("  ✅ B1: Remote fallback objects 展开正确")


def test_remote_view_and_object_codes() -> None:
    """B2: view_codes + object_codes 同时传入。"""
    backend = _make_remote_mock(
        scene_objects=[
            {
                "object_code": "by_project",
                "object_name": "项目管理",
                "fields": [],
                "actions": [],
            },
            {
                "object_code": "by_task",
                "object_name": "任务管理",
                "fields": [],
                "actions": [],
            },
        ],
        scene_views=[
            {
                "view_id": "scene_project_management",
                "view_code": "scene_project_management",
                "objects": ["by_task"],  # 经 _normalize_remote_view 后
            }
        ],
        view_included_object_codes=["by_task"],
    )

    platform = make_platform(backend)
    loader = platform.load_ontology_from_codes(
        BASE_ID,
        object_codes=["by_project"],
        view_codes=["scene_project_management"],
    )

    classes = getattr(loader, "_classes", {})
    assert "by_project" in classes
    assert "by_task" in classes, "view 关联的 by_task 应展开"
    print("  ✅ B2: Remote fallback object_codes + view_codes 正确展开")


def test_remote_view_objectCodes_raw_expansion() -> None:
    """B3: 远程 API 返回原始 objectCodes (camelCase)，_extract_view_object_codes 正确处理。"""
    backend = _make_remote_mock(
        scene_objects=[
            {
                "object_code": "by_project",
                "object_name": "项目管理",
                "fields": [],
                "actions": [],
            },
        ],
        scene_views=[
            {
                "view_id": "scene_project_management",
                "view_code": "scene_project_management",
                "objectCodes": ["by_project"],  # raw camelCase, 模拟未 normalize 的情况
            }
        ],
        view_included_object_codes=["by_project"],
    )

    platform = make_platform(backend)
    loader = platform.load_ontology_from_codes(
        BASE_ID, object_codes=[], view_codes=["scene_project_management"]
    )

    classes = getattr(loader, "_classes", {})
    assert "by_project" in classes, (
        f"_extract_view_object_codes 应能处理 objectCodes 字段，"
        f"实际 _classes: {list(classes)}"
    )
    print("  ✅ B3: Remote fallback raw objectCodes 展开正确")


def test_extract_view_object_codes_smoke() -> None:
    """验证 _extract_view_object_codes 处理各种格式。"""
    assert _extract_view_object_codes({"objectCodes": ["a", "b"]}) == ["a", "b"]
    assert _extract_view_object_codes({"object_codes": ["x"]}) == ["x"]
    assert _extract_view_object_codes({"objects": ["p", "q"]}) == ["p", "q"]
    assert _extract_view_object_codes({"object_ids": ["r"]}) == ["r"]
    assert _extract_view_object_codes(
        {"objects": [{"object_code": "z"}, {"objectCode": "w"}]}
    ) == ["z", "w"]
    assert _extract_view_object_codes({"objects": []}) == []
    assert _extract_view_object_codes({}) == []
    print("  ✅ _extract_view_object_codes: 所有格式通过")


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    print("=" * 60)
    print("端到端验证: load_ontology_from_codes 视图关联对象展开")
    print("=" * 60)
    print()

    tests_passed = 0
    tests_failed = 0

    def run(name: str, fn: Any) -> None:
        nonlocal tests_passed, tests_failed
        try:
            fn()
            tests_passed += 1
        except Exception as e:
            tests_failed += 1
            print(f"    ❌ 失败: {e}")
            import traceback

            traceback.print_exc()

    # 辅助函数测试
    print("── _extract_view_object_codes ──")
    run("格式测试", test_extract_view_object_codes_smoke)

    # 场景 A: 实体存储
    print("\n── 场景 A: Entity Store 路径 ──")
    run("A1: relations 展开", test_entity_store_relations_only)
    run("A2: view objects 字段展开", test_entity_store_view_field_only)
    run("A3: object_codes + view_codes", test_entity_store_with_object_codes)
    run("A4: 无 view_codes 不展开", test_entity_store_no_view_codes)

    # 场景 B: 远程适配器
    print("\n── 场景 B: Remote Fallback 路径 ──")
    run("B1: objects 展开", test_remote_view_codes_only)
    run("B2: object_codes + view_codes", test_remote_view_and_object_codes)
    run("B3: raw objectCodes 展开", test_remote_view_objectCodes_raw_expansion)

    print("\n" + "=" * 60)
    print(f"结果: {tests_passed} 通过, {tests_failed} 失败")
    print("=" * 60)

    if tests_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
