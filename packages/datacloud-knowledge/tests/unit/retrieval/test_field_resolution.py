"""field_resolution 单元测试 — 注入 FakeTermStore，验证字段消歧。"""

from __future__ import annotations

import pytest
from datacloud_knowledge.capabilities.types import TermDetail
from datacloud_knowledge.retrieval.field_resolution import resolve_field_aliases

from tests.fakes.fake_term_store import FakeTermStore


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
    """快捷构造 TermDetail."""
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
    """含种子数据的 FakeTermStore.

    scope=scene_sales 下有两个 prop：销售额 和 客户名（含别名）。
    """
    return FakeTermStore().seed(
        # scope 视图
        _make_term(
            "s1", "scene_sales", "销售视图", "scene_sales", ext_attrs={"termDataType": "view"}
        ),
        # prop: 销售额
        _make_term("p1", "sales_amount", "销售额", "scene_sales", labels={"termDataType": "prop"}),
        # prop: 客户名（含同义别名）
        _make_term(
            "p2",
            "customer_name",
            "客户名",
            "scene_sales",
            labels={"termDataType": "prop"},
            synonyms="客户名称|customer",
        ),
    )


# ── 精确匹配 ───────────────────────────────────────────────────────


class TestExactMatch:
    """精确匹配 term_name 消歧."""

    def test_exact_term_name_match(self, store: FakeTermStore) -> None:
        """精确命中 term_name → resolved."""
        result = resolve_field_aliases(store, terms=["销售额"], scope_code="scene_sales")
        assert result.resolved == {"销售额": "sales_amount"}
        assert len(result.ambiguous) == 0
        assert len(result.unresolved) == 0

    def test_alias_match(self, store: FakeTermStore) -> None:
        """命中 | 分隔的别名 → resolved."""
        result = resolve_field_aliases(store, terms=["客户名称"], scope_code="scene_sales")
        assert result.resolved == {"客户名称": "customer_name"}

    def test_english_alias_match(self, store: FakeTermStore) -> None:
        """英文别名匹配."""
        result = resolve_field_aliases(store, terms=["customer"], scope_code="scene_sales")
        assert result.resolved == {"customer": "customer_name"}


# ── 歧义 + 未命中 ──────────────────────────────────────────────────


class TestAmbiguousAndUnresolved:
    """歧义和未命中场景."""

    def test_ambiguous_multiple_matches(self, store: FakeTermStore) -> None:
        """多个 prop 命中同一别名 → ambiguous."""
        # 添加第二个 prop，别名也含"客户名称"
        store.seed(
            _make_term(
                "p3",
                "client_name",
                "客户全名",
                "scene_sales",
                labels={"termDataType": "prop"},
                synonyms="客户名称",
            ),
        )
        result = resolve_field_aliases(store, terms=["客户名称"], scope_code="scene_sales")
        assert "客户名称" not in result.resolved
        assert "客户名称" in result.ambiguous
        # 应匹配到 p2 和 p3
        codes = {c.term_code for c in result.ambiguous["客户名称"]}
        assert codes == {"customer_name", "client_name"}

    def test_unresolved_no_match(self, store: FakeTermStore) -> None:
        """无任何匹配 → unresolved."""
        result = resolve_field_aliases(store, terms=["不存在的字段"], scope_code="scene_sales")
        assert "不存在的字段" in result.unresolved
        assert len(result.resolved) == 0


# ── 多术语批量 ─────────────────────────────────────────────────────


class TestBatchResolution:
    """批量术语消歧."""

    def test_mixed_resolution(self, store: FakeTermStore) -> None:
        """混合场景：resolved + unresolved."""
        result = resolve_field_aliases(
            store, terms=["销售额", "不存在的字段", "客户名称"], scope_code="scene_sales"
        )
        assert result.resolved == {"销售额": "sales_amount", "客户名称": "customer_name"}
        assert result.unresolved == ["不存在的字段"]

    def test_empty_terms(self, store: FakeTermStore) -> None:
        """空输入."""
        result = resolve_field_aliases(store, terms=[], scope_code="scene_sales")
        assert result.resolved == {}
        assert result.unresolved == []

    def test_empty_scope_no_props(self, store: FakeTermStore) -> None:
        """无匹配 scope 时全部 unresolved."""
        result = resolve_field_aliases(store, terms=["销售额"], scope_code="nonexistent")
        assert result.unresolved == ["销售额"]
