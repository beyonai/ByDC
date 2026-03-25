"""
计划层数据模型

本模块定义了查询计划生成和执行过程中使用的所有数据模型。

核心模型分类：

视图载荷模型：
- ObjectViewPayload: 完整的视图载荷，包含对象、关系、数据源等
- ObjectViewObject: 对象视图定义
- ObjectViewField: 字段定义
- ObjectViewAction: 动作定义
- ObjectViewRelation: 关联关系定义

执行计划模型：
- QueryExecutionPlan: 查询执行计划
- PlanStep: 执行步骤
- PlanAggregation: 聚合配置

这些模型构成了 LLM 生成查询计划的输入和输出格式。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ObjectViewSource:
    """
    对象视图数据源
    
    定义对象数据的来源信息。
    
    Attributes:
        source_id: 数据源唯一标识
        source_type: 数据源类型（DB/API/KNOWLEDGE_BASE）
        datasource_alias: 数据源别名
        db_type: 数据库类型（仅 DB 类型有效）
    """
    
    source_id: str
    source_type: str
    datasource_alias: str = ""
    db_type: str = ""


@dataclass
class ObjectViewField:
    """
    对象视图字段
    
    定义对象中可查询的字段信息。
    
    Attributes:
        name: 字段代码
        type: 字段类型
        description: 字段描述
        aliases: 字段别名列表，支持多种名称引用
        term_set: 术语集名称，用于术语解析
        term_type: 术语类型
        dataset_id: 数据集 ID
        source_column: 物理列名，SQL 中必须使用此名称
    """
    
    name: str
    type: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    term_set: str | None = None
    term_type: str | None = None
    dataset_id: int | None = None
    source_column: str | None = None


@dataclass
class ObjectViewFunctionParam:
    """
    对象视图函数参数
    
    定义函数/动作的参数信息。
    
    Attributes:
        param_code: 参数代码
        param_name: 参数名称
        param_type: 参数类型
        direction: 参数方向（IN/OUT）
        required: 是否必填
        mapping_path: 响应映射路径
        default_value: 默认值
        term_set: 术语集名称
        term_type: 术语类型
        dataset_id: 数据集 ID
    """
    
    param_code: str
    param_name: str
    param_type: str
    direction: str
    required: bool = False
    mapping_path: str = ""
    default_value: Any = None
    term_set: str | None = None
    term_type: str | None = None
    dataset_id: int | None = None


@dataclass
class ObjectViewFunction:
    """
    对象视图函数
    
    定义对象上的函数接口。
    
    Attributes:
        function_code: 函数代码
        description: 函数描述
        params: 参数列表
    """
    
    function_code: str
    description: str = ""
    params: list[ObjectViewFunctionParam] = field(default_factory=list)


@dataclass
class ObjectViewAction:
    """
    对象视图动作
    
    定义对象上可执行的动作，供 LLM 选择调用。
    
    Attributes:
        action_code: 动作代码
        input_params: 输入参数列表
        output_params: 输出参数列表
        implementation_type: 实现类型（API/SCRIPT）
        function_code: 关联的函数代码（仅 API 类型）
    """

    action_code: str
    input_params: list[ObjectViewFunctionParam] = field(default_factory=list)
    output_params: list[ObjectViewFunctionParam] = field(default_factory=list)
    implementation_type: str = "API"
    function_code: str | None = None


@dataclass
class ObjectViewObject:
    """
    对象视图对象
    
    定义视图中的一个对象及其完整信息。
    
    Attributes:
        object_id: 对象 ID
        object_name: 对象名称
        source_id: 数据源 ID
        table: 表名
        description: 对象描述
        fields: 字段列表
        functions: 函数列表
        actions: 动作列表
    """
    
    object_id: str
    object_name: str
    source_id: str
    table: str = ""
    description: str = ""
    fields: list[ObjectViewField] = field(default_factory=list)
    functions: list[ObjectViewFunction] = field(default_factory=list)
    actions: list[ObjectViewAction] = field(default_factory=list)


@dataclass
class ObjectViewRelation:
    """
    对象视图关联关系
    
    定义对象间的关联关系。
    
    Attributes:
        from_object: 源对象 ID
        to_object: 目标对象 ID
        join_keys: 连接键映射
        cardinality: 基数类型
        description: 关联描述
    """
    
    from_object: str
    to_object: str
    join_keys: list[dict[str, str]] = field(default_factory=list)
    cardinality: str = "ONE_TO_MANY"
    description: str = ""


@dataclass
class ObjectViewPayload:
    """
    对象视图载荷
    
    完整的视图定义，作为 LLM 生成查询计划的输入。
    
    Attributes:
        view_id: 视图 ID
        view_name: 视图名称
        description: 视图描述
        sources: 数据源列表
        objects: 对象列表
        relations: 关联关系列表
    """
    
    view_id: str
    view_name: str = ""
    description: str = ""
    sources: list[ObjectViewSource] = field(default_factory=list)
    objects: list[ObjectViewObject] = field(default_factory=list)
    relations: list[ObjectViewRelation] = field(default_factory=list)


@dataclass
class PlanStep:
    """
    执行计划步骤
    
    定义查询执行计划中的单个步骤。
    
    Attributes:
        step_id: 步骤 ID
        type: 步骤类型（SQL/API/KB）
        source_id: 数据源 ID
        datasource_alias: 数据源别名
        sql_template: SQL 模板
        object_id: 对象 ID（API 类型必填）
        function_id: 函数/动作代码（API 类型）
        params: 执行参数
        output_ref: 输出引用名称
        bind_from_step: 绑定的前置步骤 ID
        bind_key: 绑定的键名
        query: 知识库查询文本
        tags: 知识库标签过滤
    """
    
    step_id: str
    type: str
    source_id: str = ""
    datasource_alias: str = ""
    sql_template: str = ""
    object_id: str = ""
    function_id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    output_ref: str = ""
    bind_from_step: str = ""
    bind_key: str = ""
    query: str = ""
    tags: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanAggregation:
    """
    执行计划聚合配置
    
    定义如何聚合多个步骤的执行结果。
    
    Attributes:
        strategy: 聚合策略（DIRECT/SQLITE_MEM）
        final_step_id: 最终步骤 ID
        sqlite_sql: SQLite 聚合 SQL
        columns: 输出列定义
    """
    
    strategy: str
    final_step_id: str | None = None
    sqlite_sql: str = ""
    columns: list[dict[str, str]] = field(default_factory=list)


@dataclass
class QueryExecutionPlan:
    """
    查询执行计划
    
    LLM 生成的完整查询执行计划，包含执行步骤和聚合配置。
    
    Attributes:
        question: 原始问题
        can_answer: 是否可以回答
        clarification: 澄清说明（无法回答时）
        steps: 执行步骤列表
        aggregation: 聚合配置
    """
    
    question: str = ""
    can_answer: bool = True
    clarification: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    aggregation: PlanAggregation | None = None


def parse_plan(data: dict[str, Any], question: str = "") -> QueryExecutionPlan:
    """
    将字典解析为 QueryExecutionPlan 对象
    
    从 snake_case 格式的字典构建执行计划对象，
    自动过滤掉不属于各模型的字段。
    
    Args:
        data: snake_case 格式的计划数据字典
        question: 原始问题（可选，作为默认值）
    
    Returns:
        QueryExecutionPlan: 解析后的执行计划对象
    """
    steps = [
        PlanStep(**{k: v for k, v in s.items() if k in PlanStep.__dataclass_fields__})
        for s in data.get("steps", [])
    ]
    agg_data = data.get("aggregation")
    aggregation = None
    if agg_data:
        aggregation = PlanAggregation(
            **{k: v for k, v in agg_data.items() if k in PlanAggregation.__dataclass_fields__}
        )
    return QueryExecutionPlan(
        question=data.get("question", question),
        can_answer=data.get("can_answer", True),
        clarification=data.get("clarification", ""),
        steps=steps,
        aggregation=aggregation,
    )
