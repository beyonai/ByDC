"""GraphBuilder 单元测试 — add_package / add_terms / add_relations / export_*_graph 方法。

测试 GraphBuilder 将 KPS 对象（TermDef, RelationDef 等）序列化为 rdflib.Graph 的正确性。
验证三元组（类型、属性值、命名空间）与 OWL 格式兼容。
"""

from __future__ import annotations

from datacloud_knowledge.contracts.kps import (
    ActionDef,
    DomainDef,
    KnowledgePackage,
    LibraryDef,
    RelationDef,
    TermDef,
    TermTypeDef,
)
from datacloud_knowledge.ingestion.owl_generate.graph_builder import GraphBuilder
from rdflib import RDF

# ═══════════════════════════════════════════════════════════════════════════════
# GraphBuilder — add_terms 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddTerms:
    """测试 GraphBuilder.add_terms() 方法。"""

    def test_single_term(self) -> None:
        """单个术语三元组验证：类型、属性、term_code_path。"""
        gb = GraphBuilder()
        term = TermDef(
            term_code="by_customer",
            term_name="客户",
            term_type_code="object",
            library_code="L1",
            domain_code="D1",
        )
        gb.add_terms([term])
        g = gb.export_terms_graph()

        # 验证 TermDefinition 类型
        types = {
            str(o) for _s, _p, o in g.triples((None, RDF.type, None))
        }
        assert any("TermDefinition" in t for t in types)

        # 验证 term_code_path = L1#object#by_customer
        code_paths = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("term_code_path")
        }
        assert "L1#object#by_customer" in code_paths

    def test_term_with_parent(self) -> None:
        """带有 parent_term_code 的术语在图中包含 parent_term_code 属性。"""
        gb = GraphBuilder()
        term = TermDef(
            term_code="SIGNED",
            term_name="签约成功",
            term_type_code="opp_status",
            library_code="L1",
            domain_code="D1",
            parent_term_code="status",
        )
        gb.add_terms([term])
        g = gb.export_terms_graph()

        parent_values = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("parent_term_code")
        }
        assert "status" in parent_values

    def test_term_with_synonyms(self) -> None:
        """同义词序列化为 JSON 数组。"""
        gb = GraphBuilder()
        term = TermDef(
            term_code="customer",
            term_name="客户",
            term_type_code="object",
            library_code="L1",
            domain_code="D1",
            synonyms=("顾客", "Client"),
        )
        gb.add_terms([term])
        g = gb.export_terms_graph()

        syn_values = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("synonyms")
        }
        assert any("顾客" in s for s in syn_values)
        assert any("Client" in s for s in syn_values)

    def test_term_without_parent_has_no_parent_triple(self) -> None:
        """无 parent_term_code 的术语不产生 parent_term_code 三元组。"""
        gb = GraphBuilder()
        term = TermDef(
            term_code="by_customer",
            term_name="客户",
            term_type_code="object",
            library_code="L1",
            domain_code="D1",
        )
        gb.add_terms([term])
        g = gb.export_terms_graph()

        has_parent = any(
            str(_p).endswith("parent_term_code")
            for _s, _p, o in g.triples((None, None, None))
        )
        assert not has_parent

    def test_multiple_terms(self) -> None:
        """多个术语：按个数和 code path 验证。"""
        gb = GraphBuilder()
        terms = [
            TermDef(
                term_code="obj_a", term_name="对象A", term_type_code="object",
                library_code="L1", domain_code="D1",
            ),
            TermDef(
                term_code="prop_x", term_name="属性X", term_type_code="prop",
                library_code="L1", domain_code="D1",
            ),
        ]
        gb.add_terms(terms)
        g = gb.export_terms_graph()

        code_paths = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("term_code_path")
        }
        assert "L1#object#obj_a" in code_paths
        assert "L1#prop#prop_x" in code_paths

    def test_export_terms_graph_returns_rdflib_graph(self) -> None:
        """export_terms_graph() 返回可序列化的 rdflib.Graph。"""
        gb = GraphBuilder()
        gb.add_terms([
            TermDef(
                term_code="test", term_name="测试", term_type_code="object",
                library_code="L1", domain_code="D1",
            )
        ])
        g = gb.export_terms_graph()
        xml = g.serialize(format="xml")
        assert isinstance(xml, str)
        assert "test" in xml


# ═══════════════════════════════════════════════════════════════════════════════
# GraphBuilder — add_term_types 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddTermTypes:
    """测试 GraphBuilder.add_term_types() 方法。"""

    def test_basic_term_type(self) -> None:
        """基本术语类型：trem_type_code_path, trem_type_name, trem_type_category。"""
        gb = GraphBuilder()
        tt = TermTypeDef(
            type_code="object",
            type_name="对象",
            type_category=3,  # ONTOLOGY_TERM
            type_desc="对象本体术语类型",
        )
        gb.add_term_types([tt])
        g = gb.export_term_types_graph()

        code_paths = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("trem_type_code_path")
        }
        assert "object" in code_paths

        type_names = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("trem_type_name")
        }
        assert "对象" in type_names

        categories = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("trem_type_category")
        }
        assert "3" in categories

    def test_term_type_category_mapping(self) -> None:
        """不同 term_data_type 映射到正确的 type_category 整数。"""
        categories: dict[str, int] = {
            "ONTOLOGY_TERM": 3,
            "LIST_TERM": 1,
            "DICT_TERM": 2,
        }
        gb = GraphBuilder()
        term_types = [
            TermTypeDef(
                type_code=f"type_{name}", type_name=name,
                type_category=cat, type_desc="",
            )
            for name, cat in categories.items()
        ]
        gb.add_term_types(term_types)
        g = gb.export_term_types_graph()

        # 每种类型都在图中
        for name in categories:
            names_found = {
                str(o)
                for _s, _p, o in g.triples((None, None, None))
                if str(_p).endswith("trem_type_name") and str(o) == name
            }
            assert len(names_found) >= 1, f"Term type {name} not found in graph"


# ═══════════════════════════════════════════════════════════════════════════════
# GraphBuilder — add_relations 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddRelations:
    """测试 GraphBuilder.add_relations() 方法。"""

    def test_has_field_relation(self) -> None:
        """HAS_FIELD 关系：sourceTermCode, targetTermCode, relationCategory, extField。"""
        gb = GraphBuilder()
        rel = RelationDef(
            source_term_code="L1#object#by_customer",
            target_term_code="L1#prop#customer_name",
            relation_name="客户_拥有字段_客户名称",
            relation_category="HAS_FIELD",
            cardinality="",
            ext_field={"field_alias": "客户名称"},
        )
        gb.add_relations([rel])
        g = gb.export_relations_graph()

        # sourceTermCode / targetTermCode
        source_codes = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("sourceTermCode")
        }
        assert "L1#object#by_customer" in source_codes

        target_codes = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("targetTermCode")
        }
        assert "L1#prop#customer_name" in target_codes

        # relationCategory = HAS_FIELD
        categories = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("relationCategory")
        }
        assert "HAS_FIELD" in categories

    def test_has_term_relation(self) -> None:
        """HAS_TERM 关系：category 为 HAS_TERM。"""
        gb = GraphBuilder()
        rel = RelationDef(
            source_term_code="L1#opp_status#opp_status",
            target_term_code="L1#opp_status#SIGNED",
            relation_name="opp_status包含签约成功",
            relation_category="HAS_TERM",
            cardinality="",
        )
        gb.add_relations([rel])
        g = gb.export_relations_graph()

        categories = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("relationCategory")
        }
        assert "HAS_TERM" in categories

    def test_many_to_one_relation_with_joinkeys(self) -> None:
        """MANY_TO_ONE 关系包含 joinkeys JSON。"""
        gb = GraphBuilder()
        rel = RelationDef(
            source_term_code="L1#object#obj_a",
            target_term_code="L1#object#obj_b",
            relation_name="A关联B",
            relation_category="MANY_TO_ONE",
            cardinality="",
            joinkeys=({"sourceField": "b_id", "targetField": "id"},),
        )
        gb.add_relations([rel])
        g = gb.export_relations_graph()

        joinkeys_values = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("joinkeys")
        }
        assert any("b_id" in j for j in joinkeys_values)
        assert any("targetField" in j for j in joinkeys_values)

    def test_relation_serializes_to_valid_xml(self) -> None:
        """关系图可正常序列化为 XML。"""
        gb = GraphBuilder()
        rel = RelationDef(
            source_term_code="L1#object#obj_a",
            target_term_code="L1#object#obj_b",
            relation_name="关联",
            relation_category="MANY_TO_ONE",
            cardinality="",
        )
        gb.add_relations([rel])
        g = gb.export_relations_graph()
        xml = g.serialize(format="xml")
        assert isinstance(xml, str)
        assert "TermRelation" in xml

    def test_relation_ext_field_json(self) -> None:
        """ext_field 字典正确序列化为 JSON 字符串。"""
        gb = GraphBuilder()
        rel = RelationDef(
            source_term_code="L1#view#scene_sales",
            target_term_code="L1#prop#customer_name",
            relation_name="视图_拥有字段_客户名称",
            relation_category="HAS_FIELD",
            cardinality="",
            ext_field={"field_alias": "客户名称", "synonyms": ["顾客"]},
        )
        gb.add_relations([rel])
        g = gb.export_relations_graph()

        ext_values = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("extField")
        }
        assert any("field_alias" in e for e in ext_values)
        assert any("客户名称" in e for e in ext_values)

    def test_export_relations_graph_filter_by_category(self) -> None:
        """export_relations_graph(rel_cat) 仅返回指定类别的三元组。"""
        gb = GraphBuilder()
        gb.add_relations([
            RelationDef(
                source_term_code="L1#object#a", target_term_code="L1#object#b",
                relation_name="ab", relation_category="MANY_TO_ONE", cardinality="",
            ),
            RelationDef(
                source_term_code="L1#object#c", target_term_code="L1#prop#d",
                relation_name="cd", relation_category="HAS_FIELD", cardinality="",
                ext_field={"field_alias": "x"},
            ),
            RelationDef(
                source_term_code="L1#opp_status#opp_status", target_term_code="L1#opp_status#X",
                relation_name="HasX", relation_category="HAS_TERM", cardinality="",
            ),
        ])

        # 按 MANY_TO_ONE 过滤
        g_mto = gb.export_relations_graph("MANY_TO_ONE")
        mto_cats = {
            str(o)
            for _s, _p, o in g_mto.triples((None, None, None))
            if str(_p).endswith("relationCategory")
        }
        assert mto_cats == {"MANY_TO_ONE"}

        # 按 HAS_FIELD 过滤
        g_hf = gb.export_relations_graph("HAS_FIELD")
        hf_cats = {
            str(o)
            for _s, _p, o in g_hf.triples((None, None, None))
            if str(_p).endswith("relationCategory")
        }
        assert hf_cats == {"HAS_FIELD"}

        # 不传参 → 全量
        g_all = gb.export_relations_graph()
        all_cats = {
            str(o)
            for _s, _p, o in g_all.triples((None, None, None))
            if str(_p).endswith("relationCategory")
        }
        assert all_cats == {"MANY_TO_ONE", "HAS_FIELD", "HAS_TERM"}


# ═══════════════════════════════════════════════════════════════════════════════
# GraphBuilder — add_package（集成测试）测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestAddPackage:
    """测试 GraphBuilder.add_package() — 全量 KnowledgePackage 加载。"""

    def test_full_package_integration(self) -> None:
        """add_package() 后各 export_*_graph() 方法均产出非空图。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="by_customer", term_name="客户",
                    term_type_code="object", library_code="L1", domain_code="D1",
                ),
                TermDef(
                    term_code="customer_name", term_name="客户名称",
                    term_type_code="prop", library_code="L1", domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#by_customer",
                    target_term_code="L1#prop#customer_name",
                    relation_name="客户_拥有字段_客户名称",
                    relation_category="HAS_FIELD",
                    cardinality="",
                    ext_field={"field_alias": "客户名称"},
                ),
            ),
            term_types=(
                TermTypeDef(
                    type_code="object", type_name="对象",
                    type_category=3, type_desc="对象本体术语",
                ),
                TermTypeDef(
                    type_code="prop", type_name="属性",
                    type_category=3, type_desc="属性术语",
                ),
            ),
            domains=(
                DomainDef(domain_code="D1", domain_name="测试域"),
            ),
            libraries=(
                LibraryDef(library_code="L1", library_name="测试术语库"),
            ),
        )

        gb = GraphBuilder()
        gb.add_package(pkg)

        # terms graph 有内容
        g_terms = gb.export_terms_graph()
        assert len(list(g_terms.subjects())) >= 2

        # term_types graph 有内容
        g_tt = gb.export_term_types_graph()
        assert len(list(g_tt.subjects())) >= 2

        # relations graph 有内容
        g_rel = gb.export_relations_graph()
        assert len(list(g_rel.subjects())) >= 1

    def test_empty_package(self) -> None:
        """空 KnowledgePackage 不抛异常。"""
        pkg = KnowledgePackage(terms=(), relations=())
        gb = GraphBuilder()
        gb.add_package(pkg)

        # 空图可导出
        g = gb.export_terms_graph()
        assert len(list(g.subjects())) == 0

    def test_package_domain_and_library_in_graph(self) -> None:
        """DomainDef 和 LibraryDef 通过 add_domain/add_library 注册到图中。"""
        pkg = KnowledgePackage(
            terms=(),
            relations=(),
            domains=(DomainDef(domain_code="D1", domain_name="测试域"),),
            libraries=(LibraryDef(library_code="L1", library_name="测试术语库"),),
        )
        gb = GraphBuilder()
        gb.add_package(pkg)
        # 访问内部图（full graph），export_terms_graph() 只导出 TermDefinition
        g = gb._graph

        # Domain 在图中
        domain_names = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("domainName")
        }
        assert "测试域" in domain_names

        # Library 在图中
        lib_names = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("libraryName")
        }
        assert "测试术语库" in lib_names

    def test_package_with_actions(self) -> None:
        """KnowledgePackage 包含 Action 时，Action 注册到图中（非 export_terms_graph 范围）。"""
        pkg = KnowledgePackage(
            terms=(),
            relations=(),
            actions=(
                ActionDef(
                    action_code="get_customer",
                    action_name="获取客户",
                    action_type="QUERY",
                    request_url="/api/customer",
                    request_method="GET",
                ),
            ),
        )
        gb = GraphBuilder()
        gb.add_package(pkg)
        g = gb._graph

        action_names = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("actionName")
        }
        assert "获取客户" in action_names

    def test_graph_xml_contains_namespace(self) -> None:
        """序列化 XML 包含 RDF 命名空间。"""
        gb = GraphBuilder()
        gb.add_terms([
            TermDef(
                term_code="test", term_name="测试", term_type_code="object",
                library_code="L1", domain_code="D1",
            )
        ])
        g = gb.export_terms_graph()
        xml = g.serialize(format="xml")
        assert "http://beyond.ai/ontology" in xml
        assert "rdf:RDF" in xml


# ═══════════════════════════════════════════════════════════════════════════════
# 边界情况
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """GraphBuilder 边界情况测试。"""

    def test_empty_synonyms_not_serialized(self) -> None:
        """空 synonyms 不产生三元组。"""
        gb = GraphBuilder()
        gb.add_terms([
            TermDef(
                term_code="test", term_name="测试", term_type_code="object",
                library_code="L1", domain_code="D1", synonyms=(),
            )
        ])
        g = gb.export_terms_graph()
        has_syn = any(
            str(_p).endswith("synonyms")
            for _s, _p, o in g.triples((None, None, None))
        )
        assert not has_syn

    def test_empty_ext_field_not_serialized(self) -> None:
        """ext_field=None 不产生 extField 三元组。"""
        gb = GraphBuilder()
        rel = RelationDef(
            source_term_code="L1#object#a",
            target_term_code="L1#object#b",
            relation_name="ab",
            relation_category="MANY_TO_ONE",
            cardinality="",
            ext_field=None,
        )
        gb.add_relations([rel])
        g = gb.export_relations_graph()
        has_ext = any(
            str(_p).endswith("extField")
            for _s, _p, o in g.triples((None, None, None))
        )
        assert not has_ext

    def test_relation_type_is_term_relation(self) -> None:
        """关系实体的 RDF type 为 TermRelation。"""
        gb = GraphBuilder()
        rel = RelationDef(
            source_term_code="L1#object#a",
            target_term_code="L1#object#b",
            relation_name="ab",
            relation_category="MANY_TO_ONE",
            cardinality="",
        )
        gb.add_relations([rel])
        g = gb.export_relations_graph()
        types = {
            str(o)
            for _s, _p, o in g.triples((None, RDF.type, None))
        }
        assert any("TermRelation" in t for t in types)

    def test_term_definition_type_is_term_definition(self) -> None:
        """术语实体的 RDF type 为 TermDefinition。"""
        gb = GraphBuilder()
        gb.add_terms([
            TermDef(
                term_code="test", term_name="测试", term_type_code="object",
                library_code="L1", domain_code="D1",
            )
        ])
        g = gb.export_terms_graph()
        types = {
            str(o)
            for _s, _p, o in g.triples((None, RDF.type, None))
        }
        assert any("TermDefinition" in t for t in types)

    def test_special_characters_in_code(self) -> None:
        """特殊字符（- . /）在 code 中可正常序列化。"""
        gb = GraphBuilder()
        term = TermDef(
            term_code="prop.with-dot/dash",
            term_name="特殊字符属性",
            term_type_code="prop",
            library_code="L1",
            domain_code="D1",
        )
        gb.add_terms([term])
        g = gb.export_terms_graph()
        code_paths = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("term_code_path")
        }
        assert "L1#prop#prop.with-dot/dash" in code_paths
