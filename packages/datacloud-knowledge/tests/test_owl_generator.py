"""OWL 生成器核心函数单元测试 — KPS 构建（_build_object_package / _build_view_package 等）。

本文件测试 generator.py 中将 OwlGenConfig + Table/ViewConfig
转换为 KnowledgePackage（KPS 中间模型）的核心函数。
焦点在 KPS 对象的内容正确性（术语列表、关系列表、术语类型列表），
不测试 XML 序列化（已有 test_owl_gen_multiview.py 做 GraphBuilder 集成测试）。
"""

from __future__ import annotations

from pathlib import Path

from datacloud_knowledge.ingestion.owl_generate.generator import (
    _build_object_package,
    _build_term_def,
    _build_view_package,
)
from datacloud_knowledge.ingestion.owl_generate.models import (
    Column,
    FieldRole,
    ObjectPropConfig,
    ObjectRelation,
    OwlGenConfig,
    Table,
    TermBinding,
    ViewConfig,
    ViewFieldMapping,
)
from datacloud_knowledge.ingestion.owl_generate.renderers.term_types import build_term_type_defs

# ═══════════════════════════════════════════════════════════════════════════════
# Mock Config 构建
# ═══════════════════════════════════════════════════════════════════════════════


def _minimal_config(**overrides: object) -> OwlGenConfig:
    """构建最小合法 OwlGenConfig，可覆盖任意字段。"""
    defaults: dict[str, object] = {
        "domain_code": "D1",
        "domain_name": "测试域",
        "domain_desc": "用于单元测试的领域",
        "library_code": "L1",
        "library_name": "测试术语库",
        "library_desc": "测试术语库描述",
        "db_code": "test_db",
        "db_type": "mysql",
        "db_params": {},
        "table_codes": ["test_object"],
        "table_names": {"test_object": "测试对象表"},
        "table_descs": {"test_object": "测试对象描述"},
        "term_bindings": [],
        "object_relations": [],
        "output_dir": Path("/tmp/test-owl-gen"),
    }
    defaults.update(overrides)
    return OwlGenConfig(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# _build_term_def 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildTermDef:
    """测试 _build_term_def() 函数。"""

    def test_basic_construction(self) -> None:
        """基本术语构建：所有字段正确赋值。"""
        config = _minimal_config()
        term = _build_term_def(
            config,
            term_code="test_obj",
            term_name="测试对象",
            term_type_code="object",
            term_desc="这是一个测试对象",
        )

        assert term.term_code == "test_obj"
        assert term.term_name == "测试对象"
        assert term.term_type_code == "object"
        assert term.library_code == "L1"
        assert term.domain_code == "D1"
        assert term.parent_term_code is None
        assert term.synonyms == ()
        assert term.term_desc == "这是一个测试对象"

    def test_with_parent_term_code(self) -> None:
        """带父术语编码的术语构建。"""
        config = _minimal_config()
        term = _build_term_def(
            config,
            term_code="city",
            term_name="城市",
            term_type_code="DICT_TERM",
            parent_term_code="region_code",
        )

        assert term.parent_term_code == "region_code"

    def test_parent_term_code_empty_string_becomes_none(self) -> None:
        """空字符串 parent_term_code 应转为 None。"""
        config = _minimal_config()
        term = _build_term_def(
            config,
            term_code="tag",
            term_name="标签",
            term_type_code="LIST_TERM",
            parent_term_code="",
        )

        assert term.parent_term_code is None

    def test_with_synonyms(self) -> None:
        """同义词列表正确转为 tuple。"""
        config = _minimal_config()
        term = _build_term_def(
            config,
            term_code="customer",
            term_name="客户",
            term_type_code="object",
            synonyms=["顾客", "Client", "甲方"],
        )

        assert term.synonyms == ("顾客", "Client", "甲方")

    def test_compute_term_id_no_parent(self) -> None:
        """compute_term_id() — 无父术语时返回 {lib}#{type}#{code}。"""
        config = _minimal_config()
        term = _build_term_def(
            config, term_code="by_customer", term_name="客户", term_type_code="object"
        )

        assert term.compute_term_id() == "L1#object#by_customer"

    def test_compute_term_id_with_parent(self) -> None:
        """compute_term_id() — 有父术语时返回 {parent_id}#{type}#{code}。"""
        config = _minimal_config()
        term = _build_term_def(
            config,
            term_code="A",
            term_name="A级",
            term_type_code="ent_level",
            parent_term_code="enterprise_level",
        )

        assert (
            term.compute_term_id("L1#prop#enterprise_level")
            == "L1#prop#enterprise_level#ent_level#A"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# _build_object_package 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildObjectPackage:
    """测试 _build_object_package() — 对象级 KnowledgePackage 构建。"""

    def test_basic_object_terms(self) -> None:
        """对象 KPS 包含对象本体术语 + 属性术语。"""
        config = _minimal_config(
            table_names={"test_obj": "测试对象"},
            table_descs={"test_obj": "一个测试对象"},
        )
        table = Table(
            code="test_obj",
            name="测试对象",
            desc="一个测试对象",
            columns=[
                Column(name="id", sql_type="int", nullable=False, comment="ID"),
                Column(name="name", sql_type="varchar", nullable=False, comment="名称"),
            ],
        )
        term_type_defs = build_term_type_defs(config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        # 术语：object + 2 prop = 3
        assert len(pkg.terms) == 3
        # 对象本体术语
        obj_term = pkg.terms[0]
        assert obj_term.term_code == "test_obj"
        assert obj_term.term_name == "测试对象"
        assert obj_term.term_type_code == "object"

        # 属性术语
        prop_codes = {t.term_code for t in pkg.terms if t.term_type_code == "prop"}
        assert prop_codes == {"id", "name"}

    def test_prop_dedup_across_objects(self) -> None:
        """跨对象属性去重：已见的 prop code 不重复生成。"""
        config = _minimal_config(
            table_names={"obj_a": "对象A", "obj_b": "对象B"},
            table_descs={"obj_a": "A", "obj_b": "B"},
        )
        table_a = Table(
            code="obj_a",
            name="对象A",
            desc="A",
            columns=[
                Column(name="shared_col", sql_type="varchar", nullable=False, comment="共享字段")
            ],
        )
        table_b = Table(
            code="obj_b",
            name="对象B",
            desc="B",
            columns=[
                Column(name="shared_col", sql_type="varchar", nullable=False, comment="共享字段")
            ],
        )
        term_type_defs = build_term_type_defs(config)

        seen: set[str] = set()
        pkg_a = _build_object_package(config, table_a, {}, term_type_defs, seen)
        pkg_b = _build_object_package(config, table_b, {}, term_type_defs, seen)

        # 对象 A 有 object + 1 prop = 2 术语
        assert len(pkg_a.terms) == 2
        # 对象 B 只有 object 术语（prop 已去重）
        assert len(pkg_b.terms) == 1
        assert pkg_b.terms[0].term_type_code == "object"

    def test_has_field_relations(self) -> None:
        """每个字段生成一个 HAS_FIELD 关系。"""
        config = _minimal_config(
            table_names={"test_obj": "测试对象"},
            table_descs={"test_obj": "测试对象"},
        )
        table = Table(
            code="test_obj",
            name="测试对象",
            desc="测试对象",
            columns=[
                Column(name="col_a", sql_type="varchar", nullable=False, comment="列A"),
                Column(name="col_b", sql_type="int", nullable=False, comment="列B"),
            ],
        )
        term_type_defs = build_term_type_defs(config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        has_field_rels = [r for r in pkg.relations if r.relation_category == "HAS_FIELD"]
        assert len(has_field_rels) == 2

        # 验证 source → target 模式
        source_codes = {r.source_term_code for r in has_field_rels}
        target_codes = {r.target_term_code for r in has_field_rels}
        assert source_codes == {"L1#object#test_obj"}
        assert target_codes == {"L1#prop#col_a", "L1#prop#col_b"}

        # ext_field 包含 field_alias
        for rel in has_field_rels:
            assert rel.ext_field is not None
            assert "field_alias" in rel.ext_field

    def test_has_field_relations_with_object_prop_config(self) -> None:
        """使用 ObjectPropConfig 后 relation 指向配置的 property_code。"""
        config = _minimal_config(
            table_names={"test_obj": "测试对象"},
            table_descs={"test_obj": "测试对象"},
            object_prop_configs={
                ("test_obj", "raw_code"): ObjectPropConfig(
                    property_code="business_prop_code",
                    property_name="业务属性名",
                )
            },
        )
        table = Table(
            code="test_obj",
            name="测试对象",
            desc="测试对象",
            columns=[
                Column(name="raw_code", sql_type="varchar", nullable=False, comment="原始编码")
            ],
        )
        term_type_defs = build_term_type_defs(config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        has_field_rels = [r for r in pkg.relations if r.relation_category == "HAS_FIELD"]
        assert len(has_field_rels) == 1
        assert has_field_rels[0].target_term_code == "L1#prop#business_prop_code"

        # 术语 code 也使用配置的 property_code
        prop_terms = [t for t in pkg.terms if t.term_type_code == "prop"]
        assert len(prop_terms) == 1
        assert prop_terms[0].term_code == "business_prop_code"
        assert prop_terms[0].term_name == "业务属性名"

    def test_has_field_relations_with_synonyms(self) -> None:
        """字段同义词写入 ext_field.synonyms。"""
        config = _minimal_config(
            table_names={"test_obj": "测试对象"},
            table_descs={"test_obj": "测试对象"},
            object_field_synonyms={("test_obj", "col_x"): ["别名1", "别名2"]},
        )
        table = Table(
            code="test_obj",
            name="测试对象",
            desc="测试对象",
            columns=[Column(name="col_x", sql_type="varchar", nullable=False, comment="列X")],
        )
        term_type_defs = build_term_type_defs(config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        rel = next(r for r in pkg.relations if r.relation_category == "HAS_FIELD")
        assert rel.ext_field is not None
        assert rel.ext_field.get("synonyms") == ["别名1", "别名2"]

    def test_value_terms_and_has_term_relations(self) -> None:
        """术语绑定：HAS_TERM 关系（prop → type），值术语由单独导入提供。"""
        config = _minimal_config(
            table_names={"test_obj": "测试对象"},
            table_descs={"test_obj": "测试对象"},
            term_bindings=[
                TermBinding("test_obj", "status", "opp_status", "LIST_TERM"),
            ],
        )
        table = Table(
            code="test_obj",
            name="测试对象",
            desc="测试对象",
            columns=[Column(name="status", sql_type="varchar", nullable=False, comment="状态")],
        )
        term_type_defs = build_term_type_defs(config)
        term_values = {
            "opp_status": [
                {"code": "SIGNED", "name": "签约成功", "parent_prop_code": "status"},
                {"code": "LOST", "name": "丢单", "parent_prop_code": "status"},
            ]
        }

        pkg = _build_object_package(config, table, term_values, term_type_defs, set())

        # 值术语不再生成（由业务系统单独导入）
        value_terms = [t for t in pkg.terms if t.term_type_code == "opp_status"]
        assert len(value_terms) == 0

        # HAS_TERM: prop → type，一个 binding 一条
        has_term_rels = [r for r in pkg.relations if r.relation_category == "HAS_TERM"]
        assert len(has_term_rels) == 1
        rel = has_term_rels[0]
        assert rel.source_term_code == "L1#prop#status"
        assert rel.target_term_code == "L1#opp_status#opp_status"
        assert rel.cardinality == "1:1"

    def test_many_to_one_relations(self) -> None:
        """MANY_TO_ONE 关系：只有 source_code 匹配当前 table 时才生成。"""
        config = _minimal_config(
            table_names={"obj_a": "对象A", "obj_b": "对象B"},
            table_descs={"obj_a": "A", "obj_b": "B"},
            object_relations=[
                ObjectRelation(
                    relation_id="rel_1",
                    source_code="obj_a",
                    target_code="obj_b",
                    relation_name="A关联B",
                    join_keys=[{"sourceField": "b_id", "targetField": "id"}],
                ),
                ObjectRelation(
                    relation_id="rel_2",
                    source_code="obj_b",  # 不匹配当前 table
                    target_code="obj_c",
                    relation_name="B关联C",
                    join_keys=[{"sourceField": "c_id", "targetField": "id"}],
                ),
            ],
        )
        table = Table(
            code="obj_a",
            name="对象A",
            desc="A",
            columns=[Column(name="b_id", sql_type="int", nullable=False, comment="B的ID")],
        )
        term_type_defs = build_term_type_defs(config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        many_to_one_rels = [r for r in pkg.relations if r.relation_category == "MANY_TO_ONE"]
        assert len(many_to_one_rels) == 1
        rel = many_to_one_rels[0]
        assert rel.source_term_code == "L1#object#obj_a"
        assert rel.target_term_code == "L1#object#obj_b"
        assert rel.relation_name == "A关联B"
        assert len(rel.joinkeys) == 1
        assert rel.joinkeys[0]["sourceField"] == "b_id"

    def test_term_types_in_package(self) -> None:
        """KPS 包含正确的 term_types 列表（object + prop + 绑定的值术语类型）。"""
        config = _minimal_config(
            table_names={"test_obj": "测试对象"},
            table_descs={"test_obj": "测试对象"},
            term_bindings=[
                TermBinding("test_obj", "status", "opp_status", "LIST_TERM"),
            ],
        )
        table = Table(
            code="test_obj",
            name="测试对象",
            desc="测试对象",
            columns=[],
        )
        term_type_defs = build_term_type_defs(config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        type_codes_in_pkg = {t.type_code for t in pkg.term_types}
        assert "object" in type_codes_in_pkg
        assert "prop" in type_codes_in_pkg
        assert "opp_status" in type_codes_in_pkg

        # type_category 映射：object/prop → ONTOLOGY_TERM=3
        for tt in pkg.term_types:
            if tt.type_code in ("object", "prop"):
                assert tt.type_category == 3  # ONTOLOGY_TERM
            elif tt.type_code == "opp_status":
                assert tt.type_category == 1  # LIST_TERM

    def test_total_relation_count(self) -> None:
        """完整场景的关系计数：HAS_FIELD × 列数 + HAS_TERM × binding + MANY_TO_ONE。"""
        config = _minimal_config(
            table_names={"test_obj": "测试对象"},
            table_descs={"test_obj": "测试对象"},
            term_bindings=[
                TermBinding("test_obj", "status", "opp_status", "LIST_TERM"),
            ],
            object_relations=[
                ObjectRelation(
                    relation_id="rel_1",
                    source_code="test_obj",
                    target_code="other_obj",
                    relation_name="关联",
                    join_keys=[{"sourceField": "o_id", "targetField": "id"}],
                ),
            ],
        )
        table = Table(
            code="test_obj",
            name="测试对象",
            desc="测试对象",
            columns=[
                Column(name="id", sql_type="int", nullable=False, comment="ID"),
                Column(name="status", sql_type="varchar", nullable=False, comment="状态"),
            ],
        )
        term_type_defs = build_term_type_defs(config)
        term_values = {"opp_status": [{"code": "A", "name": "状态A", "parent_prop_code": "status"}]}

        pkg = _build_object_package(config, table, term_values, term_type_defs, set())

        # HAS_FIELD: 2 列 → 2, HAS_TERM: 1 binding → 1, MANY_TO_ONE: 1
        assert sum(1 for r in pkg.relations if r.relation_category == "HAS_FIELD") == 2
        assert sum(1 for r in pkg.relations if r.relation_category == "HAS_TERM") == 1
        assert sum(1 for r in pkg.relations if r.relation_category == "MANY_TO_ONE") == 1
        assert len(pkg.relations) == 4

    def test_knowledge_package_immutable(self) -> None:
        """KnowledgePackage 使用 frozen dataclass，不可变。"""
        config = _minimal_config()
        table = Table(code="test_obj", name="测试对象", desc="", columns=[])
        term_type_defs = build_term_type_defs(config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())

        # terms/relations/term_types 都是 tuple，不可修改
        assert isinstance(pkg.terms, tuple)
        assert isinstance(pkg.relations, tuple)
        assert isinstance(pkg.term_types, tuple)

    def test_rel_joinkeys_immutable(self) -> None:
        """RelationDef.joinkeys 为 tuple（不可变）。"""
        config = _minimal_config(
            table_names={"test_obj": "测试对象"},
            table_descs={"test_obj": "测试对象"},
            object_relations=[
                ObjectRelation(
                    relation_id="r1",
                    source_code="test_obj",
                    target_code="other",
                    relation_name="r",
                    join_keys=[{"k": "v"}],
                )
            ],
        )
        table = Table(code="test_obj", name="测试对象", desc="", columns=[])
        term_type_defs = build_term_type_defs(config)

        pkg = _build_object_package(config, table, {}, term_type_defs, set())
        mto = next(r for r in pkg.relations if r.relation_category == "MANY_TO_ONE")

        assert isinstance(mto.joinkeys, tuple)


# ═══════════════════════════════════════════════════════════════════════════════
# _build_view_package 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildViewPackage:
    """测试 _build_view_package() — 视图级 KnowledgePackage 构建。"""

    def test_basic_view_term(self) -> None:
        """视图 KPS 包含视图本体术语。"""
        config = _minimal_config()
        view = ViewConfig(
            view_code="scene_sales",
            view_name="销售管理视图",
            view_desc="销售管理综合视图",
            object_codes=["by_customer", "by_opportunity"],
            field_mappings=[],
        )

        pkg = _build_view_package(config, view)

        # 至少包含视图本体术语
        assert len(pkg.terms) >= 1
        assert pkg.terms[0].term_code == "scene_sales"
        assert pkg.terms[0].term_name == "销售管理视图"
        assert pkg.terms[0].term_type_code == "view"

    def test_has_object_relations(self) -> None:
        """视图通过 HAS_OBJECT 关系关联其包含的对象。"""
        config = _minimal_config(
            table_names={"by_customer": "客户", "by_opportunity": "商机"},
            table_descs={"by_customer": "客户对象", "by_opportunity": "商机对象"},
        )
        view = ViewConfig(
            view_code="scene_sales",
            view_name="销售管理视图",
            view_desc="销售",
            object_codes=["by_customer", "by_opportunity"],
            field_mappings=[],
        )

        pkg = _build_view_package(config, view)

        has_obj_rels = [r for r in pkg.relations if r.relation_category == "HAS_OBJECT"]
        assert len(has_obj_rels) == 2

        source_codes = {r.source_term_code for r in has_obj_rels}
        target_codes = {r.target_term_code for r in has_obj_rels}
        assert source_codes == {"L1#view#scene_sales"}
        assert target_codes == {"L1#object#by_customer", "L1#object#by_opportunity"}

    def test_has_field_relations_for_view_mappings(self) -> None:
        """视图字段映射生成 HAS_FIELD 关系（source=view, target=prop）。"""
        config = _minimal_config(
            table_names={"by_customer": "客户"},
            table_descs={"by_customer": "客户对象"},
        )
        view = ViewConfig(
            view_code="scene_sales",
            view_name="销售管理视图",
            view_desc="销售",
            object_codes=["by_customer"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="enterprise_id",
                    property_name="企业ID",
                    source_object_code="by_customer",
                    source_object_column_code="enterprise_id",
                    role=FieldRole("DIMENSION_ATTR", "id"),
                ),
            ],
        )

        pkg = _build_view_package(config, view)

        has_field_rels = [r for r in pkg.relations if r.relation_category == "HAS_FIELD"]
        assert len(has_field_rels) == 1
        rel = has_field_rels[0]
        assert rel.source_term_code == "L1#view#scene_sales"
        assert rel.target_term_code == "L1#prop#enterprise_id"
        assert rel.ext_field is not None
        assert rel.ext_field.get("field_alias") == "企业ID"

    def test_view_prop_term_for_prefixed_mapping(self) -> None:
        """视图字段 mapping.property_code ≠ column_name + resolve 结果时，生成视图专属 prop 术语。"""
        config = _minimal_config(
            table_names={"by_customer": "客户"},
            table_descs={"by_customer": "客户对象"},
            force_view_prop_terms=True,
        )
        view = ViewConfig(
            view_code="scene_sales",
            view_name="销售管理视图",
            view_desc="销售",
            object_codes=["by_customer"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="view_enterprise_id",
                    property_name="视图企业ID",
                    source_object_code="by_customer",
                    source_object_column_code="enterprise_id",
                    role=FieldRole("DIMENSION_ATTR", "id"),
                    synonyms=["视图企业唯一ID"],
                ),
            ],
        )

        pkg = _build_view_package(config, view)

        # 视图 prop 术语：property_code != source_object_column_code
        prop_terms = [t for t in pkg.terms if t.term_type_code == "prop"]
        assert len(prop_terms) == 1
        assert prop_terms[0].term_code == "view_enterprise_id"
        assert prop_terms[0].term_name == "视图企业ID"
        assert prop_terms[0].synonyms == ("视图企业唯一ID",)

    def test_view_prop_term_skipped_when_same_code(self) -> None:
        """mapping.property_code 等于 source_object_column_code 时，不生成额外的 prop 术语。"""
        config = _minimal_config(
            table_names={"by_customer": "客户"},
            table_descs={"by_customer": "客户对象"},
        )
        view = ViewConfig(
            view_code="scene_sales",
            view_name="销售管理视图",
            view_desc="销售",
            object_codes=["by_customer"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="enterprise_id",  # 与 source_object_column_code 相同
                    property_name="企业ID",
                    source_object_code="by_customer",
                    source_object_column_code="enterprise_id",
                    role=FieldRole("DIMENSION_ATTR", "id"),
                ),
            ],
        )

        pkg = _build_view_package(config, view)

        # 没有 prop 术语（只有视图本体术语）
        prop_terms = [t for t in pkg.terms if t.term_type_code == "prop"]
        assert len(prop_terms) == 0

    def test_many_to_one_relations_in_view(self) -> None:
        """视图内对象间的 MANY_TO_ONE 关系（只包含在 view.object_codes 内的对象）。"""
        config = _minimal_config(
            table_names={"obj_a": "对象A", "obj_b": "对象B", "obj_c": "对象C"},
            table_descs={"obj_a": "A", "obj_b": "B", "obj_c": "C"},
            object_relations=[
                ObjectRelation(
                    relation_id="r1",
                    source_code="obj_a",
                    target_code="obj_b",
                    relation_name="A→B",
                    join_keys=[{"sourceField": "b_id", "targetField": "id"}],
                ),
                ObjectRelation(
                    relation_id="r2",
                    source_code="obj_a",
                    target_code="obj_c",  # obj_c 不在 view.object_codes 中
                    relation_name="A→C",
                    join_keys=[{"sourceField": "c_id", "targetField": "id"}],
                ),
            ],
        )
        view = ViewConfig(
            view_code="scene_test",
            view_name="测试视图",
            view_desc="测试",
            object_codes=["obj_a", "obj_b"],  # 不含 obj_c
            field_mappings=[],
        )

        pkg = _build_view_package(config, view)

        mto_rels = [r for r in pkg.relations if r.relation_category == "MANY_TO_ONE"]
        assert len(mto_rels) == 1
        assert mto_rels[0].target_term_code == "L1#object#obj_b"

    def test_view_value_terms_when_forced(self) -> None:
        """force_view_value_terms=True 时，视图包含值术语。"""
        config = _minimal_config(
            table_names={"by_customer": "客户"},
            table_descs={"by_customer": "客户对象"},
            term_bindings=[
                TermBinding("by_customer", "status", "opp_status", "LIST_TERM"),
            ],
            force_view_value_terms=True,
        )
        view = ViewConfig(
            view_code="scene_sales",
            view_name="销售管理视图",
            view_desc="销售",
            object_codes=["by_customer"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="status",
                    property_name="状态",
                    source_object_code="by_customer",
                    source_object_column_code="status",
                    role=FieldRole("DIMENSION_ATTR", "id"),
                ),
            ],
        )
        term_type_defs = build_term_type_defs(config)
        term_values = {
            "opp_status": [
                {"code": "SIGNED", "name": "签约成功"},
            ]
        }

        pkg = _build_view_package(config, view, term_values, term_type_defs)

        # 值术语不再生成（force_view_value_terms 已移除，值由单独导入提供）
        value_terms = [t for t in pkg.terms if t.term_type_code == "opp_status"]
        assert len(value_terms) == 0

    def test_view_with_field_synonyms_in_ext_field(self) -> None:
        """视图字段映射的同义词写入 HAS_FIELD 关系的 ext_field。"""
        config = _minimal_config(
            table_names={"by_customer": "客户"},
            table_descs={"by_customer": "客户对象"},
        )
        view = ViewConfig(
            view_code="scene_sales",
            view_name="销售管理视图",
            view_desc="销售",
            object_codes=["by_customer"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="customer_name",
                    property_name="客户名称",
                    source_object_code="by_customer",
                    source_object_column_code="customer_name",
                    role=FieldRole("DIMENSION_ATTR", "name"),
                    synonyms=["顾客姓名", "企业全称"],
                ),
            ],
        )

        pkg = _build_view_package(config, view)

        has_field_rels = [r for r in pkg.relations if r.relation_category == "HAS_FIELD"]
        assert len(has_field_rels) == 1
        rel = has_field_rels[0]
        assert rel.ext_field is not None
        assert rel.ext_field.get("synonyms") == ["顾客姓名", "企业全称"]

    def test_view_package_returns_empty_relations_for_simple_view(self) -> None:
        """无 object_codes 的视图：只有视图本体术语，无关系。"""
        config = _minimal_config()
        view = ViewConfig(
            view_code="empty_view",
            view_name="空视图",
            view_desc="空",
            object_codes=[],
            field_mappings=[],
        )

        pkg = _build_view_package(config, view)

        assert len(pkg.terms) == 1  # 只有视图本体术语
        assert len(pkg.relations) == 0
        assert pkg.terms[0].term_code == "empty_view"
