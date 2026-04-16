"""
OQL 跨源执行器测试
"""

import pytest
from datacloud_data_sdk.oql import OQLError, OQLErrorCode
from datacloud_data_sdk.oql.cross_source_executor import classify_include_links
from datacloud_data_sdk.oql.memory_merger import MemoryMerger

from tests.datacloud_data.fixtures.oql_test_data import (
    MockRegistry,
)


class TestClassifyIncludeLinks:
    """测试 include_links 分类"""

    def test_same_source_link(self):
        """同源关联"""
        registry = MockRegistry()
        root_cls = registry.get_class("Flight")

        same_source, cross_source = classify_include_links(
            [{"path": "crew", "select": ["crew_name"]}], root_cls, registry
        )

        assert len(same_source) == 1
        assert len(cross_source) == 0

    def test_cross_source_link(self):
        """跨源关联"""
        registry = MockRegistry()
        root_cls = registry.get_class("Flight")

        same_source, cross_source = classify_include_links(
            [{"path": "crew.manual", "select": ["manual_name"]}], root_cls, registry
        )

        assert len(same_source) == 0
        assert len(cross_source) == 1

    def test_unknown_relation(self):
        """未知关系"""
        registry = MockRegistry()
        root_cls = registry.get_class("Flight")

        with pytest.raises(OQLError) as exc_info:
            classify_include_links([{"path": "unknown_rel", "select": []}], root_cls, registry)
        assert exc_info.value.code == OQLErrorCode.OQL_ERR_UNKNOWN_RELATION


class TestMemoryMerger:
    """测试内存合并"""

    def test_left_join_with_match(self):
        """有匹配的 LEFT JOIN"""
        main = [
            {"id": 1, "name": "A"},
            {"id": 2, "name": "B"},
        ]
        sub = [
            {"id": 1, "value": "X"},
            {"id": 2, "value": "Y"},
        ]

        result = MemoryMerger.left_join(main, sub, "id", "id", "sub")

        assert len(result) == 2
        assert result[0]["sub__value"] == "X"
        assert result[1]["sub__value"] == "Y"

    def test_left_join_no_match(self):
        """无匹配的 LEFT JOIN"""
        main = [
            {"id": 1, "name": "A"},
            {"id": 3, "name": "C"},
        ]
        sub = [
            {"id": 1, "value": "X"},
        ]

        result = MemoryMerger.left_join(main, sub, "id", "id", "sub")

        assert len(result) == 2
        assert result[0]["sub__value"] == "X"
        assert result[1]["sub__value"] is None

    def test_left_join_one_to_many(self):
        """一对多 LEFT JOIN"""
        main = [
            {"id": 1, "name": "A"},
        ]
        sub = [
            {"id": 1, "value": "X"},
            {"id": 1, "value": "Y"},
        ]

        result = MemoryMerger.left_join(main, sub, "id", "id", "sub")

        assert len(result) == 2
        assert result[0]["sub__value"] == "X"
        assert result[1]["sub__value"] == "Y"

    def test_left_join_empty_sub(self):
        """子表为空的 LEFT JOIN"""
        main = [
            {"id": 1, "name": "A"},
        ]
        sub = []

        result = MemoryMerger.left_join(main, sub, "id", "id", "sub")

        assert len(result) == 1
        assert result[0]["id"] == 1
