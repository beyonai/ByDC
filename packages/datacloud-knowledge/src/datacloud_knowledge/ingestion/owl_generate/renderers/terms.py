"""术语定义 OWL 渲染 — 基于 GraphBuilder API。

迁移说明：
- _term_item() f-string 模板 → _build_term_def() 构建 KPS TermDef
- _wrap_terms() XML 包装 → GraphBuilder.add_terms() + export_terms_graph() + serialize
- code_path 格式从"OBJECT#code"/"PROP#code"等旧格式统一为
  TermDef.compute_term_id() 的 {library}#{type}#{code} 标准格式（对齐任务 1.5/1.8）
"""

from __future__ import annotations

from collections import OrderedDict

from datacloud_knowledge.contracts.kps import TermDef
from datacloud_knowledge.ingestion.owl_generate.graph_builder import GraphBuilder
from datacloud_knowledge.ingestion.owl_generate.models import OwlGenConfig, Table, ViewConfig

# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助：构建 KPS TermDef
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
    """从旧 _term_item() 参数构建 KPS TermDef 对象。

    code_path（旧格式：OBJECT#code / PROP#code）不再作为独立字段存储，
    统一由 TermDef.compute_term_id() 在序列化时动态计算。
    """
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


def _serialize_terms_xml(builder: GraphBuilder) -> str:
    """将 GraphBuilder 中所有术语序列化为 XML 字符串。"""
    terms_graph = builder.export_terms_graph()
    result = terms_graph.serialize(format="xml")
    return result if isinstance(result, str) else result.decode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# OWL 渲染（GraphBuilder API）
# ═══════════════════════════════════════════════════════════════════════════════


def render_terms(
    config: OwlGenConfig,
    tables: list[Table],
    term_values: dict[str, list[dict[str, str]]],
    term_type_defs: OrderedDict[str, tuple[str, str, str]],
) -> dict[str, tuple[str, int]]:
    """渲染术语定义 OWL，按类型拆文件。

    兼容旧接口，内部使用 GraphBuilder API。
    返回 ``{relative_path: (content, count)}``：
    - ``terms/terms_ontology.owl`` — 对象/动作/视图/属性术语
    - ``terms/terms_{type_code}.owl`` — 每种值术语类型一个文件
    """
    result: dict[str, tuple[str, int]] = {}

    # ── 本体术语（对象/动作/视图/属性）──
    ontology_terms: list[TermDef] = []

    # 对象术语
    for table in tables:
        ontology_terms.append(
            _build_term_def(
                config,
                term_code=table.code,
                term_name=table.name,
                term_type_code="object",
                term_desc=table.desc,
            )
        )

    # 动作术语
    for table in tables:
        action_code = f"query_{table.code}"
        ontology_terms.append(
            _build_term_def(
                config,
                term_code=action_code,
                term_name=f"查询{table.name}",
                term_type_code="action",
                term_desc=f"{table.name}查询动作",
            )
        )

    # 视图术语
    for v in config.resolved_views():
        ontology_terms.append(
            _build_term_def(
                config,
                term_code=v.view_code,
                term_name=v.view_name,
                term_type_code="view",
                term_desc=v.view_desc,
            )
        )

    # 属性术语 (prop)：跨对象同名字段只保留首个定义
    seen_prop_codes: set[str] = set()
    for table in tables:
        for col in table.columns:
            resolved_prop = config.resolve_object_prop(
                table.code, col.name, col.comment or col.name
            )
            if resolved_prop.property_code in seen_prop_codes:
                continue
            seen_prop_codes.add(resolved_prop.property_code)
            ontology_terms.append(
                _build_term_def(
                    config,
                    term_code=resolved_prop.property_code,
                    term_name=resolved_prop.property_name,
                    term_type_code="prop",
                    term_desc=resolved_prop.property_desc,
                    synonyms=resolved_prop.synonyms,
                )
            )

    if ontology_terms:
        builder = GraphBuilder()
        builder.add_terms(ontology_terms)
        result["terms/terms_ontology.owl"] = (
            _serialize_terms_xml(builder),
            len(ontology_terms),
        )

    # ── 值术语（每种类型一个文件）──
    for type_code, values in term_values.items():
        type_name = term_type_defs.get(type_code, (type_code, "", ""))[0]
        value_terms: list[TermDef] = []
        for entry in values:
            value_terms.append(
                _build_term_def(
                    config,
                    term_code=entry["code"],
                    term_name=entry["name"],
                    term_type_code=type_code,
                    term_desc=f"{type_name}术语：{entry['name']}",
                    parent_term_code=entry.get("parent_prop_code", ""),
                )
            )
        if value_terms:
            builder = GraphBuilder()
            builder.add_terms(value_terms)
            result[f"terms/terms_{type_code}.owl"] = (
                _serialize_terms_xml(builder),
                len(value_terms),
            )

    return result


def render_terms_for_object(
    config: OwlGenConfig,
    table: Table,
    term_values: dict[str, list[dict[str, str]]],
    term_type_defs: OrderedDict[str, tuple[str, str, str]],
    seen_prop_codes: set[str] | None = None,
) -> tuple[str, int]:
    """渲染单个对象下的所有术语（object + prop + 值术语）— GraphBuilder API。

    业务逻辑：
    1. 创建对象本体术语（object）；
    2. 为该表的每个字段创建属性术语（prop），跨对象去重；
    3. 为该表绑定的值术语类型创建值术语（LIST_TERM/DICT_TERM）。

    产物写入 {object_code}_terms.owl 文件。

    Returns:
        (XML 字符串, 术语数量) 元组。
    """
    terms: list[TermDef] = []
    prop_codes = seen_prop_codes if seen_prop_codes is not None else set()

    # 对象本体术语
    terms.append(
        _build_term_def(
            config,
            term_code=table.code,
            term_name=table.name,
            term_type_code="object",
            term_desc=table.desc,
        )
    )

    # 属性术语（prop）：跨对象去重
    for col in table.columns:
        resolved_prop = config.resolve_object_prop(table.code, col.name, col.comment or col.name)
        if resolved_prop.property_code in prop_codes:
            continue
        prop_codes.add(resolved_prop.property_code)
        terms.append(
            _build_term_def(
                config,
                term_code=resolved_prop.property_code,
                term_name=resolved_prop.property_name,
                term_type_code="prop",
                term_desc=resolved_prop.property_desc,
                synonyms=resolved_prop.synonyms,
            )
        )

    # 值术语：从 term_bindings 收集当前表的绑定类型，展开 DISTINCT 值
    binding_lookup = {b.column_name: b for b in config.term_bindings if b.table_code == table.code}
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

    builder = GraphBuilder()
    builder.add_terms(terms)
    return (_serialize_terms_xml(builder), len(terms))


def render_terms_for_view(
    config: OwlGenConfig,
    view: ViewConfig,
    term_values: dict[str, list[dict[str, str]]] | None = None,
    term_type_defs: OrderedDict[str, tuple[str, str, str]] | None = None,
) -> tuple[str, int]:
    """渲染单个视图的术语定义 — GraphBuilder API。

    业务逻辑：
    1. 创建视图本体术语（view）；
    2. 对 property_code 不同于源对象字段的视图映射，生成独立 prop 术语；
    3. 若启用了 force_view_value_terms，为绑定字段生成值术语副本。

    产物写入 {view_code}_terms.owl 文件。
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

    # 视图专属 prop 术语：property_code 不同于源对象字段的映射
    for mapping in view.field_mappings:
        object_prop_code = config.resolve_object_prop_code(
            mapping.source_object_code,
            mapping.source_object_column_code,
        )
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
                synonyms=mapping.synonyms,
            )
        )

    # 视图值术语：force_view_value_terms 模式下为绑定字段生成值术语副本
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

    builder = GraphBuilder()
    builder.add_terms(terms)
    return (_serialize_terms_xml(builder), len(terms))
