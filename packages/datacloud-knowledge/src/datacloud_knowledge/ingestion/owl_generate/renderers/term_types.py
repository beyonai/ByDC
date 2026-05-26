"""术语类型 OWL 渲染 — 基于 GraphBuilder API。

迁移模式（meta.py 后第二个迁移的 renderer）：
1. 保留纯数据函数（build_term_type_defs, enrich_term_type_names）不变；
2. 渲染函数内部构建 KPS TermTypeDef → 调用 GraphBuilder.add_term_types() → 序列化；
3. 函数签名保持向后兼容（返回 XML 字符串），generator.py 无需修改。
"""

from __future__ import annotations

from collections import OrderedDict

from datacloud_knowledge.contracts.kps import TermTypeDef
from datacloud_knowledge.ingestion.owl_generate.graph_builder import GraphBuilder
from datacloud_knowledge.ingestion.owl_generate.models import OwlGenConfig, Table

# ═══════════════════════════════════════════════════════════════════════════════
# 术语类型定义构建（纯数据函数，无 XML 渲染，不变）
# ═══════════════════════════════════════════════════════════════════════════════


def build_term_type_defs(
    config: OwlGenConfig,
) -> OrderedDict[str, tuple[str, str, str]]:
    """构建术语类型定义表：code → (name, desc, data_type)。

    包含固定的本体术语类型 + 从 term_bindings 收集的值术语类型
    + ONTOLOGY_PROP（属性术语类型，补全缺失层）。
    """
    defs: OrderedDict[str, tuple[str, str, str]] = OrderedDict()
    # 固定本体术语类型
    defs["object"] = ("对象", "对象本体术语类型", "ONTOLOGY_TERM")
    defs["action"] = ("动作", "动作本体术语类型", "ONTOLOGY_TERM")
    defs["view"] = ("视图", "视图本体术语类型", "ONTOLOGY_TERM")
    # 属性术语类型（补全缺失层）
    defs["prop"] = ("属性", "属性/字段本体术语类型", "ONTOLOGY_TERM")
    # 从 term_bindings 收集值术语类型
    seen: set[str] = set()
    for binding in config.term_bindings:
        if binding.term_type_code in seen:
            continue
        seen.add(binding.term_type_code)
        configured_type = config.resolve_term_type(binding.term_type_code)
        type_name = (
            configured_type.type_name if configured_type is not None else binding.term_type_code
        )
        type_desc = (
            configured_type.type_desc
            if configured_type is not None and configured_type.type_desc
            else f"{type_name}术语类型"
        )
        defs[binding.term_type_code] = (
            type_name,
            type_desc,
            binding.term_data_type,
        )
    return defs


def enrich_term_type_names(
    defs: OrderedDict[str, tuple[str, str, str]],
    tables: list[Table],
    config: OwlGenConfig,
) -> None:
    """用表字段注释替换术语类型名称（就地修改）。"""
    col_comments: dict[str, str] = {}
    for table in tables:
        for col in table.columns:
            if col.comment:
                col_comments.setdefault(col.name, col.comment)
    for binding in config.term_bindings:
        code = binding.term_type_code
        if code in defs:
            old_name, _old_desc, data_type = defs[code]
            if config.resolve_term_type(code) is not None:
                continue
            comment = col_comments.get(binding.column_name, "")
            if comment and old_name == code:
                defs[code] = (comment, f"{comment}术语类型", data_type)


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助：旧格式 → KPS TermTypeDef 转换
# ═══════════════════════════════════════════════════════════════════════════════


def _term_data_type_to_category(term_data_type: str) -> int:
    """将旧 term_data_type 字符串映射为 KPS type_category 整数。

    KPS TermTypeDef.type_category 语义：
    1 = LIST_TERM（列表术语），2 = DICT_TERM（字典术语），
    3 = ONTOLOGY_TERM（本体术语），4 = DOC_NAME_TERM（文档名称术语）。
    """
    _mapping: dict[str, int] = {
        "ONTOLOGY_TERM": 3,
        "LIST_TERM": 1,
        "DICT_TERM": 2,
        "DOC_NAME_TERM": 4,
    }
    return _mapping.get(term_data_type, 3)


def _term_type_defs_to_kps(
    term_type_defs: OrderedDict[str, tuple[str, str, str]],
    type_codes: set[str] | None = None,
) -> list[TermTypeDef]:
    """将 build_term_type_defs() 的旧格式输出转为 KPS TermTypeDef 列表。

    Args:
        term_type_defs: code → (name, desc, term_data_type) 映射。
        type_codes: 要包含的 type_code 集合，None 表示全部。
    """
    result: list[TermTypeDef] = []
    for type_code, (name, desc, term_data_type) in term_type_defs.items():
        if type_codes is not None and type_code not in type_codes:
            continue
        result.append(
            TermTypeDef(
                type_code=type_code,
                type_name=name,
                type_category=_term_data_type_to_category(term_data_type),
                type_desc=desc,
            )
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# OWL 渲染（GraphBuilder API）
# ═══════════════════════════════════════════════════════════════════════════════


def _serialize_xml(builder: GraphBuilder) -> str:
    """将 GraphBuilder 的图序列化为 XML 字符串。"""
    result = builder.build().serialize(format="xml")
    return result if isinstance(result, str) else result.decode("utf-8")


def render_term_types(
    config: OwlGenConfig,
    defs: OrderedDict[str, tuple[str, str, str]],
) -> str:
    """术语类型定义 OWL — 使用 GraphBuilder 构建并序列化。

    将所有术语类型（本体 + 值术语）注册到一个 GraphBuilder 图中，
    通过 rdflib serialize 产出标准 RDF/XML 字符串。

    Args:
        config: 生成配置（未使用，保留签名兼容）。
        defs: build_term_type_defs() 的返回结果。
    """
    term_types = _term_type_defs_to_kps(defs)
    builder = GraphBuilder()
    builder.add_term_types(term_types)
    return _serialize_xml(builder)


def render_term_types_for_object(
    config: OwlGenConfig,
    table: Table,
    term_type_defs: OrderedDict[str, tuple[str, str, str]],
) -> str:
    """渲染单个对象涉及的术语类型定义 — 使用 GraphBuilder 构建并序列化。

    业务逻辑：从 term_type_defs 中筛选当前表绑定的术语类型
    （object + prop + 表专属的值术语类型），构造 TermTypeDef 列表，
    通过 GraphBuilder 注册到 rdflib.Graph 后序列化输出。
    产物写入 {object_code}_term_types.owl 文件。

    Args:
        config: 生成配置（用于查询当前表的 term_bindings）。
        table: 当前对象表。
        term_type_defs: build_term_type_defs() 的返回结果。
    """
    # 收集当前对象涉及的术语类型编码
    type_codes: set[str] = {"object", "prop"}
    for binding in config.term_bindings:
        if binding.table_code == table.code:
            type_codes.add(binding.term_type_code)

    # 构建 KPS TermTypeDef 列表
    term_types = _term_type_defs_to_kps(term_type_defs, type_codes)

    # 使用 GraphBuilder 构建图并序列化
    builder = GraphBuilder()
    builder.add_term_types(term_types)
    return _serialize_xml(builder)
