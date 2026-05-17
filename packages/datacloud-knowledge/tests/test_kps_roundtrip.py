"""KPS 往返测试 — 验证 KnowledgePackage → GraphBuilder → XML → rdflib 重解析一致性。

端到端测试 _build_object_package/_build_view_package 产出的 KPS
经过 GraphBuilder 序列化后，能被 rdflib 正确重解析，
且关键字段（cardinality、relation_category、term_code_path）保持一致。
"""

from __future__ import annotations

from pathlib import Path

from datacloud_knowledge.contracts.kps import KnowledgePackage
from datacloud_knowledge.ingestion.owl_generate.generator import (
    _build_object_package,
    _build_view_package,
)
from datacloud_knowledge.ingestion.owl_generate.graph_builder import GraphBuilder
from datacloud_knowledge.ingestion.owl_generate.models import (
    Column,
    FieldRole,
    ObjectPropConfig,
    ObjectRelation,
    OwlGenConfig,
    Table,
    TermBinding,
    TermTypeConfig,
    ViewConfig,
    ViewFieldMapping,
)
from datacloud_knowledge.ingestion.owl_generate.renderers.term_types import (
    build_term_type_defs,
    enrich_term_type_names,
)
from rdflib import Graph


def _build_base_config() -> OwlGenConfig:
    """构建最小测试用 OwlGenConfig。"""
    return OwlGenConfig(
        domain_code="D1",
        domain_name="测试域",
        domain_desc="",
        library_code="L1",
        library_name="测试库",
        library_desc="",
        db_code="db_test",
        db_type="mysql",
        db_params={},
        table_codes=["obj_customer"],
        table_names={"obj_customer": "客户表"},
        table_descs={"obj_customer": "客户"},
        term_bindings=[],
        object_relations=[],
        output_dir=Path("/tmp/test-kps-roundtrip"),
        views=[],
    )


def _kps_to_xml(pkg: KnowledgePackage) -> str:
    """将 KnowledgePackage 通过 GraphBuilder 序列化为 XML 字符串。"""
    gb = GraphBuilder()
    gb.add_package(pkg)
    g = gb.export_terms_graph()
    result = g.serialize(format="xml")
    return result if isinstance(result, str) else result.decode("utf-8")


def _kps_relations_to_xml(pkg: KnowledgePackage, category: str | None = None) -> str:
    """将 KnowledgePackage 的关系通过 GraphBuilder 序列化为 XML 字符串。"""
    gb = GraphBuilder()
    gb.add_package(pkg)
    g = gb.export_relations_graph(category)
    result = g.serialize(format="xml")
    return result if isinstance(result, str) else result.decode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# 对象包往返测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestObjectPackageRoundtrip:
    """_build_object_package → GraphBuilder → XML → rdflib 重新解析。"""

    def test_roundtrip_terms_cardinality_non_empty(self) -> None:
        """往返后：所有关系 cardinality 非空且为合法值。"""
        config = _build_base_config()
        config.object_relations = [
            ObjectRelation(
                relation_id="r1",
                source_code="obj_customer",
                target_code="obj_order",
                relation_name="客户拥有订单",
                join_keys=[{"sourceField": "customer_id", "targetField": "customer_id"}],
            )
        ]
        table = Table(
            code="obj_customer",
            name="客户表",
            desc="客户",
            columns=[
                Column(name="customer_id", sql_type="varchar", nullable=False, comment="客户ID"),
                Column(
                    name="customer_name", sql_type="varchar", nullable=False, comment="客户名称"
                ),
            ],
        )
        term_type_defs = build_term_type_defs(config)
        enrich_term_type_names(term_type_defs, [table], config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        # KPS → XML → re-parse
        xml_str = _kps_relations_to_xml(pkg)
        g = Graph()
        g.parse(data=xml_str, format="xml")

        cardinalities = {
            str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("cardinality")
        }
        valid = frozenset({"1:1", "1:N", "N:1", "N:N"})
        assert cardinalities, "cardinality 集合不应为空"
        assert cardinalities.issubset(valid), f"cardinality 包含非法值: {cardinalities - valid}"

    def test_roundtrip_terms_object_term_present(self) -> None:
        """往返后：对象本体术语 term_code_path = L1#object#obj_customer。"""
        config = _build_base_config()
        table = Table(
            code="obj_customer",
            name="客户表",
            desc="客户",
            columns=[
                Column(name="customer_id", sql_type="varchar", nullable=False, comment="客户ID"),
            ],
        )
        term_type_defs = build_term_type_defs(config)
        enrich_term_type_names(term_type_defs, [table], config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        xml_str = _kps_to_xml(pkg)
        g = Graph()
        g.parse(data=xml_str, format="xml")

        term_code_paths = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("term_code_path")
        }
        assert "L1#object#obj_customer" in term_code_paths

    def test_roundtrip_relations_has_field_category(self) -> None:
        """往返后：HAS_FIELD 关系 relationCategory 正确保留。"""
        config = _build_base_config()
        table = Table(
            code="obj_customer",
            name="客户表",
            desc="客户",
            columns=[
                Column(name="customer_id", sql_type="varchar", nullable=False, comment="客户ID"),
            ],
        )
        term_type_defs = build_term_type_defs(config)
        enrich_term_type_names(term_type_defs, [table], config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        xml_str = _kps_relations_to_xml(pkg, "HAS_FIELD")
        g = Graph()
        g.parse(data=xml_str, format="xml")

        categories = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("relationCategory")
        }
        assert categories == {"HAS_FIELD"}, f"期望 HAS_FIELD，实际: {categories}"

    def test_roundtrip_relations_many_to_one_cardinality(self) -> None:
        """往返后：MANY_TO_ONE 关系 cardinality = N:1。"""
        config = _build_base_config()
        config.object_relations = [
            ObjectRelation(
                relation_id="r1",
                source_code="obj_customer",
                target_code="obj_order",
                relation_name="客户拥有订单",
                join_keys=[{"sourceField": "customer_id", "targetField": "customer_id"}],
            )
        ]
        table = Table(
            code="obj_customer",
            name="客户表",
            desc="客户",
            columns=[
                Column(name="customer_id", sql_type="varchar", nullable=False, comment="客户ID"),
            ],
        )
        term_type_defs = build_term_type_defs(config)
        enrich_term_type_names(term_type_defs, [table], config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        xml_str = _kps_relations_to_xml(pkg, "MANY_TO_ONE")
        g = Graph()
        g.parse(data=xml_str, format="xml")

        cardinalities = {
            str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("cardinality")
        }
        assert cardinalities == {"N:1"}, f"MANY_TO_ONE 期望 cardinality=N:1，实际: {cardinalities}"

    def test_roundtrip_has_term_cardinality(self) -> None:
        """往返后：HAS_TERM 关系 cardinality = 1:N。"""
        config = _build_base_config()
        config.term_bindings = [
            TermBinding("obj_customer", "customer_level", "level_type", "LIST_TERM")
        ]
        config.term_type_configs = {
            "level_type": TermTypeConfig(type_name="客户等级", type_desc="客户等级术语类型")
        }
        config.object_prop_configs = {
            ("obj_customer", "customer_level"): ObjectPropConfig(
                property_code="customer_level",
                property_name="客户等级",
            )
        }
        table = Table(
            code="obj_customer",
            name="客户表",
            desc="客户",
            columns=[
                Column(
                    name="customer_level",
                    sql_type="varchar",
                    nullable=False,
                    comment="客户等级",
                ),
            ],
        )
        term_type_defs = build_term_type_defs(config)
        enrich_term_type_names(term_type_defs, [table], config)
        term_values: dict[str, list[dict[str, str]]] = {
            "level_type": [
                {"code": "A", "name": "A级"},
                {"code": "B", "name": "B级"},
            ]
        }

        pkg = _build_object_package(config, table, term_values, term_type_defs, set())

        xml_str = _kps_relations_to_xml(pkg, "HAS_TERM")
        g = Graph()
        g.parse(data=xml_str, format="xml")

        cardinalities = {
            str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("cardinality")
        }
        assert cardinalities == {"1:N"}, f"HAS_TERM 期望 cardinality=1:N，实际: {cardinalities}"

    def test_roundtrip_prop_deduplication(self) -> None:
        """往返后：跨对象去重，相同 prop 只出现一次。"""
        config = _build_base_config()
        config.table_codes = ["obj_customer", "obj_order"]
        config.table_names.update({"obj_order": "订单表"})
        config.table_descs.update({"obj_order": "订单"})
        table = Table(
            code="obj_customer",
            name="客户表",
            desc="客户",
            columns=[
                Column(name="customer_id", sql_type="varchar", nullable=False, comment="客户ID"),
                Column(
                    name="customer_name", sql_type="varchar", nullable=False, comment="客户名称"
                ),
            ],
        )
        table2 = Table(
            code="obj_order",
            name="订单表",
            desc="订单",
            columns=[
                Column(name="customer_id", sql_type="varchar", nullable=False, comment="客户ID"),
            ],
        )
        term_type_defs = build_term_type_defs(config)
        enrich_term_type_names(term_type_defs, [table, table2], config)

        # 第一个对象去重集为空
        seen: set[str] = set()
        pkg1 = _build_object_package(config, table, {}, term_type_defs, seen)

        xml1 = _kps_to_xml(pkg1)
        g1 = Graph()
        g1.parse(data=xml1, format="xml")
        paths1 = {
            str(o)
            for _s, _p, o in g1.triples((None, None, None))
            if str(_p).endswith("term_code_path")
        }
        assert "L1#prop#customer_id" in paths1
        assert "L1#prop#customer_name" in paths1

        # 第二个对象使用已填充的去重集，customer_id 不应重复
        pkg2 = _build_object_package(config, table2, {}, term_type_defs, seen)

        xml2 = _kps_to_xml(pkg2)
        g2 = Graph()
        g2.parse(data=xml2, format="xml")
        paths2 = {
            str(o)
            for _s, _p, o in g2.triples((None, None, None))
            if str(_p).endswith("term_code_path")
        }
        assert "L1#prop#customer_id" not in paths2, f"customer_id prop 应被去重，但出现了: {paths2}"


# ═══════════════════════════════════════════════════════════════════════════════
# 视图包往返测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestViewPackageRoundtrip:
    """_build_view_package → GraphBuilder → XML → rdflib 重新解析。"""

    def test_roundtrip_view_term_present(self) -> None:
        """往返后：视图术语 term_code_path = L1#view#v_analysis。"""
        config = _build_base_config()
        config.table_names.update({"obj_customer": "客户表", "obj_order": "订单表"})
        view = ViewConfig(
            view_code="v_analysis",
            view_name="分析视图",
            view_desc="综合分析",
            object_codes=["obj_customer", "obj_order"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="customer_id",
                    property_name="客户ID",
                    source_object_code="obj_customer",
                    source_object_column_code="customer_id",
                    role=FieldRole("DIMENSION_ATTR", "id"),
                )
            ],
        )

        pkg = _build_view_package(config, view)

        xml_str = _kps_to_xml(pkg)
        g = Graph()
        g.parse(data=xml_str, format="xml")

        term_code_paths = {
            str(o)
            for _s, _p, o in g.triples((None, None, None))
            if str(_p).endswith("term_code_path")
        }
        assert "L1#view#v_analysis" in term_code_paths

    def test_roundtrip_view_has_object_cardinality(self) -> None:
        """往返后：视图 HAS_OBJECT 关系 cardinality = 1:N。"""
        config = _build_base_config()
        config.table_names.update({"obj_customer": "客户表", "obj_order": "订单表"})
        view = ViewConfig(
            view_code="v_analysis",
            view_name="分析视图",
            view_desc="综合分析",
            object_codes=["obj_customer", "obj_order"],
            field_mappings=[],
        )

        pkg = _build_view_package(config, view)

        xml_str = _kps_relations_to_xml(pkg, "HAS_OBJECT")
        g = Graph()
        g.parse(data=xml_str, format="xml")

        cardinalities = {
            str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("cardinality")
        }
        assert cardinalities, "cardinality 不应为空"
        assert cardinalities.issubset({"1:N"}), (
            f"HAS_OBJECT 期望 cardinality=1:N，实际: {cardinalities}"
        )

    def test_roundtrip_view_many_to_one_cardinality(self) -> None:
        """往返后：视图内 MANY_TO_ONE 关系 cardinality = N:1。"""
        config = _build_base_config()
        config.table_names.update({"obj_customer": "客户表", "obj_order": "订单表"})
        config.object_relations = [
            ObjectRelation(
                relation_id="r1",
                source_code="obj_customer",
                target_code="obj_order",
                relation_name="客户→订单",
                join_keys=[{"sourceField": "customer_id", "targetField": "customer_id"}],
            )
        ]
        view = ViewConfig(
            view_code="v_analysis",
            view_name="分析视图",
            view_desc="综合分析",
            object_codes=["obj_customer", "obj_order"],
            field_mappings=[],
        )

        pkg = _build_view_package(config, view)

        xml_str = _kps_relations_to_xml(pkg, "MANY_TO_ONE")
        g = Graph()
        g.parse(data=xml_str, format="xml")

        cardinalities = {
            str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("cardinality")
        }
        assert cardinalities == {"N:1"}, (
            f"视图 MANY_TO_ONE 期望 cardinality=N:1，实际: {cardinalities}"
        )
