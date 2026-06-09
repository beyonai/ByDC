"""_patterns 单元测试 — 注入 FakeTermStore，验证查询组合模式。"""

from __future__ import annotations

import pytest
from datacloud_knowledge.capabilities.types import TermDetail
from datacloud_knowledge.retrieval._patterns import (
    query_bound_values,
    query_scope_props,
    query_user_synonyms,
)

from tests.fakes.fake_term_store import FakeTermStore

# ── 共享 fixture ────────────────────────────────────────────────────


def _make_term(
    term_id: str,
    term_code: str,
    term_name: str,
    term_type: str,
    *,
    dataset_id: str = "ds1",
    labels: dict[str, str] | None = None,
    synonyms: str = "",
    ext_attrs: dict[str, str] | None = None,
) -> TermDetail:
    """快捷构造 TermDetail。"""
    return TermDetail(
        term_id=term_id,
        term_code=term_code,
        term_name=term_name,
        term_type=term_type,
        dataset_id=dataset_id,
        labels=labels or {},
        synonyms=synonyms,
        ext_attrs=ext_attrs or {},
    )


@pytest.fixture
def store() -> FakeTermStore:
    """含种子数据的 FakeTermStore。"""
    return FakeTermStore().seed(
        _make_term("t1", "sales_amount", "销售额", "prop", ext_attrs={"termDataType": "prop"}),
        _make_term("t2", "customer_name", "客户名", "prop", ext_attrs={"termDataType": "prop"}),
        _make_term("t3", "scene_enterprise", "企业分析", "view"),
        _make_term("t4", "region_val", "华东", "region_code"),
        _make_term("t5", "level_val", "高", "level_code"),
        _make_term(
            "t6",
            "syn_001",
            "我的别名",
            "synonym",
            labels={"userId": "user123"},
        ),
        _make_term(
            "t7",
            "syn_002",
            "公共别名",
            "synonym",
            labels={"userId": "user456"},
        ),
    )


# ── query_scope_props ───────────────────────────────────────────────


class TestQueryScopeProps:
    """测试 query_scope_props — 按 scope_code 查 prop 术语."""

    def test_returns_only_props(self, store: FakeTermStore) -> None:
        """scope 下只返回 termDataType=prop 的术语."""
        result = query_scope_props(store, scope_code="scene_enterprise")
        assert result.total == 0  # seed 中没有 scene_enterprise 类型的 prop

    def test_filters_by_scope_code(self, store: FakeTermStore) -> None:
        """验证调用时传入的 scope_code 参数."""
        # 添加匹配的 scope 数据
        store.seed(
            _make_term(
                "t8",
                "revenue",
                "营收",
                "scene_sales",
                labels={"termDataType": "prop"},
            ),
            _make_term(
                "t9",
                "profit",
                "利润",
                "scene_sales",
                labels={"termDataType": "prop"},
            ),
        )
        result = query_scope_props(store, scope_code="scene_sales")
        assert result.total == 2

    def test_empty_scope_returns_nothing(self, store: FakeTermStore) -> None:
        """不匹配的 scope 返回空."""
        result = query_scope_props(store, scope_code="nonexistent")
        assert result.total == 0


# ── query_bound_values ──────────────────────────────────────────────


class TestQueryBoundValues:
    """测试 query_bound_values — 按 termBinding 编码批量查值术语."""

    def test_batch_query_by_codes(self, store: FakeTermStore) -> None:
        """传入多个 binding code 批量返回."""
        result = query_bound_values(store, binding_codes=["region_code", "level_code"])
        assert result.total == 2

    def test_single_code(self, store: FakeTermStore) -> None:
        """单个 code 返回对应结果."""
        result = query_bound_values(store, binding_codes=["region_code"])
        assert result.total == 1
        assert result.items[0].term_name == "华东"

    def test_empty_codes(self, store: FakeTermStore) -> None:
        """空列表返回空."""
        result = query_bound_values(store, binding_codes=[])
        assert result.total > 0  # 无 term_type 过滤 → 返回全部


# ── query_user_synonyms ─────────────────────────────────────────────


class TestQueryUserSynonyms:
    """测试 query_user_synonyms — 按 userId 查同义词."""

    def test_filters_by_user_id(self, store: FakeTermStore) -> None:
        """只返回 userId 匹配的同义词."""
        result = query_user_synonyms(store, user_id="user123")
        assert result.total == 1
        assert result.items[0].term_name == "我的别名"

    def test_different_user_returns_empty(self, store: FakeTermStore) -> None:
        """不匹配的 userId 返回空."""
        result = query_user_synonyms(store, user_id="nonexistent")
        assert result.total == 0
