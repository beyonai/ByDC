"""虚拟动作运行时模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VirtualActionProfile:
    """
    虚拟动作运行时 profile（由规则引擎自动推导，非 OWL 手工配置）。

    Attributes:
        action_family: 动作族（lookup/analyze/search）
        scope_type: 范围类型（object/view）
        scope_code: 对象编码或视图编码
        exposure_policy: 暴露策略（direct/skill_only/hidden）
        default_limit: 默认分页行数
        max_limit: 最大返回行数
        required_filters: 强制过滤字段 kind 列表（如 ["period"]）
        dimension_fields: 维度字段编码列表
        measure_fields: 度量字段编码列表
        action_name: 动作显示名
        description: 动作描述
    """

    action_family: str  # "lookup" | "analyze" | "search"
    scope_type: str  # "object" | "view"
    scope_code: str  # 对象编码或视图编码
    exposure_policy: str = "direct"
    default_limit: int = 100
    max_limit: int = 1000
    required_filters: list[str] = field(default_factory=list)
    dimension_fields: list[str] = field(default_factory=list)
    measure_fields: list[str] = field(default_factory=list)
    action_name: str = ""
    description: str = ""


@dataclass
class ViewFieldMeta:
    """
    视图字段元数据（来自 mapping OWL 的 Mapping 个体）。

    Attributes:
        property_code: 视图字段编码
        property_name: 视图字段显示名
        source_object_code: 源对象编码
        source_object_column_code: 源对象字段编码
        field_type: 继承自源对象字段的类型（如 DOUBLE/STRING/DATETIME）
        analytic_role: 分析角色（dimension/measure）
        analytic_kind: 分析细分类型
        filter_ops: 允许的过滤操作符
        group_ops: 允许的分组方式
        aggregate_ops: 允许的聚合函数
        secondary_role: 附加分析角色（如 dimension numeric 可兼作 measure）
        required_filter_group: 强制过滤组
    """

    property_code: str
    property_name: str
    source_object_code: str
    source_object_column_code: str
    field_type: str | None = None
    analytic_role: str | None = None
    analytic_kind: str | None = None
    secondary_role: str | None = None
    filter_ops: list[str] = field(default_factory=list)
    group_ops: list[str] = field(default_factory=list)
    aggregate_ops: list[str] = field(default_factory=list)
    required_filter_group: str | None = None
