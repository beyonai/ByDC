"""OWL 转换器单元测试。

测试 owl_converter.py 模块的转换功能，覆盖所有公开函数。
"""

from __future__ import annotations

import pytest
from datacloud_knowledge.ingestion.owl_import.importer.owl_converter import (
    RELATION_TYPE_TO_CARDINALITY,
    convert_domain,
    convert_relation,
    convert_term,
    convert_term_type,
    extract_knowledge_records,
    map_cardinality,
    parse_json_field,
)


class TestParseJsonField:
    """测试 parse_json_field 函数。"""

    def test_parse_valid_json_string(self) -> None:
        """测试解析有效的 JSON 字符串。"""
        result = parse_json_field('{"key": "value"}', default=None)
        assert result == {"key": "value"}

    def test_parse_valid_json_list(self) -> None:
        """测试解析有效的 JSON 列表字符串。"""
        result = parse_json_field('["a", "b", "c"]', default=[])
        assert result == ["a", "b", "c"]

    def test_parse_none_returns_default(self) -> None:
        """测试 None 输入返回默认值。"""
        result = parse_json_field(None, default="default")
        assert result == "default"

    def test_parse_empty_string_returns_default(self) -> None:
        """测试空字符串返回默认值。"""
        result = parse_json_field("", default="default")
        assert result == "default"

    def test_parse_whitespace_string_returns_default(self) -> None:
        """测试空白字符串返回默认值。"""
        result = parse_json_field("   ", default="default")
        assert result == "default"

    def test_parse_malformed_json_returns_default(self) -> None:
        """测试 malformed JSON 返回默认值，不抛异常。"""
        result = parse_json_field("{invalid json}", default={"fallback": True})
        assert result == {"fallback": True}

    def test_parse_invalid_type_returns_default(self) -> None:
        """测试非字符串类型返回默认值。"""
        result = parse_json_field(12345, default="default")
        assert result == "default"

    def test_parse_list_input_returns_list(self) -> None:
        """测试列表输入直接返回。"""
        input_list = ["a", "b"]
        result = parse_json_field(input_list, default=[])
        assert result is input_list

    def test_parse_dict_input_returns_dict(self) -> None:
        """测试字典输入直接返回。"""
        input_dict = {"key": "value"}
        result = parse_json_field(input_dict, default={})
        assert result is input_dict


class TestMapCardinality:
    """测试 map_cardinality 函数。"""

    def test_map_one_to_one(self) -> None:
        """测试 ONE_TO_ONE 映射。"""
        result = map_cardinality("ONE_TO_ONE")
        assert result == "1:1"

    def test_map_one_to_many(self) -> None:
        """测试 ONE_TO_MANY 映射。"""
        result = map_cardinality("ONE_TO_MANY")
        assert result == "1:N"

    def test_map_many_to_one(self) -> None:
        """测试 MANY_TO_ONE 映射。"""
        result = map_cardinality("MANY_TO_ONE")
        assert result == "N:1"

    def test_map_many_to_many(self) -> None:
        """测试 MANY_TO_MANY 映射。"""
        result = map_cardinality("MANY_TO_MANY")
        assert result == "N:N"

    def test_map_lowercase(self) -> None:
        """测试小写输入。"""
        result = map_cardinality("one_to_one")
        assert result == "1:1"

    def test_map_with_whitespace(self) -> None:
        """测试带空白的输入。"""
        result = map_cardinality("  ONE_TO_ONE  ")
        assert result == "1:1"

    def test_map_none_returns_none(self) -> None:
        """测试 None 输入返回 None。"""
        result = map_cardinality(None)
        assert result is None

    def test_map_empty_string_returns_none(self) -> None:
        """测试空字符串返回 None。"""
        result = map_cardinality("")
        assert result is None

    def test_map_unknown_type_returns_none(self) -> None:
        """测试未知 relation_type 返回 None。"""
        result = map_cardinality("UNKNOWN_TYPE")
        assert result is None


class TestConvertDomain:
    """测试 convert_domain 函数。"""

    def test_convert_domain_basic(self) -> None:
        """测试基本字段转换。"""
        owl_entity = {
            "domain_code": "sales",
            "domain_name": "销售",
            "parent_domain_code": "business",
            "remark": "销售领域描述",
        }

        result = convert_domain(owl_entity)

        assert result["domain_code"] == "sales"
        assert result["domain_name"] == "销售"
        assert result["parent_code"] == "business"
        assert result["domain_desc"] == "销售领域描述"

    def test_convert_domain_missing_fields(self) -> None:
        """测试缺失字段返回 None。"""
        owl_entity = {"domain_code": "sales"}

        result = convert_domain(owl_entity)

        assert result["domain_code"] == "sales"
        assert result["domain_name"] is None
        assert result["parent_code"] is None
        assert result["domain_desc"] is None

    def test_convert_domain_empty_entity(self) -> None:
        """测试空实体。"""
        result = convert_domain({})

        assert result["domain_code"] is None
        assert result["domain_name"] is None
        assert result["parent_code"] is None
        assert result["domain_desc"] is None


class TestConvertTermType:
    """测试 convert_term_type 函数。"""

    def test_convert_term_type_basic(self) -> None:
        """测试基本字段转换。"""
        owl_entity = {
            "term_type_code": "OBJECT",
            "term_type_name": "对象",
            "term_type_desc": "对象类型",
            "term_data_type": "DICT_TERM",
            "term_type_code_path": "SALE#OBJECT",
        }

        result = convert_term_type(owl_entity)

        assert result["type_code"] == "OBJECT"
        assert result["type_name"] == "对象"
        assert result["type_desc"] == "对象类型"
        assert result["type_category"] == "DICT_TERM"
        assert result["domain_code"] == "SALE"

    def test_convert_term_type_extract_domain_from_path(self) -> None:
        """测试从 code_path 提取 domain_code。"""
        owl_entity = {
            "term_type_code": "YES_OR_NO",
            "term_type_code_path": "HR#YES_OR_NO",
        }

        result = convert_term_type(owl_entity)

        assert result["domain_code"] == "HR"

    def test_convert_term_type_typo_aliases(self) -> None:
        """测试 typo 别名映射。

        owl_parser 已将 trem_* 正序化为 term_*，此处测试 converter 对正序化后字段的处理。
        """
        owl_entity = {
            "term_type_code": "OBJECT",
            "term_type_name": "对象",
            "term_type_desc": "对象类型",
            "term_data_type": "DICT_TERM",
            "term_type_code_path": "SALE#OBJECT",
        }

        result = convert_term_type(owl_entity)

        assert result["type_code"] == "OBJECT"
        assert result["type_name"] == "对象"
        assert result["type_category"] == "DICT_TERM"

    def test_convert_term_type_missing_path_returns_none(self) -> None:
        """测试缺失 path 时 domain_code 为 None。"""
        owl_entity = {"term_type_code": "OBJECT"}

        result = convert_term_type(owl_entity)

        assert result["domain_code"] is None


class TestConvertTerm:
    """测试 convert_term 函数。"""

    def test_convert_term_basic(self) -> None:
        """测试基本字段转换。"""
        owl_entity = {
            "term_code": "po_users",
            "term_name": "人员",
            "term_desc": "人员描述",
            "library_code": "HR",
            "term_type_code": "OBJECT",
            "domain_code": "HR",
            "synonyms": '["员工", "用户"]',
        }

        result = convert_term(owl_entity)

        assert result["term_code"] == "po_users"
        assert result["term_name"] == "人员"
        assert result["term_desc"] == "人员描述"
        assert result["library_code"] == "HR"
        assert result["term_type_code"] == "OBJECT"
        assert result["domain_code"] == "HR"

    def test_convert_term_with_synonyms(self) -> None:
        """测试同义词解析。"""
        owl_entity = {
            "term_name": "人员",
            "synonyms": '["员工", "用户"]',
        }

        result = convert_term(owl_entity)

        assert result["synonyms"] == ["员工", "用户"]
        assert result["aliases"] == ["员工", "用户"]

    def test_convert_term_synonyms_exclude_self(self) -> None:
        """测试同义词排除自身。"""
        owl_entity = {
            "term_name": "人员",
            "synonyms": '["人员", "员工"]',
        }

        result = convert_term(owl_entity)

        assert result["synonyms"] == ["人员", "员工"]
        assert result["aliases"] == ["员工"]

    def test_convert_term_normalize_synonyms(self) -> None:
        """测试同义词清洗（去除空白）。"""
        owl_entity = {
            "term_name": "人员",
            "synonyms": '["  员工  ", "用户", ""]',
        }

        result = convert_term(owl_entity)

        assert result["synonyms"] == ["员工", "用户"]

    def test_convert_term_malformed_synonyms_returns_empty(self) -> None:
        """测试 malformed synonyms JSON 返回空列表。"""
        owl_entity = {
            "term_name": "人员",
            "synonyms": "not valid json",
        }

        result = convert_term(owl_entity)

        assert result["synonyms"] == []

    def test_convert_term_non_list_synonyms_returns_empty(self) -> None:
        """测试非列表 synonyms 返回空列表。"""
        owl_entity = {
            "term_name": "人员",
            "synonyms": '{"key": "value"}',
        }

        result = convert_term(owl_entity)

        assert result["synonyms"] == []

    def test_convert_term_missing_domain_code(self) -> None:
        """测试缺失 domain_code 返回 None。"""
        owl_entity = {
            "term_name": "人员",
            "term_type_code": "OBJECT",
        }

        result = convert_term(owl_entity)

        assert result["domain_code"] is None


class TestConvertRelation:
    """测试 convert_relation 函数。"""

    def test_convert_relation_basic(self) -> None:
        """测试基本字段转换。"""
        owl_entity = {
            "source_library": "HR",
            "source_type": "术语类型",
            "source_code": "po_users",
            "target_library": "HR",
            "target_type": "术语类型",
            "target_code": "po_organization",
            "relation_name": "人员_归属_组织",
            "relation_type": "MANY_TO_ONE",
            "joinkeys": '[{"sourceField": "org_id", "targetField": "org_id"}]',
            "ext_field": '{"custom": "value"}',
        }

        result = convert_relation(owl_entity)

        assert result["source_term_code"] == "HR#term_type#po_users"
        assert result["target_term_code"] == "HR#term_type#po_organization"
        assert result["relation_name"] == "人员_归属_组织"
        assert result["cardinality"] == "N:1"
        # joinkeys 合并到 ext_field 中
        import json

        ext = json.loads(result["ext_field"])
        assert ext["joinkeys"] == [{"sourceField": "org_id", "targetField": "org_id"}]
        assert ext["custom"] == "value"

    def test_convert_relation_with_cardinality_mapping(self) -> None:
        """测试不同 relation_type 的 cardinality 映射。"""
        test_cases = [
            ("ONE_TO_ONE", "1:1"),
            ("ONE_TO_MANY", "1:N"),
            ("MANY_TO_ONE", "N:1"),
            ("MANY_TO_MANY", "N:N"),
        ]

        for relation_type, expected_cardinality in test_cases:
            owl_entity = {
                "source_library": "LIB",
                "source_type": "TYPE",
                "source_code": "A",
                "target_library": "LIB",
                "target_type": "TYPE",
                "target_code": "B",
                "relation_type": relation_type,
            }
            result = convert_relation(owl_entity)
            assert result["cardinality"] == expected_cardinality

    def test_convert_relation_malformed_joinkeys_returns_empty(self) -> None:
        """测试 malformed joinkeys JSON 返回空列表。"""
        owl_entity = {
            "source_library": "LIB",
            "source_type": "TYPE",
            "source_code": "A",
            "target_library": "LIB",
            "target_type": "TYPE",
            "target_code": "B",
            "joinkeys": "not valid json",
        }

        result = convert_relation(owl_entity)

        import json

        ext = json.loads(result["ext_field"])
        assert ext["joinkeys"] == []

    def test_convert_relation_non_list_joinkeys_returns_empty(self) -> None:
        """测试非列表 joinkeys 返回空列表。"""
        owl_entity = {
            "source_library": "LIB",
            "source_type": "TYPE",
            "source_code": "A",
            "target_library": "LIB",
            "target_type": "TYPE",
            "target_code": "B",
            "joinkeys": {"key": "value"},
        }

        result = convert_relation(owl_entity)

        import json

        ext = json.loads(result["ext_field"])
        assert ext["joinkeys"] == []

    def test_convert_relation_missing_optional_fields(self) -> None:
        """测试缺失可选字段。"""
        owl_entity = {
            "source_library": "HR",
            "source_type": "术语类型",
            "source_code": "po_users",
            "target_library": "HR",
            "target_type": "术语类型",
            "target_code": "po_organization",
        }

        result = convert_relation(owl_entity)

        assert result["source_term_code"] == "HR#term_type#po_users"
        assert result["target_term_code"] == "HR#term_type#po_organization"
        assert result["relation_name"] is None
        assert result["cardinality"] is None
        import json

        ext = json.loads(result["ext_field"])
        assert ext["joinkeys"] == []

    def test_convert_relation_malformed_ext_field(self) -> None:
        """测试 malformed ext_field 解析为空字典。"""
        owl_entity = {
            "source_library": "LIB",
            "source_type": "TYPE",
            "source_code": "A",
            "target_library": "LIB",
            "target_type": "TYPE",
            "target_code": "B",
            "ext_field": "not valid json",
        }

        result = convert_relation(owl_entity)

        import json

        ext = json.loads(result["ext_field"])
        assert ext["joinkeys"] == []
        assert len(ext) == 1  # 只有 joinkeys


class TestExtractKnowledgeRecords:
    """测试 extract_knowledge_records 函数。"""

    def test_extract_knowledge_records_basic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试知识记录提取与字段映射。"""
        generated_ids = iter(["kid-1", "kid-2"])
        monkeypatch.setattr(
            "datacloud_knowledge.ingestion.owl_import.importer.owl_converter._next_snowflake_id",
            lambda: next(generated_ids),
        )

        owl_term = {
            "terms_knowledge": '[{"name":"员工手册","content":"员工手册信息"}, {"name":"绩效规则","content":"绩效规则详情"}]'
        }

        result = extract_knowledge_records(owl_term, term_id="term-123")

        assert result == [
            {
                "knowledge_id": "kid-1",
                "term_id": "term-123",
                "desc_summary": "员工手册",
                "desc": "员工手册信息",
            },
            {
                "knowledge_id": "kid-2",
                "term_id": "term-123",
                "desc_summary": "绩效规则",
                "desc": "绩效规则详情",
            },
        ]

    def test_extract_knowledge_records_accepts_list_input(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """测试已解析列表输入。"""
        monkeypatch.setattr(
            "datacloud_knowledge.ingestion.owl_import.importer.owl_converter._next_snowflake_id",
            lambda: "kid-1",
        )

        owl_term = {
            "terms_knowledge": [{"name": "员工手册", "content": "员工手册信息"}],
        }

        result = extract_knowledge_records(owl_term, term_id="term-123")

        assert result == [
            {
                "knowledge_id": "kid-1",
                "term_id": "term-123",
                "desc_summary": "员工手册",
                "desc": "员工手册信息",
            }
        ]

    def test_extract_knowledge_records_malformed_json_returns_empty(self) -> None:
        """测试 malformed JSON 返回空列表。"""
        owl_term = {"terms_knowledge": "not valid json"}

        result = extract_knowledge_records(owl_term, term_id="term-123")

        assert result == []

    def test_extract_knowledge_records_non_list_returns_empty(self) -> None:
        """测试非列表 JSON 返回空列表。"""
        owl_term = {"terms_knowledge": '{"name":"员工手册","content":"员工手册信息"}'}

        result = extract_knowledge_records(owl_term, term_id="term-123")

        assert result == []

    def test_extract_knowledge_records_skip_non_dict_items(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """测试跳过非对象知识项。"""
        monkeypatch.setattr(
            "datacloud_knowledge.ingestion.owl_import.importer.owl_converter._next_snowflake_id",
            lambda: "kid-1",
        )
        owl_term = {"terms_knowledge": '["员工手册", {"name":"绩效规则","content":"绩效规则详情"}]'}

        result = extract_knowledge_records(owl_term, term_id="term-123")

        assert result == [
            {
                "knowledge_id": "kid-1",
                "term_id": "term-123",
                "desc_summary": "绩效规则",
                "desc": "绩效规则详情",
            }
        ]


class TestRelationTypeToCardinalityConstant:
    """测试 RELATION_TYPE_TO_CARDINALITY 常量。"""

    def test_constant_contains_all_types(self) -> None:
        """测试常量包含所有关系类型。"""
        assert RELATION_TYPE_TO_CARDINALITY == {
            "ONE_TO_ONE": "1:1",
            "ONE_TO_MANY": "1:N",
            "MANY_TO_ONE": "N:1",
            "MANY_TO_MANY": "N:N",
            # 本体结构关系（owl_gen 生成）
            "HAS_OBJECT": "1:N",
            "HAS_FIELD": "1:N",
            "HAS_ACTION": "1:N",
            "HAS_TERM": "1:N",
        }
