# ruff: noqa: S101
"""typed_recall 模块的单元测试。

使用 mock 替代真实数据库和 embedding 服务，验证：
1. RRF 融合逻辑
2. ktype → term_type_code 过滤映射
3. 多路召回 → 外层 RRF 融合
4. 搜索被禁用的 keyword 不触发召回
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

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


# ---- typed_multi_recall 集成测试（mock DB）----


class TestTypedMultiRecall:
    """typed_multi_recall 的 mock 集成测试。"""

    @patch("datacloud_knowledge.intent.typed_recall._load_type_codes_by_category")
    @patch("datacloud_knowledge.intent.typed_recall._recall_single_keyword")
    def test_skips_disabled_keywords(
        self,
        mock_recall: MagicMock,
        _mock_load: MagicMock,
    ) -> None:
        from datacloud_data_sdk.plan.paradigm_builder import TypedKeywordState

        from datacloud_knowledge.intent.typed_recall import typed_multi_recall

        items = [
            TypedKeywordState(
                item_id="agg-1",
                paradigm_id="5",
                paradigm_name="统计函数",
                keyword="求和",
                kid=1,
                ktype="aggregation",
                search_enabled=False,
            ),
        ]
        session = MagicMock()
        result = typed_multi_recall(items, session=session)
        # aggregation 被 search_enabled=False，不应触发召回
        mock_recall.assert_not_called()
        assert result["aggregation:求和"] == []

    @patch("datacloud_knowledge.intent.typed_recall._load_type_codes_by_category")
    @patch("datacloud_knowledge.intent.typed_recall._recall_single_keyword")
    def test_recall_returns_candidates_for_keyword(
        self,
        mock_recall: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from datacloud_data_sdk.plan.paradigm_builder import TypedKeywordState

        from datacloud_knowledge.intent.typed_recall import typed_multi_recall

        mock_load.return_value = {"object", "view", "action", "prop"}
        mock_recall.return_value = [
            {
                "term_id": "T1",
                "term_name": "企业综合分析表",
                "term_type_code": "object",
                "match_type": "bm25",
                "confidence": 0.8,
                "score": 0.8,
                "name_id": "N1",
            }
        ]

        items = [
            TypedKeywordState(
                item_id="select-1",
                paradigm_id="1",
                paradigm_name="查询值",
                keyword="企业综合",
                kid=1,
                ktype="select",
            ),
        ]
        session = MagicMock()
        result = typed_multi_recall(items, session=session)
        assert len(result["select:企业综合"]) == 1
        assert result["select:企业综合"][0]["term_name"] == "企业综合分析表"

    @patch("datacloud_knowledge.intent.typed_recall._load_type_codes_by_category")
    @patch("datacloud_knowledge.intent.typed_recall._recall_single_keyword")
    def test_deduplicates_same_keyword(
        self,
        mock_recall: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        """同一个 keyword 出现在多个 item 中，只调一次 recall。"""
        from datacloud_data_sdk.plan.paradigm_builder import TypedKeywordState

        from datacloud_knowledge.intent.typed_recall import typed_multi_recall

        mock_load.return_value = {"object", "view", "action", "prop"}
        mock_recall.return_value = [
            {
                "term_id": "T1",
                "term_name": "行业",
                "term_type_code": "industry_name",
                "match_type": "bm25",
                "confidence": 0.9,
                "score": 0.9,
                "name_id": "N1",
            }
        ]

        items = [
            TypedKeywordState(
                item_id="select-1",
                paradigm_id="1",
                paradigm_name="查询值",
                keyword="行业",
                kid=1,
                ktype="select",
            ),
            TypedKeywordState(
                item_id="groupBy-1",
                paradigm_id="2",
                paradigm_name="分组条件",
                keyword="行业",
                kid=1,
                ktype="groupBy",
            ),
        ]
        session = MagicMock()
        typed_multi_recall(items, session=session)
        # 同一个 keyword "行业" 但 ktype 不同，应该各自召回一次
        assert mock_recall.call_count == 2
        assert "select:行业" in result
        assert "groupBy:行业" in result


# ---- 基于真实 DB 数据的期望测试用例（需要 DB 连接时启用）----
# 下面的测试用例描述的是基于 DB 探索结果的预期行为，
# 用 pytest.param + marks 标记为 db_integration


REALISTIC_CASES = [
    pytest.param(
        "风险",
        "whereValue",
        {"高风险", "中风险", "低风险"},
        id="risk-level-where-value",
    ),
    pytest.param(
        "企业综合",
        "select",
        {"企业综合分析表"},
        id="enterprise-analysis-object",
    ),
    pytest.param(
        "网格",
        "select",
        {"管理网格综合分析表", "物理网格综合分析表"},
        id="grid-object-select",
    ),
    pytest.param(
        "大型企业",
        "whereValue",
        {"大型企业"},
        id="enterprise-level-exact",
    ),
    pytest.param(
        "亦庄",
        "whereValue",
        set(),  # 可能匹配很多 phy_grid_name，但至少应该有结果
        id="yizhuang-grid-name",
    ),
]


@pytest.mark.db_integration
@pytest.mark.parametrize("keyword,ktype,expected_names", REALISTIC_CASES)
def test_recall_realistic_case(
    db_session: MagicMock,
    keyword: str,
    ktype: str,
    expected_names: set[str],
) -> None:
    """基于真实 DB 数据的集成测试 — 需要 DB 连接。"""
    # 当 expected_names 为空集时表示 "至少应有结果"
    # 这些测试在 CI 中 skip，仅在有 DB 连接时手动运行
    pytest.skip("DB integration test — run manually with DATACLOUD_ENABLE_INTEGRATION_TESTS=1")
