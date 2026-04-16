"""OWL 导入包生成器 — 主编排模块。

职责：读 schema → 调用各渲染器 → 写文件。
不包含任何 OWL XML 模板，只做编排。
"""

from __future__ import annotations

import logging

from datacloud_knowledge.owl_gen._xml import write_text
from datacloud_knowledge.owl_gen.models import OwlGenConfig, Table
from datacloud_knowledge.owl_gen.renderers.manifest import render_manifest
from datacloud_knowledge.owl_gen.renderers.meta import render_domains, render_library
from datacloud_knowledge.owl_gen.renderers.ontology import (
    render_actions,
    render_dbsource,
    render_mapping,
    render_object,
    render_single_view,
    render_view_mapping,
)
from datacloud_knowledge.owl_gen.renderers.relations import (
    render_relation_action,
    render_relation_attribute,
    render_relation_object,
    render_relation_term,
    render_relation_view,
)
from datacloud_knowledge.owl_gen.renderers.term_types import (
    build_term_type_defs,
    enrich_term_type_names,
    render_term_types,
)
from datacloud_knowledge.owl_gen.renderers.terms import render_terms
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

    # meta
    write_text(out / "meta" / "domains.owl", render_domains(config))
    write_text(out / "meta" / "library.owl", render_library(config))
    logger.info("✓ meta")

    # term_types
    write_text(
        out / "term_types" / "term_types.owl",
        render_term_types(config, term_type_defs),
    )
    logger.info("✓ term_types (%d 种)", len(term_type_defs))

    # terms — 按 type_code 拆文件
    terms_files = render_terms(config, tables, term_values, term_type_defs)
    total_term_count = 0
    for rel_path, (content, count) in terms_files.items():
        write_text(out / rel_path, content)
        total_term_count += count
    logger.info("✓ terms (%d 条, %d 文件)", total_term_count, len(terms_files))

    # relations — 固定 4 个 + term 按 type_code 拆文件
    write_text(out / "relations" / "relation_view.owl", render_relation_view(config))
    write_text(out / "relations" / "relation_object.owl", render_relation_object(config))
    write_text(
        out / "relations" / "relation_attribute.owl",
        render_relation_attribute(config, tables),
    )
    write_text(
        out / "relations" / "relation_action.owl",
        render_relation_action(config, tables),
    )
    rel_term_files = render_relation_term(config, term_values)
    for rel_path, content in rel_term_files.items():
        write_text(out / rel_path, content)
    logger.info("✓ relations (4 + %d term files)", len(rel_term_files))

    # ontology
    write_text(out / "ontology" / "dbsources" / "dbsource.owl", render_dbsource(config))
    write_text(out / "ontology" / "actions" / "action.owl", render_actions(config, tables))
    for v in config.resolved_views():
        v_dir = out / "ontology" / "views" / v.view_code
        write_text(v_dir / f"{v.view_code}_view.owl", render_single_view(config, v))
        vm_content = render_view_mapping(config, view=v)
        if vm_content:
            write_text(v_dir / f"{v.view_code}_mapping.owl", vm_content)
    for table in tables:
        obj_dir = out / "ontology" / "objects" / table.code
        write_text(obj_dir / f"{table.code}_object.owl", render_object(config, table))
        write_text(obj_dir / f"{table.code}_mapping.owl", render_mapping(config, table))
    logger.info("✓ ontology (%d 张表)", len(tables))

    # manifest
    manifest_content = render_manifest(
        config,
        tables,
        total_term_count,
        len(term_type_defs),
        terms_files,
        rel_term_files,
    )
    write_text(out / "manifest.json", manifest_content)
    logger.info("✓ manifest.json")


def _total_cols(tables: list[Table]) -> int:
    return sum(len(t.columns) for t in tables)
