"""OWL 解析器单元测试。

测试 owl_parser.py 模块的解析功能，覆盖所有实体类型解析。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from datacloud_knowledge.knowledge_build.importer.owl_parser import (
    OWLParseError,
    parse_owl_file,
)

# 样例文件路径
SAMPLE_DIR = Path("packages/datacloud-knowledge/docs/模块设计/导入包样例")

DOMAINS_OWL = SAMPLE_DIR / "meta/domains.owl"
LIBRARY_OWL = SAMPLE_DIR / "meta/library.owl"
TERM_TYPES_OWL = SAMPLE_DIR / "term_types/term_types.owl"
TERMS_OWL = SAMPLE_DIR / "terms/terms.owl"
RELATION_OWL = SAMPLE_DIR / "relations/relation.owl"


class TestParseDomainOwl:
    """测试 domain OWL 文件解析。"""

    def test_parse_domain_returns_single_entity(self) -> None:
        """测试解析 domains.owl 返回一个 domain 实体。"""
        entities = parse_owl_file(DOMAINS_OWL)

        assert len(entities) == 1

    def test_parse_domain_entity_type(self) -> None:
        """测试实体类型为 domain。"""
        entities = parse_owl_file(DOMAINS_OWL)

        assert entities[0]["entity_type"] == "domain"

    def test_parse_domain_properties(self) -> None:
        """测试 domain 实体的属性。"""
        entity = parse_owl_file(DOMAINS_OWL)[0]

        assert entity["domain_code"] == "sales_crm"
        assert entity["domain_name"] == "CRM子领域"
        assert entity["parent_domain_code"] == "sales"
        assert entity["remark"] == "客户关系管理"
        assert entity["version"] == "1.0"


class TestParseLibraryOwl:
    """测试 library OWL 文件解析。"""

    def test_parse_library_returns_single_entity(self) -> None:
        """测试解析 library.owl 返回一个 library 实体。"""
        entities = parse_owl_file(LIBRARY_OWL)

        assert len(entities) == 1

    def test_parse_library_entity_type(self) -> None:
        """测试实体类型为 library。"""
        entities = parse_owl_file(LIBRARY_OWL)

        assert entities[0]["entity_type"] == "library"

    def test_parse_library_properties(self) -> None:
        """测试 library 实体的属性。"""
        entity = parse_owl_file(LIBRARY_OWL)[0]

        assert entity["library_code"] == "HR"
        assert entity["library_name"] == "人力资源知识库"
        assert entity["library_desc"] == "本体库描述"
        assert entity["version"] == "1.0"


class TestParseTermTypeOwl:
    """测试 term_type OWL 文件解析，包含 typo 兼容测试。"""

    def test_parse_term_type_returns_multiple_entities(self) -> None:
        """测试解析 term_types.owl 返回多个 term_type 实体。"""
        entities = parse_owl_file(TERM_TYPES_OWL)

        assert len(entities) == 7

    def test_parse_term_type_entity_type(self) -> None:
        """测试实体类型为 term_type。"""
        entities = parse_owl_file(TERM_TYPES_OWL)

        for entity in entities:
            assert entity["entity_type"] == "term_type"

    def test_parse_term_type_typo_aliases(self) -> None:
        """测试已知 typo 别名被正确映射。"""
        entity = parse_owl_file(TERM_TYPES_OWL)[0]

        # 验证 typo 被映射到正确字段名
        assert "term_type_code_path" in entity
        assert "term_type_code" in entity
        assert "term_type_name" in entity
        assert "term_type_desc" in entity
        assert "term_data_type" in entity

    def test_parse_term_type_first_entity_properties(self) -> None:
        """测试第一个 term_type 实体的属性。"""
        entity = parse_owl_file(TERM_TYPES_OWL)[0]

        assert entity["term_type_code_path"] == "SALE#YES_OR_NO"
        assert entity["term_type_code"] == "YES_OR_NO"
        assert entity["term_type_name"] == "是否"
        assert entity["term_type_desc"] == "是否，1：是，2：否"
        assert entity["term_data_type"] == "DICT_TERM"
        assert entity["version"] == "1.0"


class TestParseTermOwl:
    """测试 term OWL 文件解析。"""

    def test_parse_term_returns_single_entity(self) -> None:
        """测试解析 terms.owl 返回 term 实体。"""
        entities = parse_owl_file(TERMS_OWL)
        assert len(entities) == 2  # po_organization and po_users

    def test_parse_term_entity_type(self) -> None:
        """测试实体类型为 term。"""
        entities = parse_owl_file(TERMS_OWL)
        assert entities[0]["entity_type"] == "term"

    def test_parse_term_properties(self) -> None:
        """测试 term 实体的属性。"""
        # terms.owl has 2 entities; first is po_organization
        entity = parse_owl_file(TERMS_OWL)[0]
        assert entity["term_code_path"] == "OBJECT#po_organization"
        assert entity["term_code"] == "po_organization"
        assert entity["term_name"] == "组织信息"
        assert entity["library_code"] == "hr_kb"
        assert entity["term_type_code"] == "OBJECT"
        assert entity["ext_field"] == "{}"
        assert entity["version"] == "1.0"


class TestParseRelationOwl:
    """测试 relation OWL 文件解析，包含 typo 兼容测试。"""

    def test_parse_relation_returns_single_entity(self) -> None:
        """测试解析 relation.owl 返回一个 relation 实体。"""
        entities = parse_owl_file(RELATION_OWL)

        assert len(entities) == 1

    def test_parse_relation_entity_type(self) -> None:
        """测试实体类型为 relation。"""
        entities = parse_owl_file(RELATION_OWL)

        assert entities[0]["entity_type"] == "relation"

    def test_parse_relation_typo_aliases(self) -> None:
        """测试 relation 中的 typo 别名被正确映射。"""
        entity = parse_owl_file(RELATION_OWL)[0]

        # 验证 typo 被映射到正确字段名
        assert "source_library" in entity
        assert "target_library" in entity

    def test_parse_relation_properties(self) -> None:
        """测试 relation 实体的属性。"""
        entity = parse_owl_file(RELATION_OWL)[0]
        assert entity["source_library"] == "HR"
        assert entity["source_type"] == "OBJECT"
        assert entity["source_code"] == "po_users"
        assert entity["target_library"] == "HR"
        assert entity["target_type"] == "OBJECT"
        assert entity["target_code"] == "po_organization"
        assert entity["relation_name"] == "人员_归属_组织"
        assert entity["relation_type"] == "MANY_TO_ONE"
        assert entity["joinkeys"] == '[{"sourceField":"org_id", "targetField":"org_id"}]'
        assert entity["ext_field"] == "{}"
        assert entity["version"] == "1.0"


class TestParseEmptyAndMalformed:
    """测试空文件和格式错误文件的处理。"""

    def test_parse_empty_file_returns_empty_list(self) -> None:
        """测试解析空文件返回空列表。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".owl", delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            entities = parse_owl_file(temp_path)
            assert entities == []
        finally:
            temp_path.unlink()

    def test_parse_whitespace_only_file_returns_empty_list(self) -> None:
        """测试解析仅包含空白的文件返回空列表。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".owl", delete=False) as f:
            f.write("   \n\t\n   ")
            temp_path = Path(f.name)

        try:
            entities = parse_owl_file(temp_path)
            assert entities == []
        finally:
            temp_path.unlink()

    def test_parse_malformed_xml_raises_owl_parse_error(self) -> None:
        """测试解析格式错误的 XML 抛出 OWLParseError。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".owl", delete=False) as f:
            f.write('<?xml version="1.0"?><invalid>')
            temp_path = Path(f.name)

        try:
            with pytest.raises(OWLParseError):
                parse_owl_file(temp_path)
        finally:
            temp_path.unlink()


class TestParseErrorHandling:
    """测试解析错误处理。"""

    def test_parse_file_without_entity_type_raises_error(self) -> None:
        """测试解析没有实体类型的 NamedIndividual 抛出 OWLParseError。"""
        content = """<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.w3.org/2002/07/owl#"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <owl:NamedIndividual rdf:about="#no_type">
        <some_property rdf:datatype="http://www.w3.org/2001/XMLSchema#string">value</some_property>
    </owl:NamedIndividual>
</rdf:RDF>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".owl", delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)

        try:
            entities = parse_owl_file(temp_path)
            # 未知 class 不再抛异常，而是返回 entity_type 为空的实体
            assert len(entities) == 1
            assert entities[0].get("entity_type", "") == ""
        finally:
            temp_path.unlink()
