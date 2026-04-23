from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from datacloud_knowledge.owl_gen.generator import generate_from_tables
from datacloud_knowledge.owl_gen.models import (
    Column,
    FieldRole,
    ObjectRelation,
    OwlGenConfig,
    Table,
    TermBinding,
    ViewConfig,
    ViewFieldMapping,
)
from datacloud_knowledge.owl_gen.renderers.manifest import render_manifest
from datacloud_knowledge.owl_gen.renderers.ontology import (
    render_single_view,
    render_view,
    render_view_mapping,
)
from datacloud_knowledge.owl_gen.renderers.relations import render_relation_view
from datacloud_knowledge.owl_gen.renderers.terms import render_terms, render_terms_for_view


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

    assert result.count("<owl:NamedIndividual") == 5
    assert "rel_scene_enterprise_analysis_to_ads_manage_grid_analysis" in result
    assert "rel_scene_grid_analysis_to_ads_manage_grid_analysis" in result


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

    assert "term_view_scene_enterprise_analysis" in ontology_terms
    assert "term_view_scene_grid_analysis" in ontology_terms


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
    assert ontology_terms.count("term_prop_enterprise_id") == 1
    assert "属性：企业唯一ID" in ontology_terms
    assert "企业综合分析表的字段" not in ontology_terms
    assert "物理网格综合分析表的字段" not in ontology_terms


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


def test_generate_from_tables_skips_duplicate_props_in_later_objects(tmp_path: Path) -> None:
    config = _build_config()
    config.output_dir = tmp_path
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

    generate_from_tables(config, tables, {})

    first_terms = (
        tmp_path / "object" / "ads_enterprise_analysis" / "ads_enterprise_analysis_terms.owl"
    ).read_text()
    second_terms = (
        tmp_path / "object" / "ads_grid_analysis" / "ads_grid_analysis_terms.owl"
    ).read_text()

    assert "term_prop_enterprise_id" in first_terms
    assert "属性：企业唯一ID" in first_terms
    assert "term_prop_enterprise_id" not in second_terms


def test_render_terms_for_view_emits_only_view_term() -> None:
    """视图 terms 只生成 VIEW 术语，不再生成 prop 术语。

    prop 术语在对象层生成，视图专属别名通过 HAS_FIELD 关系的 ext_field 传递。
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
                )
            ],
        )
    ]

    result, count = render_terms_for_view(config, config.views[0])

    assert count == 1
    assert "VIEW#scene_enterprise_analysis" in result
    assert "term_prop_enterprise_id" not in result
