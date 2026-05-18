"""GraphBuilder — 基于 RDFLib Graph 的 OWL 知识包序列化器。

GraphBuilder 是生成器从字符串模板（f-string）迁移到标准 RDF Graph API 的核心组件。
它接收 KnowledgePackage（KPS）对象，构建 rdflib.Graph，
再通过 graph.serialize(format="xml") 产出标准 RDF/XML 文件。

设计原则：
- 一个 GraphBuilder 实例代表一个知识包的图（可拆分为多个文件图）。
- 命名空间对齐现有 OWL 格式（xml:base + 默认 ns），保证导入端兼容。
- 所有实体类型使用 owl:NamedIndividual + rdf:type 建模。
- 属性值使用 owl:DatatypeProperty（字符串）或 owl:ObjectProperty（引用）。
- 不依赖 _xml.py（GraphBuilder 内置 XML 工具函数），renderers 全部迁移后可删除 _xml.py。

用法示例:
    from datacloud_knowledge.contracts.kps import KnowledgePackage, TermDef, RelationDef
    from datacloud_knowledge.ingestion.owl_generate.graph_builder import GraphBuilder

    pkg = KnowledgePackage(terms=(...), relations=(...), ...)
    builder = GraphBuilder()
    builder.add_terms(pkg.terms)       # 添加术语定义
    builder.add_relations(pkg.relations)  # 添加关系定义
    graph = builder.build()           # 获取 RDFLib Graph
    graph.serialize("output.owl", format="xml")
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from typing import Any

from datacloud_knowledge.contracts.kps import (
    ActionDef,
    ActionParamDef,
    DomainDef,
    KnowledgePackage,
    LibraryDef,
    RelationDef,
    TermDef,
    TermTypeDef,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# RDF 命名空间
# ═══════════════════════════════════════════════════════════════════════════════

_OWL_NS = "http://www.w3.org/2002/07/owl#"
_RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
_XSD_NS = "http://www.w3.org/2001/XMLSchema#"

# 默认 xml:base（与应用本体命名空间保持一致）
_DEFAULT_BASE = "http://beyond.ai/ontology#"

# ═══════════════════════════════════════════════════════════════════════════════
# OWL 实体类型 → RDF Class 映射
# ═══════════════════════════════════════════════════════════════════════════════

# KPS 类型 → RDF class 名称（使用 # 前缀，对齐现有 OWL 格式）
_ENTITY_CLASS_MAP: dict[str, str] = {
    "DomainDef": "#DomainDefinition",
    "LibraryDef": "#LibraryDefinition",
    "TermTypeDef": "#TermTypeDefinition",
    "TermDef": "#TermDefinition",
    "ActionDef": "#ActionDefinition",
    "RelationDef": "#TermRelation",
}

# ═══════════════════════════════════════════════════════════════════════════════
# XML 工具函数（内置于 GraphBuilder，_xml.py 删除后不依赖外部）
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_xml_id(value: str, max_len: int = 200) -> str:
    """将字符串转为合法 XML NCName 片段。"""
    return re.sub(r"[^\w]", "_", value)[:max_len]


def _serialize_truthy(value: object) -> str:
    """将 Python bool 序列化为 RDF xsd:boolean 字面值。"""
    return "true" if value else "false"


# ═══════════════════════════════════════════════════════════════════════════════
# 数据类型映射（从 _xml.py 迁移）
# ═══════════════════════════════════════════════════════════════════════════════


def map_data_type(sql_type: str, column_name: str = "") -> str:
    """MySQL/PostgreSQL 类型 → OWL data_type。"""
    raw = sql_type.lower()
    if column_name.startswith("is_") or raw in {"tinyint(1)", "boolean"}:
        return "BOOLEAN"
    if raw.startswith(("tinyint", "int", "smallint", "integer")):
        return "INT"
    if raw.startswith("bigint"):
        return "BIGINT"
    if raw.startswith(("decimal", "double", "float", "numeric", "real")):
        return "DOUBLE"
    if raw.startswith(("datetime", "date", "timestamp", "time")):
        return "DATE"
    return "STRING"


# ═══════════════════════════════════════════════════════════════════════════════
# GraphBuilder — 核心类
# ═══════════════════════════════════════════════════════════════════════════════


class GraphBuilder:
    """OWL 知识包图构建器。

    维护一个 rdflib.ConjunctiveGraph，通过 add_* 方法逐个添加实体，
    最终 build() 返回 Graph 对象供序列化。

    支持多图拆分模式：通过 new_subgraph() 创建独立的子图，
    用于按对象/视图拆分输出多个 OWL 文件。
    """

    def __init__(self, base: str = _DEFAULT_BASE) -> None:
        """初始化 GraphBuilder。

        Args:
            base: XML base URI，默认为 http://beyond.ai/ontology#。
        """
        # 延迟导入 rdflib，避免作为强制依赖
        from rdflib import OWL, RDF, RDFS, XSD, Graph, Namespace

        self._graph = Graph()
        self._base = base
        self._RDF = RDF
        self._RDFS = RDFS
        self._OWL = OWL
        self._XSD = XSD

        # 创建默认命名空间（作为三元组谓词的命名空间前缀）
        self._ns = Namespace(base)

        # 绑定命名空间前缀
        self._graph.bind("", self._ns)
        self._graph.bind("owl", OWL)
        self._graph.bind("rdf", RDF)
        self._graph.bind("rdfs", RDFS)
        self._graph.bind("xsd", XSD)

    # ── 图操作 ──────────────────────────────────────────────────────────────

    def build(self) -> Any:
        """返回构建完成的 RDFLib Graph，可用于 serialize()。

        Returns:
            rdflib.Graph 实例。
        """
        return self._graph

    def add_to(self, target: Any) -> None:
        """将当前图的所有三元组合并到目标 Graph。

        Args:
            target: 目标 rdflib.Graph 实例。
        """
        for triple in self._graph:
            target.add(triple)

    # ── DomainDef ────────────────────────────────────────────────────────────

    def add_domain(self, domain: DomainDef) -> None:
        """添加领域定义到图中。

        领域不作为独立 OWL 文件产出（信息由 term 的 domain_code 字段承载），
        但域本身需要定义为 owl:NamedIndividual 供引用。

        Args:
            domain: DomainDef 实例。
        """
        uri = self._ns[f"domain_{_safe_xml_id(domain.domain_code)}"]
        self._graph.add((uri, self._RDF.type, self._ns.DomainDefinition))
        self._add_literal(uri, self._ns.domainCode, domain.domain_code)
        self._add_literal(uri, self._ns.domainName, domain.domain_name)
        if domain.parent_code:
            self._add_literal(uri, self._ns.parentCode, domain.parent_code)
        if domain.domain_desc:
            self._add_literal(uri, self._ns.domainDesc, domain.domain_desc)

    # ── LibraryDef ───────────────────────────────────────────────────────────

    def add_library(self, library: LibraryDef) -> None:
        """添加术语库定义到图中。

        Args:
            library: LibraryDef 实例。
        """
        uri = self._ns[f"library_{_safe_xml_id(library.library_code)}"]
        self._graph.add((uri, self._RDF.type, self._ns.LibraryDefinition))
        self._add_literal(uri, self._ns.libraryCode, library.library_code)
        self._add_literal(uri, self._ns.libraryName, library.library_name)
        if library.library_desc:
            self._add_literal(uri, self._ns.libraryDesc, library.library_desc)

    # ── TermTypeDef ──────────────────────────────────────────────────────────

    def add_term_types(self, term_types: Iterable[TermTypeDef]) -> None:
        """批量添加术语类型定义到图中。

        Args:
            term_types: TermTypeDef 可迭代对象。
        """
        for tt in term_types:
            self._add_term_type(tt)

    def _add_term_type(self, tt: TermTypeDef) -> None:
        """添加单个术语类型定义。

        Args:
            tt: TermTypeDef 实例。
        """
        uri = self._ns[f"termtype_{_safe_xml_id(tt.type_code)}"]
        self._graph.add((uri, self._RDF.type, self._ns.TermTypeDefinition))
        # 术语类型编码（保留旧命名风格兼容性：trem字样）
        self._add_literal(uri, self._ns.trem_type_code_path, tt.type_code)
        self._add_literal(uri, self._ns.trem_type_code, tt.type_code)
        self._add_literal(uri, self._ns.trem_type_name, tt.type_name)
        self._add_literal(uri, self._ns.trem_type_category, str(tt.type_category))
        if tt.type_desc:
            self._add_literal(uri, self._ns.trem_type_desc, tt.type_desc)

    # ── TermDef ──────────────────────────────────────────────────────────────

    def add_terms(self, terms: Iterable[TermDef]) -> None:
        """批量添加术语定义到图中。

        Args:
            terms: TermDef 可迭代对象。
        """
        for term in terms:
            self._add_term(term)

    def _add_term(self, term: TermDef) -> None:
        """添加单个术语定义。

        Args:
            term: TermDef 实例。
        """
        term_id = term.compute_term_id()
        uri = self._ns[f"term_{_safe_xml_id(term_id)}"]
        self._graph.add((uri, self._RDF.type, self._ns.TermDefinition))

        # 核心标识字段
        self._add_literal(uri, self._ns.term_code_path, term_id)
        self._add_literal(uri, self._ns.term_code, term.term_code)
        self._add_literal(uri, self._ns.term_name, term.term_name)
        self._add_literal(uri, self._ns.term_type_code, term.term_type_code)
        self._add_literal(uri, self._ns.library_code, term.library_code)
        self._add_literal(uri, self._ns.domain_code, term.domain_code)

        # 层级关系
        if term.parent_term_code:
            self._add_literal(uri, self._ns.parent_term_code, term.parent_term_code)

        # 同义词（JSON 序列化）
        if term.synonyms:
            self._add_literal(
                uri, self._ns.synonyms, json.dumps(list(term.synonyms), ensure_ascii=False)
            )

        # 描述
        if term.term_desc:
            self._add_literal(uri, self._ns.term_desc, term.term_desc)

    # ── RelationDef ──────────────────────────────────────────────────────────

    def add_relations(self, relations: Iterable[RelationDef]) -> None:
        """批量添加关系定义到图中。

        Args:
            relations: RelationDef 可迭代对象。
        """
        for rel in relations:
            self._add_relation(rel)

    def _add_relation(self, rel: RelationDef) -> None:
        """添加单个关系定义。

        Args:
            rel: RelationDef 实例。
        """
        rel_id = f"rel_{_safe_xml_id(rel.source_term_code)}_to_{_safe_xml_id(rel.target_term_code)}"
        uri = self._ns[rel_id]
        self._graph.add((uri, self._RDF.type, self._ns.TermRelation))

        # 源和目标编码
        self._add_literal(uri, self._ns.sourceTermCode, rel.source_term_code)
        self._add_literal(uri, self._ns.targetTermCode, rel.target_term_code)

        # 关系元数据
        self._add_literal(uri, self._ns.relationName, rel.relation_name)
        self._add_literal(uri, self._ns.relationCategory, rel.relation_category)
        self._add_literal(uri, self._ns.cardinality, rel.cardinality)

        # JOIN 键（JSON 序列化），仅 MANY_TO_ONE 关系有值
        if rel.joinkeys:
            self._add_literal(
                uri,
                self._ns.joinkeys,
                json.dumps(list(rel.joinkeys), ensure_ascii=False),
            )

        # 扩展字段
        if rel.ext_field:
            self._add_literal(
                uri,
                self._ns.extField,
                json.dumps(rel.ext_field, ensure_ascii=False),
            )

    # ── ActionDef ────────────────────────────────────────────────────────────

    def add_actions(self, actions: Iterable[ActionDef]) -> None:
        """批量添加 Action 定义到图中。

        Args:
            actions: ActionDef 可迭代对象。
        """
        for action in actions:
            self._add_action(action)

    def _add_action(self, action: ActionDef) -> None:
        """添加单个 Action 定义。

        Args:
            action: ActionDef 实例。
        """
        uri = self._ns[f"action_{_safe_xml_id(action.action_code)}"]
        self._graph.add((uri, self._RDF.type, self._ns.ActionDefinition))

        self._add_literal(uri, self._ns.actionCode, action.action_code)
        self._add_literal(uri, self._ns.actionName, action.action_name)
        self._add_literal(uri, self._ns.actionType, action.action_type)
        self._add_literal(uri, self._ns.requestUrl, action.request_url)
        self._add_literal(uri, self._ns.requestMethod, action.request_method)

        for param in action.request_params:
            self._add_action_param(uri, param, "RequestParameter")
        for param in action.response_params:
            self._add_action_param(uri, param, "ResponseParameter")

    def _add_action_param(self, action_uri: Any, param: ActionParamDef, param_type: str) -> None:
        """添加 Action 的参数定义。

        Args:
            action_uri: Action 的 RDF URI。
            param: ActionParamDef 实例。
            param_type: "RequestParameter" 或 "ResponseParameter"。
        """
        param_uri = self._ns[f"param_{_safe_xml_id(param.param_code)}_{_safe_xml_id(param_type)}"]
        self._graph.add((param_uri, self._RDF.type, self._ns[param_type]))
        self._add_literal(param_uri, self._ns.paramCode, param.param_code)
        self._add_literal(param_uri, self._ns.paramType, param.param_type)
        self._add_literal(param_uri, self._ns.description, param.description)
        self._add_literal(
            param_uri,
            self._ns.isRequired,
            _serialize_truthy(param.is_required),
        )

    # ── KnowledgePackage ─────────────────────────────────────────────────────

    def add_package(self, pkg: KnowledgePackage) -> None:
        """从 KnowledgePackage 一次性添加所有实体。

        这是批量导入的便捷方法，等价于依次调用各个 add_* 方法。

        Args:
            pkg: KnowledgePackage 实例。
        """
        for domain in pkg.domains:
            self.add_domain(domain)
        for library in pkg.libraries:
            self.add_library(library)
        self.add_term_types(pkg.term_types)
        self.add_terms(pkg.terms)
        self.add_relations(pkg.relations)
        self.add_actions(pkg.actions)

    # ── EntityDefinition & EntityField（对象定义）─────────────────────────────
    # 定义级实体（非 KPS），用于 _definition.owl / _mapping.owl / _dbsource.owl 文件

    def add_entity_definition(
        self,
        object_code: str,
        object_name: str,
        object_desc: str = "",
        action_refs: str = "",
        relation_refs: str = "",
        field_refs: list[str] | None = None,
    ) -> None:
        """添加 EntityDefinition（对象/实体定义）到图中。

        Args:
            object_code: 对象编码。
            object_name: 对象中文名称。
            object_desc: 对象描述。
            action_refs: JSON 数组字符串，引用的 Action 列表。
            relation_refs: JSON 数组字符串，引用的关系 ID 列表。
            field_refs: 字段引用 ID 列表（如 ["customer_code_field"]）。
        """
        uri = self._ns[f"{_safe_xml_id(object_code)}_v1"]
        self._graph.add((uri, self._RDF.type, self._ns.EntityDefinition))
        self._add_literal(uri, self._ns.entityCode, object_code)
        self._add_literal(uri, self._ns.entityName, object_name)
        self._add_literal(uri, self._ns.entityDesc, object_desc)
        self._add_literal(uri, self._ns.version, "1.0")
        self._add_literal(uri, self._ns.entitySource, "DB")
        if field_refs:
            for ref_id in field_refs:
                self._graph.add((uri, self._ns.fields, self._ns[ref_id]))
        if action_refs:
            self._add_literal(uri, self._ns.actionRefs, action_refs)
        if relation_refs:
            self._add_literal(uri, self._ns.relations, relation_refs)

    def add_entity_field(self, props: dict[str, str]) -> None:
        """添加 EntityField（实体字段定义）到图中。

        Args:
            props: 字段属性字典，key 对应 OWL property 名（驼峰），
                  必含 propertyCode, propertyName, dataType, sourceColumn。
        """
        uri = self._ns[f"{_safe_xml_id(props['propertyCode'])}_field"]
        self._graph.add((uri, self._RDF.type, self._ns.EntityField))
        self._add_literal(uri, self._ns.propertyCode, props["propertyCode"])
        self._add_literal(uri, self._ns.propertyName, props["propertyName"])
        self._add_literal(uri, self._ns.dataType, props["dataType"])
        self._add_literal(uri, self._ns.isRequired, props.get("isRequired", "false"))
        self._add_literal(uri, self._ns.defaultValue, props.get("defaultValue", ""))
        self._add_literal(uri, self._ns.sourceColumn, props["sourceColumn"])
        self._add_literal(uri, self._ns.synonyms, props.get("synonyms", ""))
        self._add_literal(uri, self._ns.dataFormat, props.get("dataFormat", ""))
        self._add_literal(uri, self._ns.measurementUnit, props.get("measurementUnit", ""))
        self._add_literal(uri, self._ns.propertyCategory, props.get("propertyCategory", ""))
        self._add_literal(uri, self._ns.propertyGroup, props.get("propertyGroup", "STORAGE"))
        self._add_literal(uri, self._ns.extProperty, props.get("extProperty", ""))
        self._add_literal(uri, self._ns.termTypeCodePath, props.get("termTypeCodePath", ""))
        self._add_literal(uri, self._ns.libraryCode, props.get("libraryCode", ""))
        self._add_literal(uri, self._ns.relAction, props.get("relAction", "[]"))
        self._add_literal(uri, self._ns.relTermCodeorname, props.get("relTermCodeorname", ""))
        self._add_literal(uri, self._ns.termDataType, props.get("termDataType", ""))

    # ── EntityMapping & Mapping（对象映射）────────────────────────────────────

    def add_entity_mapping(
        self,
        object_code: str,
        object_name: str,
        object_desc: str = "",
        mapping_refs: list[str] | None = None,
    ) -> None:
        """添加 EntityMapping（表级映射容器）。

        Args:
            mapping_refs: 映射引用 ID 列表（如 ["prop_code_mapping"]），通过 owl:ObjectProperty 关联。
        """
        uri = self._ns[f"{_safe_xml_id(object_code)}_mapping"]
        self._graph.add((uri, self._RDF.type, self._ns.EntityMapping))
        self._add_literal(uri, self._ns.entityCode, object_code)
        self._add_literal(uri, self._ns.entityName, object_name)
        self._add_literal(uri, self._ns.entityDesc, object_desc)
        self._add_literal(uri, self._ns.version, "1.0")
        if mapping_refs:
            for ref_id in mapping_refs:
                self._graph.add((uri, self._ns.mapping, self._ns[ref_id]))

    def add_field_mapping(self, props: dict[str, str]) -> None:
        """添加 Mapping（字段级映射项）。

        Args:
            props: 映射属性字典，含 propertyCode, propertyName,
                   sourceTableCode, sourceColumnCode, sourceDatasourceCode, extProperty。
        """
        uri = self._ns[f"{_safe_xml_id(props['propertyCode'])}_mapping"]
        self._graph.add((uri, self._RDF.type, self._ns.Mapping))
        self._add_literal(uri, self._ns.propertyCode, props["propertyCode"])
        self._add_literal(uri, self._ns.propertyName, props["propertyName"])
        self._add_literal(uri, self._ns.sourceTableCode, props["sourceTableCode"])
        self._add_literal(uri, self._ns.sourceColumnCode, props["sourceColumnCode"])
        self._add_literal(uri, self._ns.sourceDatasourceCode, props["sourceDatasourceCode"])
        self._add_literal(uri, self._ns.extProperty, props.get("extProperty", ""))

    # ── DatabaseDefinition（数据源）───────────────────────────────────────────

    def add_dbsource(self, db_code: str, db_type: str, db_params_json: str) -> None:
        """添加 DatabaseDefinition（数据源定义）。"""
        uri = self._ns[f"dbsource_{_safe_xml_id(db_code)}"]
        self._graph.add((uri, self._RDF.type, self._ns.DatabaseDefinition))
        self._add_literal(uri, self._ns.dbCode, db_code)
        self._add_literal(uri, self._ns.dbType, db_type)
        self._add_literal(uri, self._ns.dbParams, db_params_json)

    # ── SceneDefinition & SceneField（视图定义）──────────────────────────────

    def add_scene_definition(
        self,
        view_code: str,
        view_name: str,
        view_desc: str = "",
        object_codes_json: str = "",
        relations_json: str = "",
        field_refs: list[str] | None = None,
    ) -> None:
        """添加 SceneDefinition（视图/场景定义）。"""
        uri = self._ns[f"{_safe_xml_id(view_code)}_v1"]
        self._graph.add((uri, self._RDF.type, self._ns.SceneDefinition))
        self._add_literal(uri, self._ns.viewCode, view_code)
        self._add_literal(uri, self._ns.viewName, view_name)
        self._add_literal(uri, self._ns.description, view_desc)
        self._add_literal(uri, self._ns.version, "1.0")
        if object_codes_json:
            self._add_literal(uri, self._ns.objectCodes, object_codes_json)
        if relations_json:
            self._add_literal(uri, self._ns.relations, relations_json)
        if field_refs:
            for ref_id in field_refs:
                self._graph.add((uri, self._ns.fields, self._ns[ref_id]))

    def add_scene_field(self, props: dict[str, str]) -> None:
        """添加 SceneField（视图字段定义）。

        Args:
            props: 字段属性字典，含 propertyCode, propertyName,
                   sourceObjectCode, sourceObjectColumnCode, synonyms, extProperty。
        """
        uri = self._ns[f"{_safe_xml_id(props['propertyCode'])}_field"]
        self._graph.add((uri, self._RDF.type, self._ns.SceneField))
        self._add_literal(uri, self._ns.propertyCode, props["propertyCode"])
        self._add_literal(uri, self._ns.propertyName, props["propertyName"])
        self._add_literal(uri, self._ns.sourceObjectCode, props.get("sourceObjectCode", ""))
        self._add_literal(
            uri, self._ns.sourceObjectColumnCode, props.get("sourceObjectColumnCode", "")
        )
        self._add_literal(uri, self._ns.synonyms, props.get("synonyms", ""))
        self._add_literal(uri, self._ns.extProperty, props.get("extProperty", ""))

    # ── 文件级输出辅助 ──────────────────────────────────────────────────────

    def export_terms_graph(self, term_type_code: str | None = None) -> Any:
        """导出仅包含术语定义的独立 Graph。

        用于生成 _terms.owl 或 _term_types.owl 独立文件。

        Args:
            term_type_code: 过滤特定术语类型编码，None 导出所有。

        Returns:
            仅含术语三元组的 rdflib.Graph。
        """
        from rdflib import Graph

        g = Graph()
        g.bind("", self._ns)
        for s, _p, _o in self._graph.triples((None, self._RDF.type, self._ns.TermDefinition)):
            if term_type_code is not None:
                # 过滤特定术语类型
                type_val = self._graph.value(s, self._ns.term_type_code)
                if type_val and str(type_val) != term_type_code:
                    continue
            for sp, po in self._graph.predicate_objects(s):
                g.add((s, sp, po))
        return g

    def export_term_types_graph(self) -> Any:
        """导出仅包含术语类型定义的独立 Graph。

        用于生成 _term_types.owl 独立文件。

        Returns:
            仅含 TermTypeDefinition 三元组的 rdflib.Graph。
        """
        from rdflib import Graph

        g = Graph()
        g.bind("", self._ns)
        for s, _p, _o in self._graph.triples((None, self._RDF.type, self._ns.TermTypeDefinition)):
            for sp, po in self._graph.predicate_objects(s):
                g.add((s, sp, po))
        return g

    def export_relations_graph(self, relation_category: str | None = None) -> Any:
        """导出仅包含关系定义的独立 Graph。

        用于生成 _attribute_relations.owl / _object_relations.owl 等独立文件。

        Args:
            relation_category: 过滤特定关系类别，None 导出所有。

        Returns:
            仅含关系三元组的 rdflib.Graph。
        """
        from rdflib import Graph

        g = Graph()
        g.bind("", self._ns)
        for s, _p, _o in self._graph.triples((None, self._RDF.type, self._ns.TermRelation)):
            if relation_category is not None:
                cat_val = self._graph.value(s, self._ns.relationCategory)
                if cat_val and str(cat_val) != relation_category:
                    continue
            for sp, po in self._graph.predicate_objects(s):
                g.add((s, sp, po))
        return g

    def export_actions_graph(self, action_code: str | None = None) -> Any:
        """导出仅包含 Action 定义的独立 Graph。

        Args:
            action_code: 过滤特定 Action 编码，None 导出所有。

        Returns:
            仅含 Action 三元组的 rdflib.Graph。
        """
        from rdflib import Graph

        g = Graph()
        g.bind("", self._ns)
        for s, _p, _o in self._graph.triples((None, self._RDF.type, self._ns.ActionDefinition)):
            if action_code is not None:
                ac_val = self._graph.value(s, self._ns.actionCode)
                if ac_val and str(ac_val) != action_code:
                    continue
            for sp, po in self._graph.predicate_objects(s):
                g.add((s, sp, po))
        return g

    # ── 内部辅助方法 ──────────────────────────────────────────────────────────

    def _add_literal(self, subject: Any, predicate: Any, value: str) -> None:
        """添加字面值三元组 (s, p, "value"^^xsd:string)。

        Args:
            subject: RDF 主语 URI。
            predicate: RDF 谓语 URI（Namespace 属性）。
            value: 字符串值。
        """
        from rdflib import Literal

        self._graph.add((subject, predicate, Literal(value)))


__all__ = [
    "GraphBuilder",
    "map_data_type",
]
