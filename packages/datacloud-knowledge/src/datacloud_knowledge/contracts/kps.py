"""知识包中间模型（Knowledge Package Schema）— 生成/导入/校验的统一契约。

KPS 是生成器（owl_generate）与导入器（owl_import）之间的"缝（Seam）"：
- 生成器产出 KPS，再序列化为 OWL XML 文件；
- 导入器解析 OWL XML 文件，还原为 KPS，再写入数据库；
- 校验器对 KPS 执行语义校验，阻断不合规数据入库。

全部类型使用 frozen dataclass + slots，零外部依赖，可在任意上下文中安全传递。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DomainDef:
    """业务领域定义 — 术语的分类目录，支持层级结构。

    Attributes:
        domain_code: 领域编码（如 "D1"、"SALE"）。
        domain_name: 领域中文名称（如 "销售域"）。
        parent_code: 上级领域编码，None 表示根领域。
        domain_desc: 领域描述。
    """

    domain_code: str
    domain_name: str
    parent_code: str | None = None
    domain_desc: str = ""


@dataclass(frozen=True, slots=True)
class LibraryDef:
    """术语库定义 — 术语的来源归属，简单标识法。

    Attributes:
        library_code: 术语库编码（如 "L1"、"standard"）。
        library_name: 术语库中文名称（如 "标准术语库"）。
        library_desc: 术语库描述。
    """

    library_code: str
    library_name: str
    library_desc: str = ""


@dataclass(frozen=True, slots=True)
class TermTypeDef:
    """术语类型定义 — 描述一类术语的元信息。

    Attributes:
        type_code: 术语类型编码（如 "object"、"prop"、"LIST_TERM"）。
        type_name: 术语类型中文名称（如 "对象"、"属性"）。
        type_category: 大分类：1=列表术语(LIST_TERM), 2=字典术语(DICT_TERM),
                       3=本体术语(ONTOLOGY_TERM), 4=文档名称术语(DOC_NAME_TERM)。
        type_desc: 术语类型描述。
    """

    type_code: str
    type_name: str
    type_category: int  # 1:LIST_TERM, 2:DICT_TERM, 3:ONTOLOGY_TERM, 4:DOC_NAME_TERM
    type_desc: str = ""


@dataclass(frozen=True, slots=True)
class TermDef:
    """术语定义 — 知识图谱中最基本的语义单元。

    术语可以是对象(view/object)、属性(prop)、枚举值(list/dict term)等。
    通过 parent_term_code 建立层级关系（如 prop 归属 object、value 归属 prop）。

    Attributes:
        term_code: 术语编码（如 "by_customer"、"customer_name"、"签约成功"）。
        term_name: 术语标准中文名称（如 "客户"、"客户名称"）。
        term_type_code: 术语类型编码（如 "object"、"prop"、"LIST_TERM"）。
        library_code: 所属术语库编码。
        domain_code: 所属领域编码。
        parent_term_code: 父术语编码，None 表示顶层术语。
        synonyms: 同义词列表（如 ["顾客", "Client"]）。
        term_desc: 术语描述。
    """

    term_code: str
    term_name: str
    term_type_code: str
    library_code: str
    domain_code: str
    parent_term_code: str | None = None
    synonyms: tuple[str, ...] = ()
    term_desc: str = ""

    def compute_term_id(self, parent_term_id: str | None = None) -> str:
        """全系统唯一 term_id 计算入口。

        term_id 格式：{library_code}#{term_type_code}#{term_code}
        若有父术语：{parent_term_id}#{term_type_code}#{term_code}

        此方法是生成器、导入器、校验器统一的 term_id 计算规则唯一入口，
        替代之前分散在 17 个构建点的 f-string 拼接逻辑。
        """
        if parent_term_id:
            return f"{parent_term_id}#{self.term_type_code}#{self.term_code}"
        return f"{self.library_code}#{self.term_type_code}#{self.term_code}"


@dataclass(frozen=True, slots=True)
class ActionParamDef:
    """Action 请求/响应参数定义。

    Attributes:
        param_code: 参数编码（如 "id"、"customer_code"）。
        param_type: 参数类型（如 "integer"、"string"、"array"）。
        description: 参数中文描述。
        is_required: 是否为必填参数。
    """

    param_code: str
    param_type: str  # integer | string | array | ...
    description: str
    is_required: bool = False


@dataclass(frozen=True, slots=True)
class ActionDef:
    """Action 定义 — 数据操作 API 的语义描述。

    Action 不作为术语类型，不进入术语体系（不参与 BM25 检索、不生成 term_id）。
    Action 通过独立文件通道（actions/*.owl）与 EntityDefinition 的 action_refs 关联。
    Phase 1 Action 不落库，仅做文件级引用完整性校验。

    Attributes:
        action_code: Action 编码（如 "get_by_customer"）。
        action_name: Action 中文名称（如 "获取客户详情"）。
        action_type: Action 类型：QUERY（查询）或 MUTATION（变更）。
        request_url: API 接口 URL。
        request_method: HTTP 方法：GET | POST | PUT | DELETE。
        request_params: 请求参数列表。
        response_params: 响应参数列表。
    """

    action_code: str
    action_name: str
    action_type: str  # QUERY | MUTATION
    request_url: str
    request_method: str  # GET | POST
    request_params: tuple[ActionParamDef, ...] = ()
    response_params: tuple[ActionParamDef, ...] = ()
    # function_refs 等 Function 概念落地后追加


@dataclass(frozen=True, slots=True)
class RelationDef:
    """关系定义 — 术语之间的语义关系。

    关系是知识图谱的边，连接源术语与目标术语。
    relation_category 直接存入 DB 列，值为具体的关系类型。

    Attributes:
        source_term_code: 源术语编码（{lib}#{type}#{code} 格式）。
        target_term_code: 目标术语编码。
        relation_name: 关系中文名称（如 "包含"、"引用"）。
        relation_category: 关系类别：HAS_FIELD | HAS_OBJECT | HAS_TERM | MANY_TO_ONE。
        cardinality: 数量约束：1:1 | 1:N | N:1 | N:N。
        joinkeys: JOIN 键列表（仅 MANY_TO_ONE 关系有值），每项含 sourceField/targetField。
        ext_field: 扩展字段（JSON 格式存储其他业务属性）。
    """

    source_term_code: str  # {library}#{type}#{code}
    target_term_code: str
    relation_name: str
    relation_category: str  # HAS_FIELD | HAS_OBJECT | HAS_TERM | MANY_TO_ONE
    cardinality: str  # 1:1 | 1:N | N:1 | N:N
    joinkeys: tuple[dict[str, str], ...] = ()
    ext_field: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class KnowledgePackage:
    """知识包内存表示 — 生成/导入/校验的唯一契约。

    生成器产出 KnowledgePackage → 序列化为 OWL 文件；
    导入器解析 OWL 文件 → 还原为 KnowledgePackage → 写入 DB；
    校验器验证 KnowledgePackage → 阻断不合规数据。

    Attributes:
        terms: 术语定义列表（必填，不可为 None）。
        relations: 关系定义列表（必填，不可为 None）。
        domains: 领域定义列表。
        libraries: 术语库定义列表。
        term_types: 术语类型定义列表（仅 object/view/prop + 值术语类型，不含 action）。
        actions: Action 定义列表（独立通道，不作为术语）。
    """

    terms: tuple[TermDef, ...]
    relations: tuple[RelationDef, ...]
    domains: tuple[DomainDef, ...] = ()
    libraries: tuple[LibraryDef, ...] = ()
    term_types: tuple[TermTypeDef, ...] = ()  # 仅 object/view/prop + 值术语类型，不含 action
    actions: tuple[ActionDef, ...] = ()  # Action 独立通道


__all__ = [
    "ActionDef",
    "ActionParamDef",
    "DomainDef",
    "KnowledgePackage",
    "LibraryDef",
    "RelationDef",
    "TermDef",
    "TermTypeDef",
]
