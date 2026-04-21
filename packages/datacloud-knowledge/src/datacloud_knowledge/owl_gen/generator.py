"""OWL 导入包生成器 — 主编排模块。

职责：读 schema → 调用各渲染器 → 写文件。
不包含任何 OWL XML 模板，只做编排。
"""

from __future__ import annotations

import logging

from datacloud_knowledge.owl_gen._xml import write_text
from datacloud_knowledge.owl_gen.models import OwlGenConfig, Table
from datacloud_knowledge.owl_gen.renderers.ontology import (
    render_dbsource,
    render_mapping,
    render_object,
    render_single_view,
)
from datacloud_knowledge.owl_gen.renderers.relations import (
    render_attribute_relations_for_object,
    render_object_relations_for_object,
    render_term_relations_for_object,
    render_view_relations_for_view,
)
from datacloud_knowledge.owl_gen.renderers.term_types import (
    build_term_type_defs,
    enrich_term_type_names,
    render_term_types_for_object,
)
from datacloud_knowledge.owl_gen.renderers.terms import (
    render_terms_for_object,
    render_terms_for_view,
)
from datacloud_knowledge.owl_gen.schema_reader import load_term_values, read_tables

logger = logging.getLogger(__name__)


def generate(config: OwlGenConfig) -> None:
    """端到端生成 OWL 导入包。"""
    out = config.output_dir
    logger.info("开始生成 OWL 导入包 → %s", out)

    logger.info("读取 MySQL 表结构...")
    tables = read_tables(config)
    logger.info("读取到 %d 张表，共 %d 个字段", len(tables), _total_cols(tables))

    logger.info("读取术语值...")
    term_values = load_term_values(config)
    total_values = sum(len(v) for v in term_values.values())
    logger.info("读取到 %d 种术语类型，共 %d 条术语值", len(term_values), total_values)

    _write_package(config, tables, term_values)
    logger.info("OWL 导入包生成完成: %s", out)


def generate_from_tables(
    config: OwlGenConfig,
    tables: list[Table],
    term_values: dict[str, list[dict[str, str]]],
) -> None:
    """从已有的表结构和术语值生成（不连 MySQL）。"""
    _write_package(config, tables, term_values)


def _write_package(
    config: OwlGenConfig,
    tables: list[Table],
    term_values: dict[str, list[dict[str, str]]],
) -> None:
    """渲染所有 OWL 文件并写入 output_dir。"""
    out = config.output_dir

    # 术语类型定义
    term_type_defs = build_term_type_defs(config)
    enrich_term_type_names(term_type_defs, tables, config)

    total_term_count = 0
    relation_file_count = 0

    for table in tables:
        obj_dir = out / "object" / table.code
        write_text(obj_dir / f"{table.code}_definition.owl", render_object(config, table))
        write_text(obj_dir / f"{table.code}_mapping.owl", render_mapping(config, table))
        write_text(obj_dir / f"{table.code}_dbsource.owl", render_dbsource(config))

        object_relations = render_object_relations_for_object(config, table.code)
        if object_relations:
            write_text(obj_dir / f"{table.code}_object_relations.owl", object_relations)
            relation_file_count += 1

        attribute_relations = render_attribute_relations_for_object(config, table)
        if attribute_relations:
            write_text(obj_dir / f"{table.code}_attribute_relations.owl", attribute_relations)
            relation_file_count += 1

        term_relations = render_term_relations_for_object(config, table, term_values)
        if term_relations:
            write_text(obj_dir / f"{table.code}_term_relations.owl", term_relations)
            relation_file_count += 1

        write_text(
            obj_dir / f"{table.code}_term_types.owl",
            render_term_types_for_object(config, table, term_type_defs),
        )
        terms_content, term_count = render_terms_for_object(
            config,
            table,
            term_values,
            term_type_defs,
        )
        write_text(obj_dir / f"{table.code}_terms.owl", terms_content)
        total_term_count += term_count

    for view in config.resolved_views():
        view_dir = out / "view" / view.view_code
        write_text(view_dir / f"{view.view_code}_definition.owl", render_single_view(config, view))
        view_relations = render_view_relations_for_view(config, view)
        if view_relations:
            write_text(view_dir / f"{view.view_code}_relations.owl", view_relations)
            relation_file_count += 1
        terms_content, term_count = render_terms_for_view(config, view)
        write_text(view_dir / f"{view.view_code}_terms.owl", terms_content)
        total_term_count += term_count

    logger.info(
        "✓ package (objects=%d, views=%d, terms=%d, relation_files=%d)",
        len(tables),
        len(config.resolved_views()),
        total_term_count,
        relation_file_count,
    )


def _total_cols(tables: list[Table]) -> int:
    return sum(len(t.columns) for t in tables)
