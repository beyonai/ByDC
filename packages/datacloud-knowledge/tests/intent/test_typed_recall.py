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
        from datacloud_knowledge.search.rrf import rrf_fuse

        assert rrf_fuse([]) == []

    def test_single_list_preserves_order(self) -> None:
        from datacloud_knowledge.search.rrf import rrf_fuse

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
        from datacloud_knowledge.search.rrf import rrf_fuse

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
        from datacloud_knowledge.search.rrf import rrf_fuse

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


class TestSingleCharFallback:
    """单字符兜底召回只在常规召回全空时启用。"""

    def test_single_char_tsquery_keeps_unique_cjk_chars_only(self) -> None:
        from datacloud_knowledge.intent import batch_recall

        assert batch_recall._single_char_fallback_tsquery("黄升") == "黄 | 升"
        assert batch_recall._single_char_fallback_tsquery("黄黄A&升!") == "黄 | 升"
        assert batch_recall._single_char_fallback_tsquery("task_status") == ""

    def test_fallback_batch_keeps_only_requests_empty_in_all_paths(self) -> None:
        from datacloud_knowledge.intent import batch_recall

        empty_request = batch_recall.RecallRequest(
            map_key="whereValue:黄升",
            keyword="黄升",
            ktype="whereValue",
            type_filter=frozenset({"person_name"}),
            is_per_type=False,
            per_type_limit=0,
            is_value_recall=True,
        )
        hit_request = batch_recall.RecallRequest(
            map_key="select:任务状态",
            keyword="任务状态",
            ktype="select",
            type_filter=frozenset({"prop"}),
            is_per_type=False,
            per_type_limit=0,
        )
        non_cjk_request = batch_recall.RecallRequest(
            map_key="select:task_status",
            keyword="task_status",
            ktype="select",
            type_filter=frozenset({"prop"}),
            is_per_type=False,
            per_type_limit=0,
        )
        batch = batch_recall.PreparedBatch(
            requests=(empty_request, hit_request, non_cjk_request),
            normal_requests=(empty_request, hit_request, non_cjk_request),
            per_type_requests=(),
        )
        path_results = {
            "bm25_and": {"select:任务状态": [("t1", "任务状态", "n1", "prop", "task_status")]},
            "jieba": {},
            "substring": {},
            "vector": {"whereValue:黄升": [("v1", "向量命中", "vn1", "person_name", "vector_hit")]},
        }

        fallback_batch = batch_recall._build_single_char_fallback_batch(batch, path_results)

        assert fallback_batch.requests == (empty_request,)
        assert fallback_batch.normal_requests == (empty_request,)
        assert fallback_batch.per_type_requests == ()

    def test_fallback_dedupes_ranked_rows_by_term_name(self) -> None:
        from datacloud_knowledge.intent import batch_recall

        results = {
            "whereValue:黄升": [
                ("t1", "黄药师", "n1", "person_name", "huang_yaoshi"),
                ("t2", "黄蓉", "n2", "person_name", "huang_rong"),
                ("t3", "黄药师", "n3", "person_alias", "huang_yaoshi_alias"),
            ]
        }

        deduped = batch_recall._dedupe_ranked_rows_by_term_name(results)

        assert deduped == {
            "whereValue:黄升": [
                ("t1", "黄药师", "n1", "person_name", "huang_yaoshi"),
                ("t2", "黄蓉", "n2", "person_name", "huang_rong"),
            ]
        }

    def test_candidate_dedupe_preserves_first_display_name_rank(self) -> None:
        from datacloud_knowledge.intent import batch_recall

        candidates = [
            {"term_id": "t1", "term_name": "王重阳"},
            {"term_id": "t2", "term_name": "黄药师"},
            {"term_id": "t3", "term_name": "王重阳"},
        ]

        deduped = batch_recall._dedupe_candidates_by_term_name(candidates)

        assert [candidate["term_id"] for candidate in deduped] == ["t1", "t2"]

    def test_layered_fallback_ignores_vector_but_respects_keyword_hits(self, monkeypatch) -> None:
        from datacloud_knowledge.intent import batch_recall

        empty_request = batch_recall.RecallRequest(
            map_key="whereValue:黄升",
            keyword="黄升",
            ktype="whereValue",
            type_filter=frozenset({"person_name"}),
            is_per_type=False,
            per_type_limit=0,
            is_value_recall=True,
        )
        normal_hit_request = batch_recall.RecallRequest(
            map_key="whereValue:黄蓉",
            keyword="黄蓉",
            ktype="whereValue",
            type_filter=frozenset({"person_name"}),
            is_per_type=False,
            per_type_limit=0,
            is_value_recall=True,
        )
        batch = batch_recall.PreparedBatch(
            requests=(empty_request, normal_hit_request),
            normal_requests=(empty_request, normal_hit_request),
            per_type_requests=(),
        )
        result = {
            "whereValue:黄升": [
                {
                    "term_id": "vector",
                    "term_name": "王重阳",
                    "term_type_code": "person_name",
                    "name_id": "vector_name",
                    "term_code": "wang_chongyang",
                }
            ],
            "whereValue:黄蓉": [
                {
                    "term_id": "normal",
                    "term_name": "黄蓉",
                    "term_type_code": "person_name",
                    "name_id": "normal_name",
                    "term_code": "huang_rong",
                }
            ],
        }

        def _fake_fallback(
            fallback_batch: batch_recall.PreparedBatch,
            *,
            top_k: int,
        ) -> dict[str, list[tuple[str, str, str, str, str]]]:
            assert top_k == 2
            assert [request.map_key for request in fallback_batch.requests] == ["whereValue:黄升"]
            return {"whereValue:黄升": [("fb", "黄药师", "fb_name", "person_name", "huang_yaoshi")]}

        monkeypatch.setattr(batch_recall, "_batch_single_char_fallback", _fake_fallback)

        batch_recall._add_layered_single_char_fallback_results(
            result,
            (empty_request, normal_hit_request),
            [(batch_recall.ScopeRecallLayer(scope_code="scene", weight=1.0), result)],
            [(batch_recall.ScopeRecallLayer(scope_code="scene", weight=1.0), batch)],
            [
                (
                    batch_recall.ScopeRecallLayer(scope_code="scene", weight=1.0),
                    {
                        "bm25_and": {
                            "whereValue:黄蓉": [
                                ("normal", "黄蓉", "normal_name", "person_name", "huang_rong")
                            ]
                        },
                        "jieba": {},
                        "substring": {},
                        "vector": {
                            "whereValue:黄升": [
                                ("vector", "王重阳", "vector_name", "person_name", "wang_chongyang")
                            ]
                        },
                    },
                )
            ],
            top_k=2,
            rrf_k=60,
        )

        assert [candidate["term_name"] for candidate in result["whereValue:黄升"]] == [
            "王重阳",
            "黄药师",
        ]
        assert [candidate["term_name"] for candidate in result["whereValue:黄蓉"]] == ["黄蓉"]
