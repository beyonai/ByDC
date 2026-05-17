from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from datacloud_knowledge.ingestion.owl_generate.generator import generate_from_tables
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
from datacloud_knowledge.ingestion.owl_generate.renderers.manifest import render_manifest
from datacloud_knowledge.ingestion.owl_generate.renderers.ontology import (
    render_object,
    render_single_view,
    render_view,
    render_view_mapping,
)
from datacloud_knowledge.ingestion.owl_generate.renderers.relations import (
    render_relation_view,
    render_view_relations_for_view,
)
from datacloud_knowledge.ingestion.owl_generate.renderers.terms import (
    render_terms,
    render_terms_for_view,
)
from rdflib import RDF, Graph


def _build_config() -> OwlGenConfig:
    views = [
        ViewConfig(
            view_code="scene_enterprise_analysis",
            view_name="企业综合分析视图",
            view_desc="企业视图",
            object_codes=[
                "ads_enterprise_analysis",
                "ads_grid_analysis",
                "ads_manage_grid_analysis",
            ],
            field_mappings=[
                ViewFieldMapping(
                    property_code="enterprise_id",
                    property_name="企业唯一ID",
                    source_object_code="ads_enterprise_analysis",
                    source_object_column_code="enterprise_id",
                    role=FieldRole("DIMENSION_ATTR", "id"),
                ),
                ViewFieldMapping(
                    property_code="energy_efficiency_Index",
                    property_name="企业经济效益等级",
                    source_object_code="ads_enterprise_analysis",
                    source_object_column_code="energy_efficiency_Index",
                    role=FieldRole("DIMENSION_ATTR", "name"),
                ),
            ],
        ),
        ViewConfig(
            view_code="scene_grid_analysis",
            view_name="物理网格综合分析视图",
            view_desc="网格视图",
            object_codes=["ads_grid_analysis", "ads_manage_grid_analysis"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="phy_grid_id",
                    property_name="物理网格编码",
                    source_object_code="ads_grid_analysis",
                    source_object_column_code="phy_grid_id",
                    role=FieldRole("DIMENSION_ATTR", "id"),
                )
            ],
        ),
    ]
    return OwlGenConfig(
        domain_code="D1",
        domain_name="d",
        domain_desc="d",
        library_code="L1",
        library_name="l",
        library_desc="l",
        db_code="db",
        db_type="mysql",
        db_params={},
        table_codes=["ads_enterprise_analysis", "ads_grid_analysis", "ads_manage_grid_analysis"],
        table_names={
            "ads_enterprise_analysis": "企业综合分析表",
            "ads_grid_analysis": "物理网格综合分析表",
            "ads_manage_grid_analysis": "管理网格综合分析表",
        },
        table_descs={
            "ads_enterprise_analysis": "企业",
            "ads_grid_analysis": "网格",
            "ads_manage_grid_analysis": "管理网格",
        },
        term_bindings=[],
        object_relations=[
            ObjectRelation(
                relation_id="rel_ads_enterprise_analysis_to_ads_grid_analysis",
                source_code="ads_enterprise_analysis",
                target_code="ads_grid_analysis",
                relation_name="企业归属物理网格",
                join_keys=[{"sourceField": "phy_grid_id", "targetField": "phy_grid_id"}],
            ),
            ObjectRelation(
                relation_id="rel_ads_grid_analysis_to_ads_manage_grid_analysis",
                source_code="ads_grid_analysis",
                target_code="ads_manage_grid_analysis",
                relation_name="物理网格归属管理网格",
                join_keys=[{"sourceField": "manage_grid_id", "targetField": "manage_grid_id"}],
            ),
        ],
        output_dir=Path("/tmp/test-owl-gen"),
        views=views,
    )


def test_render_view_supports_multiple_views() -> None:
    config = _build_config()

    result = render_view(config)

    assert "scene_enterprise_analysis" in result
    assert "scene_grid_analysis" in result


def test_render_single_view_writes_one_view_definition() -> None:
    config = _build_config()

    result = render_single_view(config, config.views[0])

    assert "scene_enterprise_analysis" in result
    assert "scene_grid_analysis" not in result


def test_render_view_mapping_uses_view_specific_field_mappings() -> None:
    config = _build_config()

    enterprise_mapping = render_view_mapping(config, view=config.views[0])
    grid_mapping = render_view_mapping(config, view=config.views[1])

    assert "enterprise_id" in enterprise_mapping
    assert "energy_efficiency_Index" in enterprise_mapping
    assert "phy_grid_id" not in enterprise_mapping
    assert "phy_grid_id" in grid_mapping
    assert "enterprise_id" not in grid_mapping


def test_render_relation_view_counts_all_view_object_links() -> None:
    config = _build_config()

    result = render_relation_view(config)

    g = Graph()
    g.parse(data=result, format="xml")

    # 统计 TermRelation 实体数
    term_rel_count = sum(
        1 for _s, _p, o in g.triples((None, RDF.type, None)) if "TermRelation" in str(o)
    )
    assert term_rel_count == 5

    # 验证场景视图到对象的包含关系：通过 sourceTermCode / targetTermCode 对
    source_map: dict = {}
    target_map: dict = {}
    for s, p, o in g.triples((None, None, None)):
        p_str = str(p)
        if p_str.endswith("sourceTermCode"):
            source_map[s] = str(o)
        elif p_str.endswith("targetTermCode"):
            target_map[s] = str(o)

    pairs = {(source_map[k], target_map[k]) for k in source_map if k in target_map}

    # 企业综合分析视图包含三张表
    assert ("L1#view#scene_enterprise_analysis", "L1#object#ads_enterprise_analysis") in pairs
    assert ("L1#view#scene_enterprise_analysis", "L1#object#ads_grid_analysis") in pairs
    assert ("L1#view#scene_enterprise_analysis", "L1#object#ads_manage_grid_analysis") in pairs
    # 物理网格综合分析视图包含两张表
    assert ("L1#view#scene_grid_analysis", "L1#object#ads_grid_analysis") in pairs
    assert ("L1#view#scene_grid_analysis", "L1#object#ads_manage_grid_analysis") in pairs


def test_render_manifest_includes_per_view_definition_and_mapping_steps() -> None:
    config = _build_config()
    tables = [
        Table(code="ads_enterprise_analysis", name="企业综合分析表", desc="企业"),
        Table(code="ads_grid_analysis", name="物理网格综合分析表", desc="网格"),
        Table(code="ads_manage_grid_analysis", name="管理网格综合分析表", desc="管理网格"),
    ]

    manifest = render_manifest(
        config=config,
        tables=tables,
        term_count=0,
        term_type_count=0,
        terms_files={},
        rel_term_files={},
    )

    assert "ontology/views/scene_enterprise_analysis/scene_enterprise_analysis_view.owl" in manifest
    assert (
        "ontology/views/scene_enterprise_analysis/scene_enterprise_analysis_mapping.owl" in manifest
    )
    assert "ontology/views/scene_grid_analysis/scene_grid_analysis_view.owl" in manifest
    assert "ontology/views/scene_grid_analysis/scene_grid_analysis_mapping.owl" in manifest
    assert '"file": "ontology/views/views.owl"' not in manifest
    assert '"count": 5' in manifest


def test_render_terms_emits_one_term_per_view() -> None:
    config = _build_config()

    result = render_terms(config, [], {}, OrderedDict())

    ontology_terms, _count = result["terms/terms_ontology.owl"]

    g = Graph()
    g.parse(data=ontology_terms, format="xml")

    term_code_paths = {
        str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("term_code_path")
    }
    assert "L1#view#scene_enterprise_analysis" in term_code_paths
    assert "L1#view#scene_grid_analysis" in term_code_paths


def test_render_terms_dedupes_props_across_objects_with_generic_desc() -> None:
    config = _build_config()
    tables = [
        Table(
            code="ads_enterprise_analysis",
            name="企业综合分析表",
            desc="企业",
            columns=[
                Column(
                    name="enterprise_id",
                    sql_type="varchar",
                    nullable=False,
                    comment="企业唯一ID",
                )
            ],
        ),
        Table(
            code="ads_grid_analysis",
            name="物理网格综合分析表",
            desc="网格",
            columns=[
                Column(
                    name="enterprise_id",
                    sql_type="varchar",
                    nullable=False,
                    comment="网格企业 ID",
                )
            ],
        ),
    ]

    result = render_terms(config, tables, {}, OrderedDict())

    ontology_terms, count = result["terms/terms_ontology.owl"]

    assert count == 7

    g = Graph()
    g.parse(data=ontology_terms, format="xml")

    # Deduped: 仅一个 enterprise_id prop term
    prop_term_count = sum(
        1
        for _s, _p, o in g.triples((None, None, None))
        if str(_p).endswith("term_code_path") and str(o) == "L1#prop#enterprise_id"
    )
    assert prop_term_count == 1

    # 描述使用 comment 而非表名拼接
    term_descs = {
        str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("term_desc")
    }
    assert "属性：企业唯一ID" in term_descs
    assert "企业综合分析表的字段" not in term_descs
    assert "物理网格综合分析表的字段" not in term_descs


def test_resolved_views_wraps_legacy_single_view_fields() -> None:
    config = OwlGenConfig(
        domain_code="D1",
        domain_name="d",
        domain_desc="d",
        library_code="L1",
        library_name="l",
        library_desc="l",
        db_code="db",
        db_type="mysql",
        db_params={},
        table_codes=["ads_enterprise_analysis"],
        table_names={"ads_enterprise_analysis": "企业综合分析表"},
        table_descs={"ads_enterprise_analysis": "企业"},
        term_bindings=[
            TermBinding(
                "ads_enterprise_analysis", "enterprise_name", "enterprise_name", "LIST_TERM"
            )
        ],
        object_relations=[],
        output_dir=Path("/tmp/test-owl-gen"),
        view_code="legacy_view",
        view_name="旧视图",
        view_desc="旧描述",
        view_field_mappings=[
            ViewFieldMapping(
                property_code="enterprise_id",
                property_name="企业唯一ID",
                source_object_code="ads_enterprise_analysis",
                source_object_column_code="enterprise_id",
                role=FieldRole("DIMENSION_ATTR", "id"),
            )
        ],
    )

    views = config.resolved_views()

    assert len(views) == 1
    assert views[0].view_code == "legacy_view"
    assert views[0].object_codes == ["ads_enterprise_analysis"]
    assert views[0].field_mappings[0].property_code == "enterprise_id"


def test_generate_from_tables_writes_per_view_files(tmp_path: Path) -> None:
    config = _build_config()
    config.output_dir = tmp_path
    tables = [
        Table(code="ads_enterprise_analysis", name="企业综合分析表", desc="企业"),
        Table(code="ads_grid_analysis", name="物理网格综合分析表", desc="网格"),
        Table(code="ads_manage_grid_analysis", name="管理网格综合分析表", desc="管理网格"),
    ]

    generate_from_tables(config, tables, {})

    assert (
        tmp_path / "view" / "scene_enterprise_analysis" / "scene_enterprise_analysis_definition.owl"
    ).exists()
    assert (
        tmp_path / "view" / "scene_enterprise_analysis" / "scene_enterprise_analysis_terms.owl"
    ).exists()
    assert (
        tmp_path / "view" / "scene_grid_analysis" / "scene_grid_analysis_definition.owl"
    ).exists()
    assert (tmp_path / "view" / "scene_grid_analysis" / "scene_grid_analysis_terms.owl").exists()


def test_generate_from_tables_uses_business_object_prop_config(tmp_path: Path) -> None:
    config = _build_config()
    config.output_dir = tmp_path
    config.object_prop_configs = {
        ("ads_enterprise_analysis", "total_revenue"): ObjectPropConfig(
            property_code="enterprise_total_revenue",
            property_name="企业总营收（万元）",
            synonyms=["企业收入"],
        )
    }
    tables = [
        Table(
            code="ads_enterprise_analysis",
            name="企业综合分析表",
            desc="企业",
            columns=[
                Column(
                    name="total_revenue",
                    sql_type="decimal(18,2)",
                    nullable=False,
                    comment="总营收",
                )
            ],
        )
    ]

    generate_from_tables(config, tables, {})

    object_definition = (
        tmp_path / "object" / "ads_enterprise_analysis" / "ads_enterprise_analysis_definition.owl"
    ).read_text()
    object_mapping = (
        tmp_path / "object" / "ads_enterprise_analysis" / "ads_enterprise_analysis_mapping.owl"
    ).read_text()
    object_terms = (
        tmp_path / "object" / "ads_enterprise_analysis" / "ads_enterprise_analysis_terms.owl"
    ).read_text()
    object_relations = (
        tmp_path
        / "object"
        / "ads_enterprise_analysis"
        / "ads_enterprise_analysis_attribute_relations.owl"
    ).read_text()

    # 字段定义包含 business object prop config 的 property_code
    g_def = Graph()
    g_def.parse(data=object_definition, format="xml")
    pc_values = {
        str(o)
        for _s, _p, o in g_def.triples((None, None, None))
        if str(_p).endswith("propertyCode")
    }
    assert "enterprise_total_revenue" in pc_values

    # 映射文件包含对应字段
    assert "enterprise_total_revenue_mapping" in object_mapping

    # 术语文件包含 prop term
    g_terms = Graph()
    g_terms.parse(data=object_terms, format="xml")
    term_code_paths = {
        str(o)
        for _s, _p, o in g_terms.triples((None, None, None))
        if str(_p).endswith("term_code_path")
    }
    assert "L1#prop#enterprise_total_revenue" in term_code_paths

    # 属性关系文件目标指向 prop term
    g_rel = Graph()
    g_rel.parse(data=object_relations, format="xml")
    target_codes = {
        str(o)
        for _s, _p, o in g_rel.triples((None, None, None))
        if str(_p).endswith("targetTermCode")
    }
    assert "L1#prop#enterprise_total_revenue" in target_codes

    # 同义词 "企业收入" 出现在关系文件的 extField JSON 中
    assert any("企业收入" in str(o) for _s, _p, o in g_rel.triples((None, None, None)))


def test_generate_from_tables_uses_business_term_type_config(tmp_path: Path) -> None:
    config = _build_config()
    config.output_dir = tmp_path
    config.term_bindings = [
        TermBinding(
            "ads_enterprise_analysis",
            "enterprise_level_name",
            "ent_level",
            "DICT_TERM",
        )
    ]
    config.term_type_configs = {
        "ent_level": TermTypeConfig(
            type_name="企业等级",
            type_desc="企业等级术语类型",
        )
    }
    config.object_prop_configs = {
        ("ads_enterprise_analysis", "enterprise_level_name"): ObjectPropConfig(
            property_code="enterprise_level",
            property_name="企业等级",
        )
    }
    tables = [
        Table(
            code="ads_enterprise_analysis",
            name="企业综合分析表",
            desc="企业",
            columns=[
                Column(
                    name="enterprise_level_name",
                    sql_type="varchar",
                    nullable=False,
                    comment="企业等级字段备注",
                )
            ],
        )
    ]
    term_values = {
        "ent_level": [
            {
                "code": "A",
                "name": "A级",
                "parent_prop_code": "enterprise_level",
            }
        ]
    }

    generate_from_tables(config, tables, term_values)

    term_types = (
        tmp_path / "object" / "ads_enterprise_analysis" / "ads_enterprise_analysis_term_types.owl"
    ).read_text()
    object_terms = (
        tmp_path / "object" / "ads_enterprise_analysis" / "ads_enterprise_analysis_terms.owl"
    ).read_text()

    # 术语类型文件包含 term name 和 desc
    g_tt = Graph()
    g_tt.parse(data=term_types, format="xml")
    type_values = {str(o) for _s, _p, o in g_tt.triples((None, None, None))}
    assert "企业等级" in type_values
    assert "企业等级术语类型" in type_values

    # 术语文件包含 parent_term_code
    g_terms = Graph()
    g_terms.parse(data=object_terms, format="xml")
    parent_codes = {
        str(o)
        for _s, _p, o in g_terms.triples((None, None, None))
        if str(_p).endswith("parent_term_code")
    }
    assert "enterprise_level" in parent_codes


def test_render_object_distinguishes_code_and_name_term_bindings() -> None:
    config = _build_config()
    config.term_bindings = [
        TermBinding("ads_enterprise_analysis", "enterprise_name", "enterprise_name", "LIST_TERM"),
        TermBinding("ads_enterprise_analysis", "level_code", "enterprise_level", "DICT_TERM"),
    ]
    config.name_term_type_codes = {"enterprise_name"}
    table = Table(
        code="ads_enterprise_analysis",
        name="企业综合分析表",
        desc="企业",
        columns=[
            Column("enterprise_name", "varchar", False, "企业名称"),
            Column("level_code", "varchar", False, "企业等级编码"),
        ],
    )

    result = render_object(config, table)

    g = Graph()
    g.parse(data=result, format="xml")

    # termTypeCodePath 包含正确的 term type code
    type_paths = {
        str(o)
        for _s, _p, o in g.triples((None, None, None))
        if str(_p).endswith("termTypeCodePath")
    }
    assert "L1#enterprise_name" in type_paths
    assert "L1#enterprise_level" in type_paths

    # relTermCodeorname 正确区分 name / code
    rel_names = {
        str(o)
        for _s, _p, o in g.triples((None, None, None))
        if str(_p).endswith("relTermCodeorname")
    }
    assert "name" in rel_names
    assert "code" in rel_names

    # 各出现一次
    name_count = sum(
        1
        for _s, _p, o in g.triples((None, None, None))
        if str(_p).endswith("relTermCodeorname") and str(o) == "name"
    )
    code_count = sum(
        1
        for _s, _p, o in g.triples((None, None, None))
        if str(_p).endswith("relTermCodeorname") and str(o) == "code"
    )
    assert name_count == 1
    assert code_count == 1


def test_render_object_applies_identity_and_property_alias_term_rules() -> None:
    config = _build_config()
    config.term_bindings = [
        TermBinding("ads_enterprise_analysis", "enterprise_name", "enterprise_name", "LIST_TERM"),
        TermBinding("ads_grid_analysis", "grid_name", "grid_name", "LIST_TERM"),
    ]
    config.object_identity_term_aliases = {
        ("ads_enterprise_analysis", "enterprise_id"): ("enterprise_name", "code"),
        ("ads_enterprise_analysis", "enterprise_name"): ("enterprise_name", "name"),
    }
    config.object_property_term_aliases = {
        ("ads_enterprise_analysis", "grid_id"): "grid_name",
    }
    table = Table(
        code="ads_enterprise_analysis",
        name="企业综合分析表",
        desc="企业",
        columns=[
            Column("enterprise_id", "varchar", False, "企业编码"),
            Column("enterprise_name", "varchar", False, "企业名称"),
            Column("grid_id", "varchar", False, "所属网格编码"),
        ],
    )

    result = render_object(config, table)

    g = Graph()
    g.parse(data=result, format="xml")

    # termTypeCodePath 中 L1#enterprise_name 出现 2 次（id alias + name alias）
    name_type_count = sum(
        1
        for _s, _p, o in g.triples((None, None, None))
        if str(_p).endswith("termTypeCodePath") and str(o) == "L1#enterprise_name"
    )
    assert name_type_count == 2

    # L1#grid_name 出现 1 次（property alias）
    grid_type_count = sum(
        1
        for _s, _p, o in g.triples((None, None, None))
        if str(_p).endswith("termTypeCodePath") and str(o) == "L1#grid_name"
    )
    assert grid_type_count == 1

    # relTermCodeorname: code 出现 2 次（id alias + grid_id alias），name 出现 1 次
    code_count = sum(
        1
        for _s, _p, o in g.triples((None, None, None))
        if str(_p).endswith("relTermCodeorname") and str(o) == "code"
    )
    name_count = sum(
        1
        for _s, _p, o in g.triples((None, None, None))
        if str(_p).endswith("relTermCodeorname") and str(o) == "name"
    )
    assert code_count == 2
    assert name_count == 1


def test_render_terms_for_view_emits_only_view_term() -> None:
    """视图 terms 为 prefixed 字段生成独立 prop 术语。

    同 code 映射沿用对象层 prop；property_code 与 source_object_column_code 不同的映射
    生成独立 prop 术语，避免被标准化到源字段 code。
    """
    config = _build_config()
    config.views = [
        ViewConfig(
            view_code="scene_enterprise_analysis",
            view_name="企业综合分析视图",
            view_desc="企业视图",
            object_codes=["ads_enterprise_analysis"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="enterprise_id",
                    property_name="企业综合分析视图企业 ID",
                    source_object_code="ads_enterprise_analysis",
                    source_object_column_code="enterprise_id",
                    role=FieldRole("DIMENSION_ATTR", "id"),
                    synonyms=["企业综合分析视图企业 ID"],
                ),
                ViewFieldMapping(
                    property_code="grid_total_revenue",
                    property_name="所属物理网格总营收（万元）",
                    source_object_code="ads_grid_analysis",
                    source_object_column_code="total_revenue",
                    role=FieldRole("DIMENSION", "numeric"),
                    synonyms=["所属物理网格总营收（万元）"],
                ),
            ],
        )
    ]

    result, count = render_terms_for_view(config, config.views[0])

    assert count == 2

    g = Graph()
    g.parse(data=result, format="xml")

    term_code_paths = {
        str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("term_code_path")
    }

    # 视图 term 存在
    assert "L1#view#scene_enterprise_analysis" in term_code_paths

    # 同 code 映射沿用对象层 prop，不重复生成
    assert "L1#prop#enterprise_id" not in term_code_paths

    # 独立 prop term 已生成
    assert "L1#prop#grid_total_revenue" in term_code_paths

    # 中文描述存在
    term_names = {
        str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("term_name")
    }
    assert "所属物理网格总营收（万元）" in term_names


def test_render_terms_for_view_skips_configured_object_prop_code() -> None:
    config = _build_config()
    config.object_prop_configs = {
        ("ads_enterprise_analysis", "total_revenue"): ObjectPropConfig(
            property_code="enterprise_total_revenue",
            property_name="企业总营收（万元）",
        )
    }
    config.views = [
        ViewConfig(
            view_code="scene_enterprise_analysis",
            view_name="企业综合分析视图",
            view_desc="企业视图",
            object_codes=["ads_enterprise_analysis"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="enterprise_total_revenue",
                    property_name="企业总营收（万元）",
                    source_object_code="ads_enterprise_analysis",
                    source_object_column_code="total_revenue",
                    role=FieldRole("MEASURE", "basic_metric"),
                )
            ],
        )
    ]

    result, count = render_terms_for_view(config, config.views[0])

    assert count == 1

    g = Graph()
    g.parse(data=result, format="xml")

    term_code_paths = {
        str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("term_code_path")
    }

    # 视图 term 存在
    assert "L1#view#scene_enterprise_analysis" in term_code_paths

    # 对象层已有 prop，视图层不重复生成
    assert "L1#prop#enterprise_total_revenue" not in term_code_paths


def test_render_view_relations_for_view_targets_property_code_for_prefixed_fields() -> None:
    config = _build_config()
    config.views = [
        ViewConfig(
            view_code="scene_enterprise_analysis",
            view_name="企业综合分析视图",
            view_desc="企业视图",
            object_codes=["ads_enterprise_analysis", "ads_grid_analysis"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="grid_total_revenue",
                    property_name="所属物理网格总营收（万元）",
                    source_object_code="ads_grid_analysis",
                    source_object_column_code="total_revenue",
                    role=FieldRole("DIMENSION", "numeric"),
                )
            ],
        )
    ]

    result = render_view_relations_for_view(config, config.views[0])

    g = Graph()
    g.parse(data=result, format="xml")

    target_codes = {
        str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("targetTermCode")
    }

    # prefixed 字段 targetTermCode 指向 L1#prop#grid_total_revenue
    assert any("grid_total_revenue" in t for t in target_codes)
    # 不指向原始 column total_revenue
    assert not any(t.endswith("#total_revenue") and "prop" in str(t) for t in target_codes)


def test_render_view_relations_for_view_uses_object_prop_code_for_same_code_mapping() -> None:
    config = _build_config()
    config.object_prop_configs = {
        ("ads_enterprise_analysis", "total_revenue"): ObjectPropConfig(
            property_code="enterprise_total_revenue",
            property_name="企业总营收（万元）",
        )
    }
    config.views = [
        ViewConfig(
            view_code="scene_enterprise_analysis",
            view_name="企业综合分析视图",
            view_desc="企业视图",
            object_codes=["ads_enterprise_analysis"],
            field_mappings=[
                ViewFieldMapping(
                    property_code="total_revenue",
                    property_name="企业总营收（万元）",
                    source_object_code="ads_enterprise_analysis",
                    source_object_column_code="total_revenue",
                    role=FieldRole("MEASURE", "basic_metric"),
                )
            ],
        )
    ]

    result = render_view_relations_for_view(config, config.views[0])

    g = Graph()
    g.parse(data=result, format="xml")

    target_codes = {
        str(o) for _s, _p, o in g.triples((None, None, None)) if str(_p).endswith("targetTermCode")
    }

    # property_code 映射到对象层已配置的 prop code
    assert any("enterprise_total_revenue" in t for t in target_codes)
