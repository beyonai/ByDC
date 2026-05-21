"""OWL 导入包生成器 — 主编排模块。

数据流（Phase 1.5）：
  OwlGenConfig → adapters schema reader → KnowledgePackage（KPS 中间模型）
      → GraphBuilder.add_package() → export_*_graph() → serialize → 写文件

定义级文件（EntityDefinition/Mapping/DBSource/SceneDefinition）非 KPS，
通过 GraphBuilder 定义级方法直接生成。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from datacloud_knowledge.contracts.kps import (
    KnowledgePackage,
    RelationDef,
    TermDef,
    TermTypeDef,
)
from datacloud_knowledge.ingestion.owl_generate._xml import write_text
from datacloud_knowledge.ingestion.owl_generate.graph_builder import GraphBuilder
from datacloud_knowledge.ingestion.owl_generate.models import OwlGenConfig, Table, ViewConfig
from datacloud_knowledge.ingestion.owl_generate.renderers.actions import (
    write_action_files,
)
from datacloud_knowledge.ingestion.owl_generate.renderers.ontology import (
    render_dbsource,
    render_mapping,
    render_object,
    render_single_view,
)
from datacloud_knowledge.ingestion.owl_generate.renderers.relations import (
    render_view_relations_for_view,
)
from datacloud_knowledge.ingestion.owl_generate.renderers.term_types import (
    _term_data_type_to_category,
    build_term_type_defs,
    enrich_term_type_names,
)
from datacloud_knowledge.ingestion.owl_generate.schema_reader import load_term_values, read_tables

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 公开入口
# ═══════════════════════════════════════════════════════════════════════════════


def generate(config: OwlGenConfig) -> None:
    """端到端生成 OWL 导入包。"""
    out = config.output_dir
    logger.info("开始生成 OWL 导入包 → %s", out)

    logger.info("读取表结构...")
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
    """从已有的表结构和术语值生成（不连数据库）。"""
    _write_package(config, tables, term_values)


# ═══════════════════════════════════════════════════════════════════════════════
# 主编排：构建 KnowledgePackage → GraphBuilder 序列化 → 写文件
# ═══════════════════════════════════════════════════════════════════════════════


def _write_package(
    config: OwlGenConfig,
    tables: list[Table],
    term_values: dict[str, list[dict[str, str]]],
) -> None:
    """渲染所有 OWL 文件并写入 output_dir。

    核心流程：对每个对象/视图构建 KnowledgePackage，通过 GraphBuilder.add_package()
    注册到 rdflib.Graph，再通过 export_*_graph() 拆分为独立 OWL 文件输出。
    """
    out = config.output_dir
    term_type_defs = build_term_type_defs(config)
    enrich_term_type_names(term_type_defs, tables, config)

    # 跨对象 prop 去重
    seen_prop_codes: set[str] = set()
    total_term_count = 0
    relation_file_count = 0

    for table in tables:
        obj_dir = out / "object" / table.code

        # ── 定义文件（非 KPS：EntityDefinition/Mapping/DBSource）────────────
        write_text(obj_dir / f"{table.code}_definition.owl", render_object(config, table))
        write_text(obj_dir / f"{table.code}_mapping.owl", render_mapping(config, table))
        write_text(obj_dir / f"{table.code}_dbsource.owl", render_dbsource(config))

        # ── KPS 文件（KnowledgePackage → GraphBuilder）─────────────────────
        pkg = _build_object_package(config, table, term_values, term_type_defs, seen_prop_codes)
        relation_file_count += _write_kps_files(builder=None, obj_dir=obj_dir, pkg=pkg)
        total_term_count += len(pkg.terms)

    for view in config.resolved_views():
        view_dir = out / "view" / view.view_code
        write_text(view_dir / f"{view.view_code}_definition.owl", render_single_view(config, view))
        write_text(
            view_dir / f"{view.view_code}_relations.owl",
            render_view_relations_for_view(config, view),
        )

        pkg = _build_view_package(config, view, term_values, term_type_defs)
        relation_file_count += _write_kps_view_files(view_dir, pkg)
        total_term_count += len(pkg.terms)

    # ── Action 生成：写入 actions/ 子目录（独立通道，不作为术语）─────────────
    action_file_count = 0
    if config.actions:
        action_file_count = write_action_files(config, "", "")
    else:
        for table in tables:
            action_file_count += write_action_files(config, table.code, table.name)

    logger.info(
        "✓ package (objects=%d, views=%d, terms=%d, relation_files=%d, action_files=%d)",
        len(tables),
        len(config.resolved_views()),
        total_term_count,
        relation_file_count,
        action_file_count,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# KPS 构建：对象
# ═══════════════════════════════════════════════════════════════════════════════


def _build_term_def(
    config: OwlGenConfig,
    term_code: str,
    term_name: str,
    term_type_code: str,
    term_desc: str = "",
    parent_term_code: str = "",
    synonyms: list[str] | None = None,
) -> TermDef:
    """构建 KPS TermDef 对象。"""
    return TermDef(
        term_code=term_code,
        term_name=term_name,
        term_type_code=term_type_code,
        library_code=config.library_code,
        domain_code=config.domain_code,
        parent_term_code=parent_term_code if parent_term_code else None,
        synonyms=tuple(synonyms or []),
        term_desc=term_desc,
    )


def _build_object_package(
    config: OwlGenConfig,
    table: Table,
    term_values: dict[str, list[dict[str, str]]],
    term_type_defs: dict[str, tuple[str, str, str]],
    seen_prop_codes: set[str],
) -> KnowledgePackage:
    """为单个对象构建 KnowledgePackage。

    包含：对象本体术语 + 属性术语（跨对象去重） + 值术语 + 字段关系 + JOIN 关系 + 术语类型。
    """
    terms: list[TermDef] = []
    relations: list[RelationDef] = []
    term_types: list[TermTypeDef] = []

    # ── 术语类型 ──
    type_codes: set[str] = {"object", "prop"}
    for binding in config.term_bindings:
        if binding.table_code == table.code:
            type_codes.add(binding.term_type_code)

    for type_code, (name, desc, term_data_type) in term_type_defs.items():
        if type_code in type_codes:
            term_types.append(
                TermTypeDef(
                    type_code=type_code,
                    type_name=name,
                    type_category=_term_data_type_to_category(term_data_type),
                    type_desc=desc,
                )
            )

    # ── 对象本体术语 ──
    terms.append(
        _build_term_def(
            config,
            term_code=table.code,
            term_name=table.name,
            term_type_code="object",
            term_desc=table.desc,
        )
    )

    # ── 属性术语（prop）：跨对象去重 ──
    binding_lookup = {b.column_name: b for b in config.term_bindings if b.table_code == table.code}
    for col in table.columns:
        resolved_prop = config.resolve_object_prop(table.code, col.name, col.comment or col.name)
        if resolved_prop.property_code not in seen_prop_codes:
            seen_prop_codes.add(resolved_prop.property_code)
            terms.append(
                _build_term_def(
                    config,
                    term_code=resolved_prop.property_code,
                    term_name=resolved_prop.property_name,
                    term_type_code="prop",
                    term_desc=resolved_prop.property_desc,
                    parent_term_code=table.code,
                    synonyms=resolved_prop.synonyms,
                )
            )

        # 字段关系：HAS_FIELD（每个字段一个关系）
        alias = resolved_prop.property_name
        syns = resolved_prop.synonyms or config.object_field_synonyms.get(
            (table.code, col.name), []
        )
        source_term = f"{config.library_code}#object#{table.code}"
        target_term = f"{config.library_code}#prop#{resolved_prop.property_code}"
        ext_field_data: dict[str, object] = {"field_alias": alias}
        if syns:
            ext_field_data["synonyms"] = syns
        relations.append(
            RelationDef(
                source_term_code=source_term,
                target_term_code=target_term,
                relation_name=f"{table.name}_拥有字段_{alias}",
                relation_category="HAS_FIELD",
                cardinality="1:N",
                ext_field=ext_field_data,
            )
        )

    # ── 值术语（LIST_TERM / DICT_TERM）─────────────────────────────────────
    for binding in binding_lookup.values():
        type_code = binding.term_type_code
        type_name = term_type_defs.get(type_code, (type_code, "", ""))[0]
        for entry in term_values.get(type_code, []):
            terms.append(
                _build_term_def(
                    config,
                    term_code=entry["code"],
                    term_name=entry["name"],
                    term_type_code=type_code,
                    term_desc=f"{type_name}术语：{entry['name']}",
                    parent_term_code=entry.get("parent_prop_code", ""),
                )
            )
            # 值术语关系：HAS_TERM
            source_term_v = f"{config.library_code}#{type_code}#{type_code}"
            target_term_v = f"{config.library_code}#{type_code}#{entry['code']}"
            relations.append(
                RelationDef(
                    source_term_code=source_term_v,
                    target_term_code=target_term_v,
                    relation_name=f"{type_code}包含{entry['name']}",
                    relation_category="HAS_TERM",
                    cardinality="1:N",
                )
            )

    # ── JOIN 关系（MANY_TO_ONE）────────────────────────────────────────────
    for rel in config.object_relations:
        if rel.source_code != table.code:
            continue
        source_term_o = f"{config.library_code}#object#{rel.source_code}"
        target_term_o = f"{config.library_code}#object#{rel.target_code}"
        relations.append(
            RelationDef(
                source_term_code=source_term_o,
                target_term_code=target_term_o,
                relation_name=rel.relation_name,
                relation_category="MANY_TO_ONE",
                cardinality="N:1",
                joinkeys=tuple(rel.join_keys),
            )
        )

    return KnowledgePackage(
        terms=tuple(terms),
        relations=tuple(relations),
        term_types=tuple(term_types),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# KPS 构建：视图
# ═══════════════════════════════════════════════════════════════════════════════


def _build_view_package(
    config: OwlGenConfig,
    view: ViewConfig,
    term_values: dict[str, list[dict[str, str]]] | None = None,
    term_type_defs: dict[str, tuple[str, str, str]] | None = None,
) -> KnowledgePackage:
    """为单个视图构建 KnowledgePackage。

    包含：视图本体术语 + 视图专属 prop 术语 + 值术语（可选）+ 视图关系（HAS_OBJECT/HAS_FIELD/MANY_TO_ONE）。
    """
    terms: list[TermDef] = [
        _build_term_def(
            config,
            term_code=view.view_code,
            term_name=view.view_name,
            term_type_code="view",
            term_desc=view.view_desc,
        )
    ]
    relations: list[RelationDef] = []

    # ── HAS_OBJECT：视图包含哪些对象 ──
    for obj_code in view.object_codes:
        source_term = f"{config.library_code}#view#{view.view_code}"
        target_term = f"{config.library_code}#object#{obj_code}"
        relations.append(
            RelationDef(
                source_term_code=source_term,
                target_term_code=target_term,
                relation_name=f"{view.view_name}_包含_{config.table_names.get(obj_code, obj_code)}",
                relation_category="HAS_OBJECT",
                cardinality="1:N",
            )
        )

    # ── HAS_FIELD：视图拥有的字段 ──
    for mapping in view.field_mappings:
        alias = mapping.property_name or mapping.source_object_column_code
        object_prop_code = config.resolve_object_prop_code(
            mapping.source_object_code,
            mapping.source_object_column_code,
        )
        target_code = object_prop_code
        if mapping.property_code not in {mapping.source_object_column_code, object_prop_code}:
            target_code = mapping.property_code

        source_term_vf = f"{config.library_code}#view#{view.view_code}"
        target_term_vf = f"{config.library_code}#prop#{target_code}"
        ext_field_v: dict[str, object] = {"field_alias": alias}
        if mapping.synonyms:
            ext_field_v["synonyms"] = mapping.synonyms
        relations.append(
            RelationDef(
                source_term_code=source_term_vf,
                target_term_code=target_term_vf,
                relation_name=f"{view.view_name}_拥有字段_{alias}",
                relation_category="HAS_FIELD",
                cardinality="1:N",
                ext_field=ext_field_v,
            )
        )

        # 视图专属 prop 术语
        if not config.force_view_prop_terms and mapping.property_code in {
            mapping.source_object_column_code,
            object_prop_code,
        }:
            continue
        terms.append(
            _build_term_def(
                config,
                term_code=mapping.property_code,
                term_name=mapping.property_name,
                term_type_code="prop",
                term_desc=f"视图属性：{mapping.property_name}",
                parent_term_code=view.view_code,
                synonyms=mapping.synonyms,
            )
        )

    # ── MANY_TO_ONE：视图内对象间的 JOIN 关系 ──
    obj_set = set(view.object_codes)
    for rel in config.object_relations:
        if rel.source_code in obj_set and rel.target_code in obj_set:
            source_term_o = f"{config.library_code}#object#{rel.source_code}"
            target_term_o = f"{config.library_code}#object#{rel.target_code}"
            relations.append(
                RelationDef(
                    source_term_code=source_term_o,
                    target_term_code=target_term_o,
                    relation_name=rel.relation_name,
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                    joinkeys=tuple(rel.join_keys),
                )
            )

    # ── 视图值术语（force_view_value_terms 模式）─────────────────────────
    if config.force_view_value_terms and term_values and term_type_defs:
        binding_lookup = {
            (binding.table_code, binding.column_name): binding for binding in config.term_bindings
        }
        emitted_props: set[str] = set()
        for mapping in view.field_mappings:
            binding = binding_lookup.get(
                (mapping.source_object_code, mapping.source_object_column_code)
            )
            if binding is None or mapping.property_code in emitted_props:
                continue
            emitted_props.add(mapping.property_code)
            type_name = term_type_defs.get(
                binding.term_type_code, (binding.term_type_code, "", "")
            )[0]
            for entry in term_values.get(binding.term_type_code, []):
                terms.append(
                    _build_term_def(
                        config,
                        term_code=entry["code"],
                        term_name=entry["name"],
                        term_type_code=binding.term_type_code,
                        term_desc=f"{type_name}术语：{entry['name']}",
                        parent_term_code=mapping.property_code,
                    )
                )

    return KnowledgePackage(
        terms=tuple(terms),
        relations=tuple(relations),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# KPS 文件写入
# ═══════════════════════════════════════════════════════════════════════════════


def _serialize_graph(graph: Any) -> str:
    """将 rdflib.Graph 序列化为 XML 字符串。"""
    result = graph.serialize(format="xml")
    return result if isinstance(result, str) else result.decode("utf-8")


def _write_kps_files(
    builder: Any,
    obj_dir: Path,
    pkg: KnowledgePackage,
) -> int:
    """将 KnowledgePackage 拆分为独立 OWL 文件并写入对象目录。

    Returns:
        写入的关系文件数。
    """
    code = pkg.terms[0].term_code
    gb = GraphBuilder()
    gb.add_package(pkg)

    # 术语类型
    tt_graph = gb.export_term_types_graph()
    write_text(obj_dir / f"{code}_term_types.owl", _serialize_graph(tt_graph))

    # 术语
    terms_graph = gb.export_terms_graph()
    write_text(obj_dir / f"{code}_terms.owl", _serialize_graph(terms_graph))

    # 关系：按类别拆分为 3 个文件
    count = 0
    filename_map: dict[str, str] = {
        "MANY_TO_ONE": f"{code}_object_relations.owl",
        "HAS_FIELD": f"{code}_attribute_relations.owl",
        "HAS_TERM": f"{code}_term_relations.owl",
    }
    for rel_cat, filename in filename_map.items():
        rel_graph = gb.export_relations_graph(rel_cat)
        if len(list(rel_graph.subjects())) == 0:
            continue
        write_text(obj_dir / filename, _serialize_graph(rel_graph))
        count += 1
    return count


def _write_kps_view_files(
    view_dir: Path,
    pkg: KnowledgePackage,
) -> int:
    """将视图 KnowledgePackage 拆分为独立 OWL 文件并写入视图目录。

    注意：_relations.owl 由 render_view_relations_for_view 单独生成（标准格式），
    此处只写 _terms.owl，不再重复写 _relations.owl。
    """
    code = pkg.terms[0].term_code
    gb = GraphBuilder()
    gb.add_package(pkg)

    # 术语
    terms_graph = gb.export_terms_graph()
    write_text(view_dir / f"{code}_terms.owl", _serialize_graph(terms_graph))
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════════════════


def _total_cols(tables: list[Table]) -> int:
    return sum(len(t.columns) for t in tables)


# ═══════════════════════════════════════════════════════════════════════════════
# 对话式本体管理入口
# ═══════════════════════════════════════════════════════════════════════════════

_SQL_TYPE_MAP: dict[str, str] = {
    "STRING": "VARCHAR(255)",
    "INTEGER": "INT",
    "FLOAT": "DOUBLE",
    "BOOLEAN": "TINYINT",
    "DATE": "DATE",
}


def generate_from_definition(workspace_state: dict[str, Any], output_dir: Path) -> None:
    """从对话式收集的 workspace_state 生成 OWL 导入包。

    workspace_state 可以是对象 state（含 entity_code）或视图 state（含 view_code）。
    """
    if "entity_code" in workspace_state:
        _generate_object(workspace_state, output_dir)
    elif "view_code" in workspace_state:
        _generate_view(workspace_state, output_dir)
    else:
        raise ValueError("workspace_state 必须包含 entity_code 或 view_code")


def _generate_object(state: dict[str, Any], output_dir: Path) -> None:
    """从对象 workspace_state 生成 OWL 导入包。"""
    from datacloud_knowledge.ingestion.owl_generate.models import Column, FieldRole, TermBinding

    entity_code: str = state["entity_code"]
    fields: list[dict[str, Any]] = state.get("fields", [])

    # 自动在最前面插入 id 主键字段（如果用户没有传）
    has_id = any(f.get("property_code", "").lower() == "id" for f in fields)
    if not has_id:
        # 非结构化（KNOWLEDGE_BASE）主键用 STRING，结构化（DYNAMIC_TABLE）用 INTEGER
        id_data_type = "STRING" if state.get("entity_source") == "KNOWLEDGE_BASE" else "INTEGER"
        id_field: dict[str, Any] = {
            "property_code": "id",
            "property_name": "主键",
            "data_type": id_data_type,
            "ext_property": {
                "property_role_rule": {"property_role": "MEASURE", "rule_type": "primary_key"}
            },
        }
        fields = [id_field, *fields]

    columns: list[Column] = [
        Column(
            name=f["property_code"],
            sql_type=_SQL_TYPE_MAP.get(f.get("data_type", "STRING"), "VARCHAR(255)"),
            nullable=True,
            comment=f.get("property_name", f["property_code"]),
        )
        for f in fields
    ]

    table = Table(
        code=entity_code,
        name=state.get("entity_name", entity_code),
        desc=state.get("entity_desc", ""),
        columns=columns,
    )

    field_roles: dict[tuple[str, str], FieldRole] = {}
    term_bindings: list[TermBinding] = []
    for f in fields:
        ext = f.get("ext_property") or {}
        role_rule = ext.get("property_role_rule") or {}
        if role_rule.get("property_role"):
            field_roles[(entity_code, f["property_code"])] = FieldRole(
                property_role=role_rule["property_role"],
                rule_type=role_rule.get("rule_type", "description"),
                formula=role_rule.get("formula", ""),
            )
        if f.get("term_type_code"):
            term_bindings.append(
                TermBinding(
                    table_code=entity_code,
                    column_name=f["property_code"],
                    term_type_code=f["term_type_code"],
                    term_data_type=f.get("term_data_type", "LIST_TERM"),
                )
            )

    config = OwlGenConfig(
        domain_code=state.get("domain_code", "PERSONAL_DOMAIN"),
        domain_name=state.get("domain_name", "个人领域"),
        domain_desc=state.get("domain_desc", ""),
        library_code=state.get("library_code", "PERSONAL_LIB"),
        library_name=state.get("library_name", "个人本体库"),
        library_desc=state.get("library_desc", ""),
        db_code=state.get("db_code", "personal_sqlite"),
        db_type=state.get("db_type", "PERSONAL_SQLITE"),
        db_params={},
        table_codes=[entity_code],
        table_names={entity_code: state.get("entity_name", entity_code)},
        table_descs={entity_code: state.get("entity_desc", "")},
        term_bindings=term_bindings,
        object_relations=[],
        output_dir=output_dir,
        field_roles=field_roles,
        entity_source=state.get("entity_source", "DYNAMIC_TABLE"),
        kb_id=state.get("kb_id", ""),
        kb_directory=state.get("kb_directory", ""),
    )

    generate_from_tables(config, [table], {})


def _generate_view(state: dict[str, Any], output_dir: Path) -> None:
    """从视图 workspace_state 生成 OWL 导入包。"""
    from datacloud_knowledge.ingestion.owl_generate.models import (
        FieldRole,
        ObjectRelation,
        ViewConfig,
        ViewFieldMapping,
    )

    view_code: str = state["view_code"]
    object_codes: list[str] = state.get("object_codes", [])
    raw_relations: list[dict[str, Any]] = state.get("object_relations", [])

    object_relations: list[ObjectRelation] = []
    for i, rel in enumerate(raw_relations):
        src = rel.get("source_object_code", "")
        tgt = rel.get("target_object_code", "")
        src_field = rel.get("source_object_field_code", "")
        tgt_field = rel.get("target_object_field_code", "")
        object_relations.append(
            ObjectRelation(
                relation_id=f"rel_{i}",
                source_code=src,
                target_code=tgt,
                relation_name=rel.get("relation_name", f"{src}_to_{tgt}"),
                join_keys=[{"source": src_field, "target": tgt_field}],
            )
        )

    # 从 object_relations 构建视图字段映射（每个关联字段对生成两个 SceneField）
    field_mappings: list[ViewFieldMapping] = []
    seen_fields: set[tuple[str, str]] = set()
    default_role = FieldRole(property_role="DIMENSION", rule_type="description")
    for rel in raw_relations:
        src_obj = rel.get("source_object_code", "")
        tgt_obj = rel.get("target_object_code", "")
        src_field = rel.get("source_object_field_code", "")
        tgt_field = rel.get("target_object_field_code", "")
        for obj_code, col_code in [(src_obj, src_field), (tgt_obj, tgt_field)]:
            if not obj_code or not col_code:
                continue
            key = (obj_code, col_code)
            if key in seen_fields:
                continue
            seen_fields.add(key)
            # 从 state 的 fields 里找字段名称和角色（如果有）
            field_name = col_code
            field_role = default_role
            for f in state.get("fields", []):
                if f.get("property_code") == col_code:
                    field_name = f.get("property_name", col_code)
                    ext = (f.get("ext_property") or {}).get("property_role_rule", {})
                    if ext.get("property_role"):
                        field_role = FieldRole(
                            property_role=ext["property_role"],
                            rule_type=ext.get("rule_type", "description"),
                        )
                    break
            field_mappings.append(
                ViewFieldMapping(
                    property_code=col_code,
                    property_name=field_name,
                    source_object_code=obj_code,
                    source_object_column_code=col_code,
                    role=field_role,
                )
            )

    view = ViewConfig(
        view_code=view_code,
        view_name=state.get("view_name", view_code),
        view_desc=state.get("view_desc", ""),
        object_codes=object_codes,
        field_mappings=field_mappings,
    )

    config = OwlGenConfig(
        domain_code=state.get("domain_code", "PERSONAL_DOMAIN"),
        domain_name=state.get("domain_name", "个人领域"),
        domain_desc=state.get("domain_desc", ""),
        library_code=state.get("library_code", "PERSONAL_LIB"),
        library_name=state.get("library_name", "个人本体库"),
        library_desc=state.get("library_desc", ""),
        db_code=state.get("db_code", "personal_sqlite"),
        db_type=state.get("db_type", "PERSONAL_SQLITE"),
        db_params={},
        table_codes=object_codes,
        table_names={c: c for c in object_codes},
        table_descs=dict.fromkeys(object_codes, ""),
        term_bindings=[],
        object_relations=object_relations,
        output_dir=output_dir,
        views=[view],
    )

    generate_from_tables(config, [], {})
