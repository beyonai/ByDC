"""
本体内部模型模块

本模块定义了本体（Ontology）的核心数据模型，包括：
- OntologyClass: 本体对象/类定义
- OntologyField: 对象字段定义
- OntologyAction: 对象动作定义
- OntologyRelation: 对象关联关系
- OntologyActionParam: 动作参数定义

这些模型构成了数据服务 SDK 的本体元数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldPhysicalMapping:
    """
    字段物理映射

    定义字段到物理存储的映射关系。

    Attributes:
        source_type: 数据源类型（DB/API）
        source_ref: 物理引用（DB 列名或 JSONPath）
        datasource_alias: 数据源别名
    """

    source_type: str
    source_ref: str
    datasource_alias: str


@dataclass
class OntologyField:
    """
    本体字段定义

    定义对象中的字段属性，包括类型、描述、术语映射等。

    Attributes:
        field_code: 字段代码
        field_name: 字段名称
        field_type: 字段类型（STRING/NUMBER/DATE/BOOLEAN/INTEGER/ARRAY/OBJECT）
        description: 字段描述
        aliases: 字段别名列表
        required: 是否必填
        is_primary_key: 是否主键
        source_column: 源列名
        term_set: 术语集名称
        term_type: 术语类型（enum/lookup）
        term_field: 术语字段（code/name）
        dataset_id: 数据集 ID
        physical_mappings: 物理映射列表
        property_kind: 属性分类（physical/derived/linked）
        derived_config: 派生字段配置
        relation_ref: 关联引用
        resolve_action_code: 解析动作代码
        resolve_param_binding: 解析参数绑定
        analytic_role: 分析角色（dimension/measure），来自 OWL ext_property.property_role_rule
        analytic_kind: 分析细分类（id/name/time/period/number/indicator），来自 OWL rule_type 映射
        secondary_role: 附加角色（由规则引擎推断，非 OWL 配置）
        filter_ops: 允许的过滤操作符列表（由规则引擎派生）
        group_ops: 允许的分组方式列表（由规则引擎派生）
        aggregate_ops: 允许的聚合函数列表（由规则引擎派生）
        required_filter_group: 强制过滤组（如 period_required）
    """

    field_code: str
    field_name: str
    field_type: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    required: bool = False
    is_primary_key: bool = False
    source_column: str | None = None
    term_set: str | None = None
    term_type: str | None = None
    term_field: str | None = None
    dataset_id: int | None = None
    physical_mappings: list[FieldPhysicalMapping] = field(default_factory=list)
    property_kind: str = "physical"
    derived_config: dict | None = None
    relation_ref: str | None = None
    resolve_action_code: str | None = None
    resolve_param_binding: dict | None = None
    # 分析语义字段（来自 OWL ext_property.property_role_rule，规则引擎派生）
    analytic_role: str | None = None  # "dimension" | "measure"
    analytic_kind: str | None = (
        None  # "id"|"name"|"datetime"|"period"|"numeric"|"raw_number"|"basic_metric"|...
    )
    secondary_role: str | None = None  # 规则推断的附加能力角色
    filter_ops: list[str] = field(default_factory=list)
    group_ops: list[str] = field(default_factory=list)
    aggregate_ops: list[str] = field(default_factory=list)
    required_filter_group: str | None = None
    formula: str | None = None  # derived_metric / formula_metric / virtual_tag 的 SQL 表达式


@dataclass
class OntologyActionParam:
    """
    本体动作参数

    定义动作的输入/输出参数。

    Attributes:
        param_code: 参数代码
        param_name: 参数名称
        direction: 参数方向（IN/OUT/INOUT）
        param_type: 参数类型
        required: 是否必填
        default_value: 默认值
        mapping_path: 响应映射路径
        term_set: 术语集名称
        term_type: 术语类型（enum/lookup）
        term_field: 术语字段（code/name）
        dataset_id: 数据集 ID
    """

    param_code: str
    param_name: str
    direction: str
    param_type: str
    required: bool = False
    default_value: Any = None
    mapping_path: str = ""
    term_set: str | None = None
    term_type: str | None = None
    term_field: str | None = None
    dataset_id: int | None = None


@dataclass
class OntologyAction:
    """
    本体动作定义

    定义对象上可执行的动作，支持 API 调用或 Python 脚本执行。

    执行优先级：script（非空）> function_refs > 抛 ActionNotConfiguredError

    Attributes:
        action_code: 动作代码
        action_name: 动作名称
        description: 动作描述
        belong_class: 所属对象代码
        params: 参数列表
        function_refs: 关联函数列表
        action_type: 动作类型（query/operation）
        script: Python 脚本内容
        is_virtual: 是否虚拟动作（兼容位）
        input_schema: 输入 JSON Schema
        output_schema: 输出 JSON Schema
        _schema_cache: Schema 缓存
        action_family: 动作族（lookup/analyze/search/operation）
        virtual_backend: 虚拟动作后端（db_lookup/db_analyze/kb_search/api_proxy）
        exposure_policy: 暴露策略（direct/skill_only/hidden）
        scope_type: 动作范围类型（object/view）
        scope_code: 动作所属对象编码或视图编码
        planner_visible: 是否对规划器可见
        legacy_aliases: 兼容旧动作名列表
    """

    action_code: str
    action_name: str
    description: str
    belong_class: str
    params: list[OntologyActionParam]
    function_refs: list[str]
    action_type: str
    script: str | None = None
    is_virtual: bool = False
    input_schema: dict | None = None
    output_schema: dict | None = None
    _schema_cache: dict | None = field(default=None, repr=False)
    # 虚拟动作新增字段
    action_family: str | None = None  # "lookup" | "analyze" | "search" | "operation"
    virtual_backend: str | None = None  # "db_lookup" | "db_analyze" | "kb_search" | "api_proxy"
    exposure_policy: str = "direct"  # "direct" | "skill_only" | "hidden"
    scope_type: str = "object"  # "object" | "view"
    scope_code: str = ""  # 对象编码或视图编码
    planner_visible: bool = True
    legacy_aliases: list[str] = field(default_factory=list)


@dataclass
class OntologyRelation:
    """
    本体关联关系

    定义对象间的关联关系。

    Attributes:
        relation_code: 关联代码
        relation_name: 关联名称
        source_class: 源对象代码
        target_class: 目标对象代码
        relation_type: 关联类型（ONE_TO_MANY/MANY_TO_ONE/ONE_TO_ONE/MANY_TO_MANY）
        join_keys: 连接键映射
        description: 关联描述
        resolve_action_code: 解析动作代码
        resolve_param_binding: 解析参数绑定
    """

    relation_code: str
    relation_name: str = ""
    source_class: str = ""
    target_class: str = ""
    relation_type: str = ""
    join_keys: list[dict[str, str]] = field(default_factory=list)
    description: str = ""
    resolve_action_code: str | None = None
    resolve_param_binding: dict | None = None


@dataclass
class OntologyClass:
    """
    本体对象/类定义

    定义数据服务中的核心对象模型。

    Attributes:
        object_code: 对象代码
        object_name: 对象名称
        description: 对象描述
        source_type: 数据源类型（DB/API）
        datasource_alias: 数据源别名
        table_name: 表名
        source_config: 数据源配置
        tags: 标签列表
        fields: 字段列表
        actions: 动作列表
    """

    object_code: str
    object_name: str
    description: str
    source_type: str  # DB / API / KNOWLEDGE_BASE
    datasource_alias: str | None = None
    table_name: str | None = None
    source_config: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    fields: list[OntologyField] = field(default_factory=list)
    actions: list[OntologyAction] = field(default_factory=list)
