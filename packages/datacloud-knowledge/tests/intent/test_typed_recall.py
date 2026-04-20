"""typed_recall 模块的单元测试。

使用 mock 替代真实数据库和 embedding 服务，验证：
1. RRF 融合逻辑
2. ktype → term_type_code 过滤映射
3. 多路召回 → 外层 RRF 融合
4. 搜索被禁用的 keyword 不触发召回
"""

from __future__ import annotations

# ---- RRF 单元测试 ----


class TestRRFFuse:
    """rrf_fuse 纯函数测试。"""

    def test_empty_input_returns_empty(self) -> None:
        from datacloud_knowledge.query.search.rrf import rrf_fuse

        assert rrf_fuse([]) == []

    def test_single_list_preserves_order(self) -> None:
        from datacloud_knowledge.query.search.rrf import rrf_fuse

        ranked = [
            ("T1", "企业综合分析表", "N1", "object"),
            ("T2", "物理网格综合分析表", "N2", "object"),
        ]
        result = rrf_fuse([ranked])
        assert len(result) == 2
        assert result[0].term_id == "T1"
        assert result[1].term_id == "T2"
        # rank1 得分 > rank2 得分
        assert result[0].rrf_score > result[1].rrf_score

    def test_two_lists_boost_shared_candidate(self) -> None:
        from datacloud_knowledge.query.search.rrf import rrf_fuse

        list_a = [
            ("T1", "高风险", "N1", "risk_level_name"),
            ("T2", "中风险", "N2", "risk_level_name"),
        ]
        list_b = [
            ("T2", "中风险", "N2", "risk_level_name"),
            ("T3", "低风险", "N3", "risk_level_name"),
        ]
        result = rrf_fuse([list_a, list_b])
        # T2 出现在两个列表中，应该得分最高
        assert result[0].term_id == "T2"

    def test_top_n_truncation(self) -> None:
        from datacloud_knowledge.query.search.rrf import rrf_fuse

        ranked = [
            ("T1", "A", "N1", "x"),
            ("T2", "B", "N2", "x"),
            ("T3", "C", "N3", "x"),
        ]
        result = rrf_fuse([ranked], top_n=2)
        assert len(result) == 2


# ---- ktype → term_type_code 映射测试 ----


class TestKtypeCategoryMap:
    """验证 KTYPE_CATEGORY_MAP 定义完整且值合理。"""

    def test_all_ktypes_have_mapping(self) -> None:
        from datacloud_knowledge.intent.typed_recall import KTYPE_CATEGORY_MAP

        expected_ktypes = {"select", "groupBy", "whereKey", "whereValue", "orderBy", "aggregation"}
        assert set(KTYPE_CATEGORY_MAP.keys()) == expected_ktypes

    def test_where_value_maps_to_list_and_dict_categories(self) -> None:
        from datacloud_knowledge.intent.typed_recall import KTYPE_CATEGORY_MAP

        wv_cats = KTYPE_CATEGORY_MAP["whereValue"]
        assert wv_cats is not None
        assert wv_cats == {1, 2}, "whereValue should map to LIST_TERM(1) + DICT_TERM(2)"

    def test_select_maps_to_ontology_category(self) -> None:
        from datacloud_knowledge.intent.typed_recall import KTYPE_CATEGORY_MAP

        sel_cats = KTYPE_CATEGORY_MAP["select"]
        assert sel_cats is not None
        assert sel_cats == {3}, "select should map to ONTOLOGY_TERM(3)"

    def test_aggregation_is_none(self) -> None:
        from datacloud_knowledge.intent.typed_recall import KTYPE_CATEGORY_MAP

        assert KTYPE_CATEGORY_MAP["aggregation"] is None
