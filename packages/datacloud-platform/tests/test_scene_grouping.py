"""Scene grouping semantics tests — member management + getSceneDetails filtering.

Uses FakeSceneBackend directly for pure business-logic testing
without going through the full Platform / route layer.
"""

from __future__ import annotations

from typing import Any

import pytest

from fakes import (
    FakeSceneBackend,
    make_action,
    make_ds,
    make_object,
    make_relation,
    make_scene,
    make_view,
)

BASE_ID = "b1"


@pytest.fixture
def fb() -> FakeSceneBackend:
    """Fresh FakeSceneBackend for each test."""
    return FakeSceneBackend()


class TestSceneGrouping:
    """分组语义：对象独立存在、多 scene 共享、删除分组不删资源、成员幂等、移除不删实体."""

    def test_object_exists_without_scene(self, fb: FakeSceneBackend) -> None:
        """对象可以独立存在于库下，不绑定 scene."""
        obj = fb.create_object(BASE_ID, make_object("by_customer"))
        assert fb.get_object_detail(BASE_ID, "by_customer") is not None
        assert obj["objectCode"] == "by_customer"

    def test_add_object_to_scene_then_get_details(self, fb: FakeSceneBackend) -> None:
        """往分组添加对象后，getSceneDetails 应返回该对象."""
        fb.create_object(BASE_ID, make_object("by_customer"))
        fb.create_scene(BASE_ID, make_scene("默认场景", scene_code="scene_1"))
        fb.add_scene_members(
            BASE_ID, "scene_1", object_codes=["by_customer"], view_codes=[]
        )

        details = fb.get_scene_details(BASE_ID, "scene_1")
        assert len(details["objects"]) == 1
        assert details["objects"][0]["objectCode"] == "by_customer"

    def test_delete_scene_does_not_delete_objects(self, fb: FakeSceneBackend) -> None:
        """删分组不删资源."""
        fb.create_object(BASE_ID, make_object("by_customer"))
        fb.create_scene(BASE_ID, make_scene("s1", scene_code="s1"))
        fb.add_scene_members(BASE_ID, "s1", object_codes=["by_customer"], view_codes=[])
        fb.delete_scene(BASE_ID, "s1")

        # Scene 已删
        assert "s1" not in fb._scenes
        # 对象还在
        assert fb.get_object_detail(BASE_ID, "by_customer") is not None

    def test_same_object_in_multiple_scenes(self, fb: FakeSceneBackend) -> None:
        """同一个对象可以属于多个 scene."""
        fb.create_object(BASE_ID, make_object("by_customer"))
        fb.create_scene(BASE_ID, make_scene("s1", scene_code="s1"))
        fb.create_scene(BASE_ID, make_scene("s2", scene_code="s2"))
        fb.add_scene_members(BASE_ID, "s1", object_codes=["by_customer"], view_codes=[])
        fb.add_scene_members(BASE_ID, "s2", object_codes=["by_customer"], view_codes=[])

        d1 = fb.get_scene_details(BASE_ID, "s1")
        d2 = fb.get_scene_details(BASE_ID, "s2")
        assert d1["objects"][0]["objectCode"] == "by_customer"
        assert d2["objects"][0]["objectCode"] == "by_customer"

    def test_add_members_is_idempotent(self, fb: FakeSceneBackend) -> None:
        """重复添加同一对象不报错，不重复扩容."""
        fb.create_object(BASE_ID, make_object("by_customer"))
        fb.create_scene(BASE_ID, make_scene("s1", scene_code="s1"))
        fb.add_scene_members(BASE_ID, "s1", object_codes=["by_customer"], view_codes=[])
        fb.add_scene_members(BASE_ID, "s1", object_codes=["by_customer"], view_codes=[])

        scene = fb._scenes["s1"]
        assert scene["member_object_codes"] == ["by_customer"]  # 去重

    def test_remove_member_leaves_object_intact(self, fb: FakeSceneBackend) -> None:
        """移除分组成员不删对象."""
        fb.create_object(BASE_ID, make_object("by_customer"))
        fb.create_scene(BASE_ID, make_scene("s1", scene_code="s1"))
        fb.add_scene_members(BASE_ID, "s1", object_codes=["by_customer"], view_codes=[])
        fb.remove_scene_members(
            BASE_ID, "s1", object_codes=["by_customer"], view_codes=[]
        )

        # Scene 还在
        assert fb._scenes["s1"] is not None
        # 对象还在
        assert fb.get_object_detail(BASE_ID, "by_customer") is not None
        # 但 scene 的 member 列表已空
        assert fb._scenes["s1"]["member_object_codes"] == []

    def test_remove_member_leaves_view_intact(self, fb: FakeSceneBackend) -> None:
        """移除视图成员不删视图."""
        fb.create_view(BASE_ID, make_view("sales_view"))
        fb.create_scene(BASE_ID, make_scene("s1", scene_code="s1"))
        fb.add_scene_members(BASE_ID, "s1", object_codes=[], view_codes=["sales_view"])
        fb.remove_scene_members(
            BASE_ID, "s1", object_codes=[], view_codes=["sales_view"]
        )

        assert fb._scenes["s1"]["member_view_codes"] == []
        assert "sales_view" in fb._views

    def test_member_views_shown_in_details(self, fb: FakeSceneBackend) -> None:
        """getSceneDetails 应包含 scene 的成员视图."""
        fb.create_view(BASE_ID, make_view("sales_view"))
        fb.create_scene(BASE_ID, make_scene("s1", scene_code="s1"))
        fb.add_scene_members(BASE_ID, "s1", object_codes=[], view_codes=["sales_view"])

        details = fb.get_scene_details(BASE_ID, "s1")
        assert len(details["views"]) == 1
        assert details["views"][0]["viewCode"] == "sales_view"


class _Setup:
    """Helper to prepare a standard test scenario with 2 objects + 1 view + 1 relation + 1 ds."""

    @staticmethod
    def setup(fb: FakeSceneBackend) -> None:
        fb.create_object(
            BASE_ID,
            make_object("by_cust", db_id="ds_1", actions=[make_action("get_cust")]),
        )
        fb.create_object(BASE_ID, make_object("by_order", db_id="ds_1"))
        fb.create_view(
            BASE_ID, make_view("sales_view", object_codes=["by_cust", "by_order"])
        )
        fb.create_relation(
            BASE_ID, make_relation("rel_1", source="by_cust", target="by_order")
        )
        fb.create_datasource(BASE_ID, make_ds("ds_1"))
        fb.create_scene(BASE_ID, make_scene("s1", scene_code="s1"))
        fb.add_scene_members(
            BASE_ID,
            "s1",
            object_codes=["by_cust", "by_order"],
            view_codes=["sales_view"],
        )


class TestGetSceneDetailsFiltering:
    """getSceneDetails 裁剪逻辑（对齐外部协议）."""

    @pytest.fixture
    def fb(self) -> FakeSceneBackend:
        """Fresh backend with standard test data."""
        backend = FakeSceneBackend()
        _Setup.setup(backend)
        return backend

    def test_no_filter_returns_all(self, fb: FakeSceneBackend) -> None:
        """无参数 → 返回 scene 下全部资源."""
        d = fb.get_scene_details(BASE_ID, "s1")
        assert len(d["objects"]) == 2
        assert len(d["views"]) == 1
        assert len(d["actions"]) == 1  # get_cust
        assert len(d["relations"]) == 1
        assert len(d["dbsources"]["db"]) == 1

    def test_filter_by_view_code_returns_subgraph(self, fb: FakeSceneBackend) -> None:
        """只传 viewCode → views 仅匹配的，objects 为该 view 引用的."""
        d = fb.get_scene_details(BASE_ID, "s1", view_code=["sales_view"])
        assert len(d["views"]) == 1
        assert d["views"][0]["viewCode"] == "sales_view"
        assert len(d["objects"]) == 2  # view 引用了 2 个对象
        assert len(d["actions"]) == 1
        assert len(d["relations"]) == 1

    def test_filter_by_object_code_views_empty(self, fb: FakeSceneBackend) -> None:
        """只传 objectCode → views 必须为空，只返回匹配对象."""
        d = fb.get_scene_details(BASE_ID, "s1", object_code=["by_cust"])
        assert len(d["views"]) == 0  # ← 关键规则
        assert len(d["objects"]) == 1
        assert d["objects"][0]["objectCode"] == "by_cust"
        assert len(d["actions"]) == 1  # by_cust 的 get_cust

    def test_filter_both_union(self, fb: FakeSceneBackend) -> None:
        """同时传 → 并集."""
        d = fb.get_scene_details(
            BASE_ID, "s1", view_code=["sales_view"], object_code=["by_order"]
        )
        assert len(d["views"]) == 1
        assert len(d["objects"]) == 2  # view 引用的 2 个 + by_order（已在集合中）

    def test_relations_only_both_ends_in_set(self, fb: FakeSceneBackend) -> None:
        """relations 必须两端对象都在裁剪后的对象集中."""
        # 只在 by_cust 一个对象 → rel 两端是 by_cust ↔ by_order，by_order 不在集 → 0 rels
        d = fb.get_scene_details(BASE_ID, "s1", object_code=["by_cust"])
        assert len(d["relations"]) == 0

        # 两个对象都在 → rel 返回
        d2 = fb.get_scene_details(BASE_ID, "s1", object_code=["by_cust", "by_order"])
        assert len(d2["relations"]) == 1

    def test_dbsources_only_referenced_by_filtered_objects(
        self, fb: FakeSceneBackend
    ) -> None:
        """dbsources 只返回筛选后对象属性引用的数据源."""
        d = fb.get_scene_details(BASE_ID, "s1", object_code=["by_cust"])
        assert len(d["dbsources"]["db"]) == 1  # by_cust 引用了 ds_1

    def test_scene_not_found_returns_empty(self, fb: FakeSceneBackend) -> None:
        """不存在的 scene 返回空结构."""
        d = fb.get_scene_details(BASE_ID, "nonexistent")
        assert d["scene"] is None
        assert d["views"] == []
        assert d["objects"] == []
        assert d["relations"] == []
        assert d["dbsources"]["db"] == []

    def test_persistence_roundtrip(self, fb: FakeSceneBackend, tmp_path: Any) -> None:
        """Scene 持久化 → 恢复后数据完整."""
        fb.persist_scenes(tmp_path)

        fb2 = FakeSceneBackend()
        fb2.restore_scenes(tmp_path)
        # restore 后仍保留 scene + 成员
        assert "s1" in fb2._scenes
        scene = fb2._scenes["s1"]
        assert "by_cust" in scene["member_object_codes"]
        assert "by_order" in scene["member_object_codes"]
        assert "sales_view" in scene["member_view_codes"]
